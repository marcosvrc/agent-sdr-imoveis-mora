"""Fallback entre provedores (ADR-0009): a queda de um provedor não pode virar turno perdido.

O caso que quase passou batido é o `with_structured_output`: a extração do cartão depende dele, e
é justamente o que o `Runnable.with_fallbacks` do LangChain NÃO expõe — por isso o wrapper próprio.
"""
import os

os.environ["SDR_PROFILE"] = "local"

import pytest  # noqa: E402

from sdr_shared.config import get_settings  # noqa: E402
from sdr_shared.ports.factory import ModeloComFallback  # noqa: E402


class Quebrado:
    """Provedor fora do ar: estoura em tudo."""

    def __init__(self):
        self.tentativas = 0

    def invoke(self, *a, **kw):
        self.tentativas += 1
        raise RuntimeError("provedor indisponível")

    def with_structured_output(self, schema, **kw):
        return Quebrado()


class Funciona:
    def __init__(self, resposta="ok"):
        self.resposta, self.tentativas = resposta, 0

    def invoke(self, *a, **kw):
        self.tentativas += 1
        return self.resposta

    def with_structured_output(self, schema, **kw):
        return Funciona(f"estruturado:{schema}")

    def bind(self, **kw):                    # atributo qualquer, para checar o proxy
        return "veio-do-primario"


def test_primario_respondendo_nao_toca_no_reserva():
    p, r = Funciona("resposta do primário"), Funciona("resposta do reserva")
    assert ModeloComFallback(p, r, "anthropic").invoke("oi") == "resposta do primário"
    assert r.tentativas == 0, "reserva só entra quando o primário falha"


def test_primario_caido_assume_o_reserva():
    p, r = Quebrado(), Funciona("resposta do reserva")
    assert ModeloComFallback(p, r, "anthropic").invoke("oi") == "resposta do reserva"
    assert p.tentativas == 1 and r.tentativas == 1


def test_os_dois_caidos_propaga_o_erro():
    """Sem reserva de pé, o erro sobe — o handler do agente já responde ao cliente com o fallback."""
    with pytest.raises(RuntimeError):
        ModeloComFallback(Quebrado(), Quebrado(), "anthropic").invoke("oi")


def test_structured_output_tambem_tem_fallback():
    """`_extrair` do qualificador usa with_structured_output; sem isto o fallback não valeria
    para a extração do cartão, que é metade das chamadas de LLM do sistema."""
    m = ModeloComFallback(Quebrado(), Funciona(), "anthropic").with_structured_output(dict)
    assert isinstance(m, ModeloComFallback)
    assert m.invoke("oi") == "estruturado:<class 'dict'>"


def test_atributos_desconhecidos_vao_para_o_primario():
    m = ModeloComFallback(Funciona(), Funciona(), "anthropic")
    assert m.bind(x=1) == "veio-do-primario"


def test_sem_fallback_configurado_devolve_o_modelo_puro(monkeypatch):
    """Comportamento padrão inalterado: sem SDR_LLM_PROVIDER_FALLBACK, nada muda."""
    import sdr_shared.ports.factory as f

    monkeypatch.setattr(f, "modo_do_agente", lambda: "normal")
    monkeypatch.setattr(f, "_construir", lambda provider, model, temp, papel: f"modelo:{provider}")
    monkeypatch.setenv("SDR_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("SDR_LLM_PROVIDER_FALLBACK", "")
    get_settings.cache_clear()
    assert f.get_chat_model("conversa") == "modelo:anthropic"


def test_fallback_configurado_envolve_os_dois_provedores(monkeypatch):
    import sdr_shared.ports.factory as f

    monkeypatch.setattr(f, "modo_do_agente", lambda: "normal")
    monkeypatch.setattr(f, "_construir", lambda provider, model, temp, papel: f"modelo:{provider}")
    monkeypatch.setenv("SDR_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("SDR_LLM_PROVIDER_FALLBACK", "openai")
    get_settings.cache_clear()
    m = f.get_chat_model("conversa")
    assert isinstance(m, ModeloComFallback)
    assert m._primario == "modelo:anthropic" and m._reserva == "modelo:openai"
    get_settings.cache_clear()


def test_reserva_igual_ao_primario_e_ignorada(monkeypatch):
    """Configuração sem sentido não vira duas chamadas ao mesmo provedor caído."""
    import sdr_shared.ports.factory as f

    monkeypatch.setattr(f, "modo_do_agente", lambda: "normal")
    monkeypatch.setattr(f, "_construir", lambda provider, model, temp, papel: f"modelo:{provider}")
    monkeypatch.setenv("SDR_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("SDR_LLM_PROVIDER_FALLBACK", "anthropic")
    get_settings.cache_clear()
    assert f.get_chat_model("conversa") == "modelo:anthropic"
    get_settings.cache_clear()


def test_uso_registra_o_provedor_que_realmente_atendeu():
    """Sem isto, uma chamada servida pelo reserva apareceria na governança no nome do primário."""
    from sdr_shared.governanca import callbacks_para

    assert callbacks_para("conversa", "anthropic")[0].provider == "anthropic"
    assert callbacks_para("conversa")[0].provider is None, "sem override, cai no provedor do .env"
