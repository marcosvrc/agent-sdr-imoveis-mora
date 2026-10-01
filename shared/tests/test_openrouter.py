"""OpenRouter como provedor e papéis por função (ADR-0016).

O que estes testes guardam, do mais caro ao mais barato de errar:

1. O texto do cliente só passa pelo OpenRouter com retenção zero e sem coleta — em TODA requisição,
   inclusive na de saída estruturada. Conferido no corpo HTTP que sai, contra um servidor falso.
2. O custo que o OpenRouter informa chega à governança. Sem isso, modelo fora da tabela é gravado
   com custo zero e o teto mensal para de valer.
3. A extração cai só em endpoint que respeita o schema (`require_parameters`), e a conversa não.
4. O fallback entre a Anthropic direta e a Anthropic pelo OpenRouter traduz o ID nos dois sentidos.
5. Modelos que recusam `temperature` (Claude 5.x, GPT-6) não a recebem.
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ["SDR_PROFILE"] = "local"

import pytest  # noqa: E402

from sdr_shared import papeis as P  # noqa: E402
from sdr_shared.config import get_settings  # noqa: E402
from sdr_shared.ports import factory  # noqa: E402

pytest.importorskip("langchain_openai", reason="instale shared[openai] para testar o OpenRouter")


@pytest.fixture(autouse=True)
def _ambiente_limpo(monkeypatch):
    for k in ("SDR_LLM_PROVIDER", "SDR_LLM_PROVIDER_FALLBACK", "SDR_MODEL_EXTRACAO",
              "SDR_MODEL_INFORMACOES", "SDR_MODEL_ANALISE", "SDR_OPENROUTER_ZDR"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(factory, "_timeout_do_painel", lambda: None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ------------------------------------------------------------------ tradução de ID

@pytest.mark.parametrize("modelo,provedor,papel,esperado", [
    # Anthropic direta → OpenRouter: traço vira ponto, data some, prefixo hospedado some.
    ("claude-haiku-4-5", "openrouter", "roteamento", "anthropic/claude-haiku-4.5"),
    ("claude-sonnet-4-5-20250929", "openrouter", "conversa", "anthropic/claude-sonnet-4.5"),
    ("us.anthropic.claude-haiku-4-5", "openrouter", "extracao", "anthropic/claude-haiku-4.5"),
    ("claude-sonnet-5", "openrouter", "conversa", "anthropic/claude-sonnet-5"),
    ("gpt-5.6-luna", "openrouter", "roteamento", "openai/gpt-5.6-luna"),
    # Já é ID do OpenRouter: passa intacto, de qualquer fornecedor.
    ("google/gemini-3.5-flash-lite", "openrouter", "extracao", "google/gemini-3.5-flash-lite"),
    # E na volta: o reserva direto precisa de um ID que exista lá.
    ("anthropic/claude-haiku-4.5", "anthropic", "roteamento", "claude-haiku-4-5"),
    ("openai/gpt-5.6-terra", "openai", "conversa", "gpt-5.6-terra"),
    # Fornecedor que não é o do reserva: equivalente do papel — e papel novo usa o do pai.
    ("google/gemini-3.5-flash-lite", "anthropic", "extracao", "claude-haiku-4-5"),
    ("mistralai/mistral-medium-3.5", "openai", "informacoes", "gpt-5.6-terra"),
    ("google/gemini-3.8-flash", "anthropic", "analise", "claude-sonnet-4-5"),
])
def test_modelo_do_provedor_com_openrouter(modelo, provedor, papel, esperado):
    assert factory.modelo_do_provedor(modelo, provedor, papel) == esperado


def test_preco_dos_modelos_anthropic_e_openai_vale_pelo_openrouter():
    """O OpenRouter repassa o preço do fornecedor: a mesma linha da tabela serve aos dois caminhos."""
    from sdr_shared.governanca.precos import normalizar, preco_do_modelo
    assert normalizar("anthropic/claude-haiku-4.5") == "claude-haiku-4-5"
    assert preco_do_modelo("anthropic/claude-sonnet-4.5") == preco_do_modelo("claude-sonnet-4-5")
    assert preco_do_modelo("openai/gpt-5.6-luna") == preco_do_modelo("gpt-5.6-luna")
    # Fornecedor sem linha na tabela não herda preço de ninguém por semelhança de nome.
    assert preco_do_modelo("google/gemini-3.5-flash-lite") is None


def test_preco_sincronizado_de_fornecedor_conhecido_e_encontrado():
    """`openai/gpt-6-luna` não está na tabela padrão; sincronizado, fica gravado com o ID do
    OpenRouter. Procurar só pela forma normalizada (`gpt-6-luna`) não o acharia, e o painel
    recusaria salvar o modelo logo depois de cadastrar o preço dele."""
    from sdr_shared.governanca.precos import custo_usd, preco_do_modelo
    tabela = {"openai/gpt-6-luna": [0.1, 0.5, 0.0, 0.01]}
    assert preco_do_modelo("openai/gpt-6-luna", tabela) == (0.1, 0.5, 0.0, 0.01)
    assert custo_usd("openai/gpt-6-luna", 1_000_000, 0, tabela=tabela) == 0.1


def test_catalogo_so_mostra_openrouter_quando_ha_preco_sincronizado():
    assert "openrouter" not in factory.catalogo_de_modelos()
    c = factory.catalogo_de_modelos({"google/gemini-3.5-flash-lite": (0.3, 2.5, 0.0, 0.03)})
    assert c["openrouter"] == ["google/gemini-3.5-flash-lite"]


# ------------------------------------------------------------------ parâmetros por modelo

@pytest.mark.parametrize("modelo,raciocina,recusa_temp", [
    ("claude-haiku-4-5", False, False),
    ("claude-sonnet-4-5", False, False),
    ("claude-sonnet-5", True, True),
    ("claude-sonnet-5-5", True, True),
    ("anthropic/claude-sonnet-5.5", True, True),
    ("claude-opus-4-1", False, False),
    ("claude-opus-5-5", True, True),
    ("gpt-5.6-luna", True, True),
    ("gpt-6-luna", True, True),
    ("gpt-5-chat-latest", False, False),
    ("google/gemini-3.5-flash-lite", True, False),
    ("mistralai/ministral-8b", False, False),
])
def test_quem_raciocina_e_quem_recusa_temperatura(modelo, raciocina, recusa_temp):
    assert factory.raciocina_por_padrao(modelo) is raciocina
    assert factory.recusa_temperatura(modelo) is recusa_temp


def test_claude_5_direto_sem_temperatura_com_folga_e_schema_nativo(monkeypatch):
    """Sonnet 5.5 devolve 400 para `temperature` em qualquer chamada e raciocina dentro do
    `max_tokens`. Com tool calling e raciocínio ligado a extração deixa de ser forçada — daí o
    schema nativo."""
    pytest.importorskip("langchain_anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-teste")
    m = factory._construir("anthropic", "claude-sonnet-5-5", 0.0, "extracao", max_tokens=600)
    assert isinstance(m, factory.SaidaEstruturadaNativa)
    cru = m._modelo._modelo if isinstance(m._modelo, factory.ModeloComCacheDePrompt) else m._modelo
    assert cru.temperature is None
    assert cru.max_tokens == 600 * factory.FOLGA_RACIOCINIO
    if "reasoning_effort" in type(cru).model_fields:
        assert cru.reasoning_effort == "low", "`none` do papel vira o mínimo que a Anthropic aceita"

    pedidos = []
    monkeypatch.setattr(type(cru), "with_structured_output",
                        lambda self, schema, **kw: pedidos.append(kw) or "ok")
    m.with_structured_output(dict)
    assert pedidos[-1]["method"] == "json_schema"


def test_claude_4_5_direto_segue_como_antes(monkeypatch):
    pytest.importorskip("langchain_anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-teste")
    m = factory._construir("anthropic", "claude-haiku-4-5", 0.0, "roteamento", max_tokens=600)
    assert not isinstance(m, factory.SaidaEstruturadaNativa)
    cru = m._modelo if isinstance(m, factory.ModeloComCacheDePrompt) else m
    assert cru.temperature == 0.0 and cru.max_tokens == 600


# ------------------------------------------------------------------ cliente OpenRouter

@pytest.fixture(autouse=True)
def _sem_config_de_raciocinio(monkeypatch):
    """Sem isto, construir um modelo do OpenRouter iria à rede buscar o catálogo."""
    import sdr_shared.adapters.hospedados.openrouter as orq
    monkeypatch.setattr(orq, "config_raciocinio", lambda m: None)


def _openrouter(monkeypatch, modelo, papel, suportados=None, raciocinio=None, **env):
    monkeypatch.setenv("SDR_OPENROUTER_API_KEY", "sk-or-teste")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    import sdr_shared.adapters.hospedados.openrouter as orq
    monkeypatch.setattr(orq, "parametros_suportados", lambda m: suportados)
    monkeypatch.setattr(orq, "config_raciocinio", lambda m: raciocinio)
    return factory._construir("openrouter", modelo, P.TEMPERATURA[papel], papel,
                              max_tokens=P.MAX_TOKENS[papel])


def test_toda_requisicao_ao_openrouter_exige_retencao_zero(monkeypatch):
    m = _openrouter(monkeypatch, "google/gemini-3.5-flash-lite", "extracao")
    assert isinstance(m, factory.ModeloOpenRouter)
    for cliente in (m._livre, m._estrito):
        pref = cliente.extra_body["provider"]
        assert pref["zdr"] is True and pref["data_collection"] == "deny"
        assert pref["sort"] == "latency", "extração: saída curta, o que pesa é o primeiro token"
    assert "require_parameters" not in m._livre.extra_body["provider"]
    assert m._estrito.extra_body["provider"]["require_parameters"] is True


def test_zdr_so_sai_quando_desligado_de_proposito(monkeypatch):
    m = _openrouter(monkeypatch, "google/gemini-3.5-flash-lite", "conversa", SDR_OPENROUTER_ZDR="false")
    assert "zdr" not in m._livre.extra_body["provider"]
    assert m._livre.extra_body["provider"]["data_collection"] == "deny", "coleta continua negada"
    assert m._livre.extra_body["provider"]["sort"] == "throughput"


def test_raciocinio_e_temperatura_seguem_o_catalogo(monkeypatch):
    # O catálogo diz que o modelo não aceita temperatura: não vai, nem no cliente livre.
    m = _openrouter(monkeypatch, "google/gemini-3.5-flash-lite", "extracao",
                    suportados={"reasoning", "response_format", "structured_outputs"})
    assert m._livre.temperature is None
    assert m._livre.extra_body["reasoning"] == {"effort": "none"}
    assert m._estrito.extra_body["reasoning"] == {"effort": "none"}
    assert m._livre.max_tokens == 600 * factory.FOLGA_RACIOCINIO


_COM_RACIOCINIO = {"reasoning", "response_format", "structured_outputs", "tools"}


def test_raciocinio_obrigatorio_recebe_o_menor_esforco_aceito(monkeypatch):
    """A primeira matriz real: o gpt-oss-120b levou 400 em 44 de 44 chamadas ("Reasoning is
    mandatory for this endpoint and cannot be disabled") porque a extração pede `none`."""
    m = _openrouter(monkeypatch, "openai/gpt-oss-120b", "extracao", suportados=_COM_RACIOCINIO,
                    raciocinio={"mandatory": True, "supported_efforts": ["high", "low", "medium"]})
    assert m._livre.extra_body["reasoning"] == {"effort": "low"}
    assert m._estrito.extra_body["reasoning"] == {"effort": "low"}


def test_obrigatorio_sem_lista_de_esforcos_usa_low(monkeypatch):
    m = _openrouter(monkeypatch, "z-ai/glm-5.3-flash", "roteamento", suportados=_COM_RACIOCINIO,
                    raciocinio={"mandatory": True})
    assert m._livre.extra_body["reasoning"] == {"effort": "low"}


def test_quem_deixa_desligar_continua_com_none(monkeypatch):
    """O que a matriz já mediu com Luna e DeepSeek não muda: o DeepSeek nem lista `none`, e aceita."""
    m = _openrouter(monkeypatch, "deepseek/deepseek-v4.1-flash", "extracao", suportados=_COM_RACIOCINIO,
                    raciocinio={"mandatory": False, "supported_efforts": ["max", "high", "low"]})
    assert m._livre.extra_body["reasoning"] == {"effort": "none"}


def test_obrigatorio_nao_mexe_no_esforco_de_quem_ja_pede_raciocinio(monkeypatch):
    m = _openrouter(monkeypatch, "openai/gpt-oss-120b", "analise", suportados=_COM_RACIOCINIO,
                    raciocinio={"mandatory": True, "supported_efforts": ["low", "high"]})
    assert m._livre.extra_body["reasoning"] == {"effort": "medium"}


def test_sem_catalogo_gpt_oss_vai_com_low(monkeypatch):
    m = _openrouter(monkeypatch, "openai/gpt-oss-120b", "extracao", suportados=_COM_RACIOCINIO)
    assert m._livre.extra_body["reasoning"] == {"effort": "low"}


def test_estrito_nao_manda_o_que_o_modelo_nao_declara(monkeypatch):
    """Com `require_parameters`, um parâmetro não declarado deixa o OpenRouter sem endpoint."""
    m = _openrouter(monkeypatch, "mistralai/ministral-8b", "extracao",
                    suportados={"temperature", "response_format", "structured_outputs"})
    assert "reasoning" not in m._estrito.extra_body
    assert m._estrito.temperature == 0.0


# ------------------------------------------------------------------ ponta a ponta, por HTTP

class _FalsoOpenRouter(BaseHTTPRequestHandler):
    pedidos: list = []

    def log_message(self, *a):
        pass

    def _json(self, corpo: dict):
        dados = json.dumps(corpo).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):  # catálogo /models
        self._json({"data": [{"id": "google/gemini-3.5-flash-lite",
                              "supported_parameters": ["reasoning", "response_format",
                                                       "structured_outputs", "max_tokens"],
                              "pricing": {"prompt": "0.0000003", "completion": "0.0000025",
                                          "input_cache_read": "0.00000003"}}]})

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FalsoOpenRouter.pedidos.append(corpo)
        estruturado = "response_format" in corpo or "tools" in corpo
        conteudo = json.dumps({"bairro": "Pinheiros"}) if estruturado else "ok"
        self._json({"id": "gen-1", "object": "chat.completion", "created": 0, "model": corpo["model"],
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant", "content": conteudo}}],
                    "usage": {"prompt_tokens": 120, "completion_tokens": 8, "total_tokens": 128,
                              "cost": 0.000123}})


@pytest.fixture
def falso_openrouter(monkeypatch):
    _FalsoOpenRouter.pedidos = []
    srv = HTTPServer(("127.0.0.1", 0), _FalsoOpenRouter)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("SDR_OPENROUTER_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("SDR_OPENROUTER_API_KEY", "sk-or-teste")
    get_settings.cache_clear()
    import sdr_shared.adapters.hospedados.openrouter as orq
    orq._cache.update(em=0.0, modelos=None)
    gravados = []

    class Repo:
        def registrar(self, **kw):
            gravados.append(kw)

        def precos(self):
            return {}

    import sdr_shared.db.governanca as gov
    monkeypatch.setattr(gov, "UsoRepository", Repo)
    yield gravados
    srv.shutdown()
    orq._cache.update(em=0.0, modelos=None)


def test_corpo_http_e_custo_informado_chegam_certos(falso_openrouter):
    from pydantic import BaseModel

    m = factory._construir("openrouter", "google/gemini-3.5-flash-lite", 0.0, "extracao",
                           max_tokens=600, registro="extracao")
    assert m.invoke("oi").content == "ok"

    class Cartao(BaseModel):
        bairro: str

    assert m.with_structured_output(Cartao).invoke("moro em pinheiros").bairro == "Pinheiros"

    livre, estrito = _FalsoOpenRouter.pedidos
    for corpo in (livre, estrito):
        assert corpo["provider"]["zdr"] is True and corpo["provider"]["data_collection"] == "deny"
        assert corpo["reasoning"] == {"effort": "none"}
        assert "temperature" not in corpo, "o catálogo não declara temperatura para este modelo"
    assert "require_parameters" not in livre["provider"]
    assert estrito["provider"]["require_parameters"] is True

    # O custo da resposta é o que vai para a governança — o modelo nem está na tabela de preços.
    assert [g["custo"] for g in falso_openrouter] == [0.000123, 0.000123]
    assert {g["provider"] for g in falso_openrouter} == {"openrouter"}
    assert {g["papel"] for g in falso_openrouter} == {"extracao"}


def test_preco_sincronizado_sai_por_milhao(falso_openrouter):
    from sdr_shared.adapters.hospedados.openrouter import precos_de
    achados, faltando = precos_de(["google/gemini-3.5-flash-lite", "nao/existe"])
    assert achados == {"google/gemini-3.5-flash-lite": [0.3, 2.5, 0.0, 0.03]}
    assert faltando == ["nao/existe"]


# ------------------------------------------------------------------ papéis e herança

def test_todo_papel_tem_temperatura_teto_esforco_e_ordenacao():
    for tabela in (P.TEMPERATURA, P.MAX_TOKENS, P.ESFORCO, P.ORDENACAO_OPENROUTER, P.DESCRICAO):
        assert set(tabela) == set(P.PAPEIS)
    assert all(P.raiz(p) in ("conversa", "roteamento") for p in P.PAPEIS)


def test_precedencia_painel_e_ambiente_nivel_a_nivel(monkeypatch):
    """painel do papel → ambiente do papel → painel do pai → ambiente do pai."""
    painel = {}
    monkeypatch.setattr(factory, "_escolha_do_painel", lambda p: painel.get(p, (None, None)))
    monkeypatch.setenv("SDR_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("SDR_MODEL_ROTEAMENTO", "claude-haiku-4-5")
    get_settings.cache_clear()
    assert factory.modelo_efetivo("extracao") | {} == {"modelo": "claude-haiku-4-5", "provider": "anthropic",
                                                       "origem": "ambiente", "de": "roteamento"}
    painel["roteamento"] = ("gpt-5.6-luna", "openai")
    assert factory.modelo_efetivo("extracao")["modelo"] == "gpt-5.6-luna", "herda o painel do pai"

    monkeypatch.setenv("SDR_MODEL_EXTRACAO", "anthropic/claude-haiku-4.5")
    get_settings.cache_clear()
    e = factory.modelo_efetivo("extracao")
    assert (e["modelo"], e["origem"], e["de"]) == ("anthropic/claude-haiku-4.5", "ambiente", "extracao"), \
        "o ambiente do próprio papel vence o painel do pai"

    painel["extracao"] = ("google/gemini-3.5-flash-lite", "openrouter")
    e = factory.modelo_efetivo("extracao")
    assert (e["modelo"], e["provider"], e["origem"]) == ("google/gemini-3.5-flash-lite", "openrouter", "painel")


def test_degradado_poe_todo_papel_no_barato_e_grava_a_funcao(monkeypatch):
    chamadas = []
    monkeypatch.setattr(factory, "modo_do_agente", lambda: "degradado")
    monkeypatch.setattr(factory, "_reserva_do_painel", lambda: "nenhum")
    monkeypatch.setattr(factory, "_escolha_do_painel", lambda p: (None, None))
    monkeypatch.setattr(factory, "_construir",
                        lambda provider, model, temp, papel, **kw: chamadas.append((model, papel, kw)))
    monkeypatch.setenv("SDR_MODEL_EXTRACAO", "claude-sonnet-4-5")     # alguém pôs um caro na extração
    monkeypatch.setenv("SDR_MODEL_ROTEAMENTO", "claude-haiku-4-5")
    get_settings.cache_clear()
    for papel in ("extracao", "informacoes", "analise"):
        factory.get_chat_model(papel)
        modelo, atende, kw = chamadas[-1]
        assert modelo == "claude-haiku-4-5" and atende == "roteamento"
        assert kw["registro"] == papel, "a governança grava a função, não quem atendeu"
        assert kw["max_tokens"] == P.MAX_TOKENS[papel]


# ------------------------------------------------------------------ cache de prompt pelo OpenRouter

@pytest.mark.parametrize("modelo,marca", [
    ("anthropic/claude-sonnet-5", True),
    ("qwen/qwen3.8-27b", True),
    ("openai/gpt-6-luna", False),          # cache automático: marcar seria ruído
    ("google/gemma-4-26b-a4b-it", False),
])
def test_so_quem_exige_marcacao_recebe(monkeypatch, modelo, marca):
    m = _openrouter(monkeypatch, modelo, "conversa")
    assert isinstance(m, factory.ModeloComCacheDePrompt) is marca


def test_cache_desligado_pelo_ambiente_vale_no_openrouter(monkeypatch):
    m = _openrouter(monkeypatch, "anthropic/claude-sonnet-5", "conversa", SDR_PROMPT_CACHE="false")
    assert not isinstance(m, factory.ModeloComCacheDePrompt)


def test_marcacao_chega_no_corpo_http_e_cache_chega_na_governanca(falso_openrouter, monkeypatch):
    """A marcação precisa sobreviver ao `langchain-openai` até o corpo que sai, e os tokens de cache
    que o OpenRouter devolve (`cached_tokens`, `cache_write_tokens`) precisam chegar a `uso_llm`."""
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    def resposta_com_cache(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _FalsoOpenRouter.pedidos.append(corpo)
        self._json({"id": "gen-2", "object": "chat.completion", "created": 0, "model": corpo["model"],
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant", "content": "ok"}}],
                    "usage": {"prompt_tokens": 1500, "completion_tokens": 10, "total_tokens": 1510,
                              "cost": 0.0004, "prompt_tokens_details": {"cached_tokens": 1200,
                                                                        "cache_write_tokens": 200}}})

    monkeypatch.setattr(_FalsoOpenRouter, "do_POST", resposta_com_cache)
    m = factory._construir("openrouter", "anthropic/claude-sonnet-5", 0.6, "conversa",
                           max_tokens=600, registro="conversa")
    assert isinstance(m, factory.ModeloComCacheDePrompt)
    historico = [SystemMessage(content="blindagem + persona"), HumanMessage(content="oi"),
                 AIMessage(content="olá"), HumanMessage(content="quero alugar")]
    m.invoke(historico)

    msgs = _FalsoOpenRouter.pedidos[-1]["messages"]
    marcados = [isinstance(x["content"], list) and "cache_control" in x["content"][-1] for x in msgs]
    assert marcados == [True, False, False, True], "fim do system e fim do histórico"
    assert historico[0].content == "blindagem + persona", "o histórico do checkpoint não é tocado"

    g = falso_openrouter[-1]
    assert (g["cache_leitura"], g["cache_escrita"]) == (1200, 200)
    assert g["entrada"] == 100, "entrada nova = total − lido − escrito"
    assert g["custo"] == 0.0004


# ------------------------------------------------------------------ saída estruturada por ferramenta

class _Cartao(__import__("pydantic").BaseModel):
    bairro: str


def _responde_com_ferramenta(self):
    corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
    _FalsoOpenRouter.pedidos.append(corpo)
    nome = corpo["tools"][0]["function"]["name"]
    self._json({"id": "gen-3", "object": "chat.completion", "created": 0, "model": corpo["model"],
                "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{"id": "call_1", "type": "function", "function": {
                        "name": nome, "arguments": json.dumps({"bairro": "Pinheiros"})}}]}}],
                "usage": {"prompt_tokens": 300, "completion_tokens": 20, "total_tokens": 320, "cost": 0.0001}})


@pytest.mark.parametrize("modelo,suportados,forcado", [
    # Claude com retenção zero: só Bedrock, com ferramentas e sem schema. Não força — raciocínio ligado.
    ("anthropic/claude-sonnet-5", ["tools", "reasoning", "max_tokens"], False),
    # DeepSeek em host sem `structured_outputs`: ferramenta, e aí pode forçar.
    ("deepseek/deepseek-v4.1-flash", ["tools", "response_format", "reasoning"], True),
])
def test_sem_schema_a_extracao_vai_por_ferramenta(falso_openrouter, monkeypatch, modelo, suportados, forcado):
    """Pedir schema a um endpoint que não o declara, com `require_parameters`, deixa o OpenRouter
    sem endpoint: toda extração do cartão falharia. Ferramenta esses endpoints aceitam."""
    import sdr_shared.adapters.hospedados.openrouter as orq
    monkeypatch.setattr(orq, "parametros_suportados", lambda m: set(suportados))
    monkeypatch.setattr(_FalsoOpenRouter, "do_POST", _responde_com_ferramenta)
    m = factory._construir("openrouter", modelo, 0.0, "extracao", max_tokens=600, registro="extracao")

    assert m.with_structured_output(_Cartao).invoke("moro em pinheiros") == _Cartao(bairro="Pinheiros")
    corpo = _FalsoOpenRouter.pedidos[-1]
    assert "response_format" not in corpo, "schema não vai para endpoint que não o declara"
    assert corpo["tools"][0]["function"]["name"] == "_Cartao"
    assert corpo["provider"]["require_parameters"] is True
    if forcado:
        assert corpo["tool_choice"]["function"]["name"] == "_Cartao"
    else:
        assert "tool_choice" not in corpo, "Claude com raciocínio ligado recusa ferramenta forçada"


def test_com_schema_declarado_continua_por_schema(monkeypatch):
    m = _openrouter(monkeypatch, "openai/gpt-6-luna", "extracao",
                    suportados={"structured_outputs", "response_format", "tools", "reasoning"})
    assert m._por_ferramenta is False


def test_sem_catalogo_claude_vai_por_ferramenta_e_os_demais_por_schema(monkeypatch):
    claude = _openrouter(monkeypatch, "anthropic/claude-sonnet-5", "extracao", suportados=None)
    alvo = claude._modelo if isinstance(claude, factory.ModeloComCacheDePrompt) else claude
    assert alvo._por_ferramenta is True and alvo._forcar is False
    assert _openrouter(monkeypatch, "openai/gpt-6-luna", "extracao", suportados=None)._por_ferramenta is False


def test_chamada_que_falha_e_gravada_com_o_modelo_pedido(falso_openrouter, monkeypatch):
    """Um 401 não tem resposta de onde tirar o nome do modelo. Antes caía no modelo do .env, e o
    painel culpava `claude-haiku-4-5` pelo erro de `openai/gpt-6-luna`."""
    def recusa(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        dados = b'{"error": {"message": "Missing Authentication header", "code": 401}}'
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    monkeypatch.setattr(_FalsoOpenRouter, "do_POST", recusa)
    monkeypatch.setenv("SDR_MODEL_ROTEAMENTO", "claude-haiku-4-5")
    get_settings.cache_clear()
    m = factory._construir("openrouter", "openai/gpt-6-luna", 0.0, "roteamento", max_tokens=600,
                           registro="roteamento")
    import openai
    with pytest.raises(openai.AuthenticationError):
        m.invoke("oi")
    erros = [g for g in falso_openrouter if g["erro"]]
    assert erros and {g["modelo"] for g in erros} == {"openai/gpt-6-luna"}


def test_extracao_tenta_de_novo_no_openrouter_quando_vem_sem_choices(monkeypatch):
    """O OpenRouter às vezes devolve o erro do provedor com status 200 e sem `choices`; o cliente
    estoura TypeError. Metade das extrações de um teste real caiu assim no reserva direto."""
    m = _openrouter(monkeypatch, "openai/gpt-6-luna", "extracao",
                    suportados={"response_format", "structured_outputs", "reasoning"})
    chamadas = []

    class _Instavel:
        def with_structured_output(self, schema, **kw):
            from langchain_core.runnables import RunnableLambda

            def responder(_):
                chamadas.append(1)
                if len(chamadas) == 1:
                    raise TypeError("'NoneType' object is not iterable")
                return {"ok": True}
            return RunnableLambda(responder)

    m._estrito = _Instavel()
    assert m.with_structured_output(dict).invoke("x") == {"ok": True}
    assert len(chamadas) == 2


def test_resposta_vazia_tenta_de_novo(monkeypatch):
    """Um cliente mandou tudo numa mensagem e recebeu o texto de reserva: o modelo raciocinou e
    devolveu conteúdo vazio, que o filtro de saída troca por "me conta o que você procura…"."""
    from langchain_core.messages import AIMessage
    m = _openrouter(monkeypatch, "deepseek/deepseek-v4.1-flash", "conversa", suportados={"reasoning"})
    respostas = [AIMessage(content=""), AIMessage(content="Achei três opções em Moema.")]

    class _Livre:
        model_name = "deepseek/deepseek-v4.1-flash"

        def invoke(self, *a, **k):
            return respostas.pop(0)
    m._livre = _Livre()
    assert m.invoke("x").content == "Achei três opções em Moema."
    assert respostas == []
