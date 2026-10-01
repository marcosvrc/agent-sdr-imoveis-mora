"""Escolha do provedor de embeddings, e a guarda que importa: o tamanho do vetor.

`imoveis.embedding` e `documentos.embedding` são `vector(1024)`. Vetor de outro tamanho não degrada
a busca — o Postgres recusa a gravação no meio da indexação. E vetor do tamanho CERTO gerado por
outro modelo é pior ainda: grava sem reclamar e devolve vizinho errado para sempre, sem nenhum
sinal. Por isso as duas guardas testadas aqui: o provedor inválido levanta, e o tamanho é conferido
na resposta.
"""
import os

import httpx
import pytest

from sdr_shared.adapters.hospedados.embeddings import OpenAIEmbedder, OpenRouterEmbedder
from sdr_shared.config import get_settings
from sdr_shared.ports import factory


@pytest.fixture(autouse=True)
def ambiente_limpo():
    antes = {k: os.environ.get(k) for k in ("SDR_EMBEDDINGS_PROVIDER", "OPENAI_API_KEY",
                                             "SDR_OPENROUTER_API_KEY", "SDR_EMBEDDINGS_MODEL")}
    yield
    for k, v in antes.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    get_settings.cache_clear()
    factory.get_embedder.cache_clear()


def _escolher(**env):
    for k, v in env.items():
        os.environ[k] = v
    get_settings.cache_clear()
    factory.get_embedder.cache_clear()
    return factory.get_embedder()


def test_ollama_e_o_padrao_sem_configuracao():
    """Tem de rodar sem chave nenhuma: é o que permite clonar o projeto e subir."""
    os.environ.pop("SDR_EMBEDDINGS_PROVIDER", None)
    get_settings.cache_clear()
    factory.get_embedder.cache_clear()
    assert type(factory.get_embedder()).__name__ == "OllamaEmbedder"


def test_openai_entrega_as_dimensoes_do_schema():
    e = _escolher(SDR_EMBEDDINGS_PROVIDER="openai", OPENAI_API_KEY="sk-teste")
    assert type(e).__name__ == "OpenAIEmbedder"
    assert e.dimensoes == 1024, "o schema declara vector(1024); outro valor recusa na gravação"


def test_provedor_desconhecido_levanta():
    """Cair no padrão seria o pior desfecho: grava vetor de outro modelo no mesmo índice, sem erro
    nenhum na hora, e a busca passa a devolver o vizinho errado."""
    with pytest.raises(RuntimeError, match="não é suportado"):
        _escolher(SDR_EMBEDDINGS_PROVIDER="titan")


def test_openai_sem_chave_diz_o_que_falta():
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIEmbedder("", "text-embedding-3-small")


def test_pede_as_dimensoes_explicitamente(monkeypatch):
    """O modelo nasce com 1536. Sem mandar `dimensions`, o vetor chega grande demais e a indexação
    morre na primeira gravação — por isso o parâmetro é do adaptador, não uma opção de quem chama."""
    enviado = {}

    def falso_post(url, **kw):
        enviado.update(kw["json"])
        return httpx.Response(200, json={"data": [{"embedding": [0.0] * 1024}]})

    monkeypatch.setattr(httpx, "post", falso_post)
    OpenAIEmbedder("sk-teste", "text-embedding-3-small").embed("oi")
    assert enviado["dimensions"] == 1024
    assert enviado["model"] == "text-embedding-3-small"


def test_tamanho_inesperado_na_resposta_levanta(monkeypatch):
    """Se o padrão do outro lado mudar, parar aqui é melhor que gravar e descobrir na busca."""
    monkeypatch.setattr(httpx, "post", lambda url, **kw: httpx.Response(200, json={"data": [{"embedding": [0.0] * 1536}]}))
    with pytest.raises(RuntimeError, match="1024 dimensões e vieram 1536"):
        OpenAIEmbedder("sk-teste", "text-embedding-3-small").embed("oi")


def test_erro_da_api_chega_legivel(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, **kw: httpx.Response(401, text="Incorrect API key provided"))
    with pytest.raises(RuntimeError, match="401"):
        OpenAIEmbedder("sk-errada", "text-embedding-3-small").embed("oi")


# ------------------------------------------------------------------ OpenRouter (ADR-0016)

def test_openrouter_usa_a_chave_dele_e_nao_a_da_openai():
    os.environ.pop("OPENAI_API_KEY", None)
    e = _escolher(SDR_EMBEDDINGS_PROVIDER="openrouter", SDR_OPENROUTER_API_KEY="sk-or-teste")
    assert isinstance(e, OpenRouterEmbedder) and e.dimensoes == 1024
    # Sem fornecedor no ID, é o modelo da OpenAI: os vetores já indexados continuam valendo.
    assert e._model == "openai/text-embedding-3-small"
    assert e.URL == "https://openrouter.ai/api/v1/embeddings"


def test_openrouter_sem_chave_diz_o_que_falta():
    os.environ.pop("SDR_OPENROUTER_API_KEY", None)
    with pytest.raises(RuntimeError, match="SDR_OPENROUTER_API_KEY"):
        _escolher(SDR_EMBEDDINGS_PROVIDER="openrouter")


def test_openrouter_pede_dimensoes_e_nega_coleta(monkeypatch):
    enviados = []

    def falso_post(url, **kw):
        enviados.append((url, kw))
        return httpx.Response(200, json={"data": [{"embedding": [0.1] * 1024}]})

    monkeypatch.setattr(httpx, "post", falso_post)
    e = OpenRouterEmbedder("sk-or-teste", "baai/bge-m3", 1024, url="http://falso/api/v1")
    assert len(e.embed("tem fiador?")) == 1024
    url, kw = enviados[-1]
    assert url == "http://falso/api/v1/embeddings"
    assert kw["json"]["model"] == "baai/bge-m3", "ID com fornecedor passa intacto"
    assert kw["json"]["dimensions"] == 1024
    assert kw["json"]["provider"] == {"data_collection": "deny"}
    assert kw["headers"]["Authorization"] == "Bearer sk-or-teste"


def test_openrouter_que_ignora_dimensions_para_na_hora(monkeypatch):
    """Se o endpoint não repassar `dimensions`, o text-embedding-3-small volta com 1536: gravar isso
    num `vector(1024)` falharia no meio da indexação. A mensagem diz a causa provável."""
    monkeypatch.setattr(httpx, "post", lambda url, **kw: httpx.Response(200, json={"data": [{"embedding": [0.0] * 1536}]}))
    with pytest.raises(RuntimeError, match="ignorado o parâmetro `dimensions`"):
        OpenRouterEmbedder("sk-or-teste", "text-embedding-3-small").embed("x")
