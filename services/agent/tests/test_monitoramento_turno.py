"""O turno precisa se registrar sozinho (ADR-0011) — inclusive quando morre cedo.

Sem isto a taxa de falha ficaria eternamente em zero: só o caminho feliz apareceria na tela, que é
exatamente o modo de falha que não se percebe.
"""
from sdr_shared.db import get_pool
from sdr_shared.messaging import MensagemNormalizada, Canal, TipoMensagem
from sdr_shared.models import Estagio, Lead
from sdr_shared.db import LeadRepository
from agent.handler import processar


def msg(lead, texto, canal=Canal.WHATSAPP):
    return MensagemNormalizada(lead_id=lead, canal=canal, identificador_canal="5511999990000",
                               tipo=TipoMensagem.TEXTO, conteudo=texto, meta={})


def turnos():
    with get_pool().connection() as c:
        return c.execute("SELECT * FROM turnos ORDER BY id").fetchall()


def limpar():
    from agent.guardrails import vazao
    vazao.resetar()          # o limitador é estado de processo: outros módulos já gastaram a janela
    with get_pool().connection() as c:
        c.execute("DELETE FROM turnos")


def test_turno_normal_grava_duracao_estagio_e_caminho(infra):
    limpar()
    processar(msg("l1", "quero um apartamento na zona sul"))
    (t,) = turnos()
    assert t["resultado"] == "ok" and t["canal"] == "whatsapp" and t["lead_id"] == "l1"
    assert t["duracao_ms"] >= 0
    assert t["estagio"] == str(Estagio.QUALIFICANDO.value)
    assert "supervisor" in t["nos"], "o caminho pelo grafo é o que explica um turno lento"


def test_turno_que_morre_em_handoff_tambem_conta(infra):
    """Saída antecipada é turno: o cliente esperou, então entra na conta."""
    limpar()
    LeadRepository().upsert(Lead(id="l1", nome="Marcos", telefone="5511999990000", estagio=Estagio.HANDOFF))
    processar(msg("l1", "alguma novidade?"))
    (t,) = turnos()
    assert t["resultado"] == "handoff" and t["nos"] == [], "não passou pelo grafo"


def test_falha_no_grafo_vira_turno_com_resultado_erro(infra, monkeypatch):
    limpar()
    import agent.handler as h

    class GrafoQuebrado:
        def invoke(self, *a, **k):
            raise RuntimeError("modelo fora do ar")

    monkeypatch.setattr(h, "get_graph", lambda: GrafoQuebrado())
    processar(msg("l1", "quero um apartamento"))
    (t,) = turnos()
    assert t["resultado"] == "erro", "é este número que a tela de saúde mostra como taxa de falha"
