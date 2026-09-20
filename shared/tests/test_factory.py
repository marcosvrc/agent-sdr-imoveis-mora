"""O mesmo modelo tem ID diferente em cada provedor — trocar de provedor no .env não pode exigir
trocar o ID do modelo. Regressão do caminho Anthropic: IDs com prefixo de provedor hospedado
(`anthropic.`, `us.`) quebravam a API direta, e um `.env` herdado ainda pode trazê-los."""
import pytest
from sdr_shared.ports.factory import modelo_do_provedor, normalizar_modelo


@pytest.mark.parametrize("modelo,provedor,esperado", [
    ("anthropic.claude-sonnet-4-5", "anthropic", "claude-sonnet-4-5"),
    ("us.anthropic.claude-haiku-4-5", "anthropic", "claude-haiku-4-5"),
    ("claude-sonnet-4-5", "anthropic", "claude-sonnet-4-5"),
    # Outro provedor: o ID passa intacto — quem normaliza prefixo da Anthropic é o caminho dela.
    ("gpt-5.6-terra", "openai", "gpt-5.6-terra"),
])
def test_normalizar_modelo(modelo, provedor, esperado):
    assert normalizar_modelo(modelo, provedor) == esperado


def _modelo(monkeypatch, **env):
    """Constrói o chat model com um ambiente limpo (get_settings é cacheado)."""
    pytest.importorskip("langchain_anthropic", reason="instale shared[local] para testar este caminho")
    from sdr_shared.config import get_settings
    from sdr_shared.ports import factory
    for k in ("SDR_LLM_PROVIDER", "SDR_ANTHROPIC_WORKSPACE_ID", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    try:
        return factory.get_chat_model("conversa")
    finally:
        get_settings.cache_clear()


def _headers(m) -> dict:
    return dict(m._client._custom_headers)


def test_workspace_id_vira_header(monkeypatch):
    """Chave de organização (não escopada a workspace) só funciona com este header."""
    m = _modelo(monkeypatch, SDR_LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-ant-teste",
                SDR_ANTHROPIC_WORKSPACE_ID="wrkspc_abc")
    assert _headers(m)["anthropic-workspace-id"] == "wrkspc_abc"
    assert m.model == "claude-sonnet-4-5"          # sem o prefixo `anthropic.` herdado


def test_sem_workspace_id_nao_manda_header(monkeypatch):
    """Chave já escopada a um workspace rejeita o header, então ele não pode ir por padrão."""
    m = _modelo(monkeypatch, SDR_LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-ant-teste")
    assert "anthropic-workspace-id" not in _headers(m)


# ---------------------------------------------------------- famílias diferentes

@pytest.mark.parametrize("modelo,provedor,papel,esperado", [
    # Mesma família: só o prefixo muda, o modelo é o mesmo.
    ("claude-sonnet-4-5", "anthropic", "conversa", "claude-sonnet-4-5"),
    ("anthropic.claude-haiku-4-5", "anthropic", "roteamento", "claude-haiku-4-5"),
    # Família diferente: traduzir o NOME não faria o modelo existir do outro lado. Troca-se pelo
    # equivalente do papel — modelo bom para conversa, modelo barato para roteamento.
    ("claude-sonnet-4-5", "openai", "conversa", "gpt-5.6-terra"),
    ("claude-haiku-4-5", "openai", "roteamento", "gpt-5.6-luna"),
    ("anthropic.claude-sonnet-4-5", "openai", "analise", "gpt-5.6-terra"),
    # E na volta: quem configura OpenAI como primário e Anthropic como reserva também precisa disso.
    ("gpt-5.6-terra", "anthropic", "conversa", "claude-sonnet-4-5"),
    ("gpt-5.6-luna", "anthropic", "roteamento", "claude-haiku-4-5"),
    # Modelo já da família do provedor passa intacto.
    ("gpt-5-mini", "openai", "conversa", "gpt-5-mini"),
])
def test_modelo_do_provedor(modelo, provedor, papel, esperado):
    assert modelo_do_provedor(modelo, provedor, papel) == esperado


def test_fallback_para_outra_familia_usa_um_modelo_que_existe_la(monkeypatch):
    """O teste que justifica a tabela de equivalência existir.

    Sem ela, `_construir(reserva, model, …)` mandaria `claude-sonnet-4-5` para a OpenAI e voltaria
    404 — o reserva falharia exatamente no momento em que ele existe para servir.
    """
    pytest.importorskip("langchain_openai", reason="instale shared[openai] para testar este caminho")
    m = _modelo(monkeypatch, SDR_LLM_PROVIDER="anthropic", ANTHROPIC_API_KEY="sk-ant-teste",
                SDR_LLM_PROVIDER_FALLBACK="openai", OPENAI_API_KEY="sk-teste")
    assert m.__class__.__name__ == "ModeloComFallback"
    assert m._primario.model == "claude-sonnet-4-5"
    assert m._reserva.model_name.startswith("gpt-"), "o reserva precisa de um ID que exista na OpenAI"


def test_todo_modelo_equivalente_tem_preco():
    """Modelo sem preço na tabela é registrado com custo ZERO: o painel mostra gasto menor que o
    real e a degradação por orçamento nunca dispara. O fallback é justamente o caminho em que
    ninguém está olhando na hora."""
    from sdr_shared.governanca.precos import PRECOS_PADRAO, normalizar
    from sdr_shared.ports.factory import _EQUIVALENTE
    for provedor, papeis in _EQUIVALENTE.items():
        for papel, modelo in papeis.items():
            assert normalizar(modelo) in PRECOS_PADRAO, f"{provedor}/{papel}: {modelo} sem preço"


def test_catalogo_so_oferece_modelo_que_o_painel_consegue_salvar():
    """O combo da tela sai daqui. Se oferecesse um modelo sem preço, o usuário escolheria da lista
    e levaria 422 no salvar — ou pior, salvaria e desligaria o teto de orçamento em silêncio."""
    from sdr_shared.governanca.precos import PRECOS_PADRAO, preco_do_modelo
    from sdr_shared.ports.factory import catalogo_de_modelos

    catalogo = catalogo_de_modelos()
    assert set(catalogo) == {"openai", "anthropic"}, "Ollama não tem lista: depende do que a máquina baixou"
    for provedor, modelos in catalogo.items():
        assert modelos, f"{provedor} ficou sem nenhuma opção"
        for m in modelos:
            assert preco_do_modelo(m), f"{m} entrou no combo sem preço"
    assert "claude-sonnet-4-5" in catalogo["anthropic"] and "gpt-5-mini" in catalogo["openai"]
    # embeddings e modelo local não são opção de conversa
    assert "bge-m3" not in catalogo["anthropic"] + catalogo["openai"]
    assert all(m in PRECOS_PADRAO for m in catalogo["anthropic"])


def test_catalogo_incorpora_precos_cadastrados_no_painel():
    """Quem cadastra um preço novo ganha o modelo na tela sem que ninguém toque no frontend."""
    from sdr_shared.ports.factory import catalogo_de_modelos

    c = catalogo_de_modelos({"claude-opus-9": (1.0, 2.0, 0.0, 0.0), "gpt-7-nova": (1.0, 2.0, 0.0, 0.0)})
    assert "claude-opus-9" in c["anthropic"] and "gpt-7-nova" in c["openai"]
