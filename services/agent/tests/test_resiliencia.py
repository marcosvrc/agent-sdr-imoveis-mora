"""O cliente nunca pode ficar esperando em silêncio: falha do modelo/grafo vira resposta + handoff."""
from sdr_shared.db import LeadRepository, MensagemRepository
from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
from sdr_shared.models import Estagio

from agent import handler as h
from test_cenarios import msg, ultima


def test_falha_do_grafo_responde_e_encaminha(infra, monkeypatch):
    broker, _ = infra

    class GrafoQuebrado:
        def invoke(self, *_a, **_kw):
            raise RuntimeError("modelo indisponível (simulado)")

    monkeypatch.setattr(h, "get_graph", lambda: GrafoQuebrado())
    h.processar(msg("lx", "Quero um apartamento na zona sul"))

    r = ultima(broker)
    assert "problema técnico" in r["texto"] and r["acao"] == "handoff"        # o cliente é avisado
    lead = LeadRepository().get("lx")
    assert lead.estagio == Estagio.HANDOFF                                    # e entra na fila de um humano
    saidas = [m for m in MensagemRepository().historico("lx") if m["direcao"] == "out"]
    assert saidas and saidas[-1]["meta"]["motivo"] == "falha_agente"          # fica registrado para auditoria


def test_worker_avisa_mesmo_se_processar_estourar(infra, monkeypatch):
    """Rede de segurança do broker: `ao_falhar` avisa o cliente quando nem o try interno pega o erro."""
    broker, _ = infra
    capturado = {}

    class BrokerFake:
        def consume(self, _topic, _handler, ao_falhar=None):
            capturado["ao_falhar"] = ao_falhar
        def publish(self, *_a, **_kw):
            pass

    monkeypatch.setattr("sdr_shared.ports.get_broker", lambda: BrokerFake())
    h.local_worker()
    assert capturado["ao_falhar"] is not None

    entrada = MensagemNormalizada(lead_id="ly", canal=Canal.WEB, identificador_canal="sess-ly",
                                  tipo=TipoMensagem.TEXTO, conteudo="oi")
    capturado["ao_falhar"](entrada.model_dump_json(), RuntimeError("boom"))
    r = ultima(broker, "outbound-web")
    assert "problema técnico" in r["texto"] and LeadRepository().get("ly").estagio == Estagio.HANDOFF


def test_broker_confirma_mensagem_com_erro(monkeypatch):
    """A mensagem com erro é confirmada (não reprocessa em loop) e o callback de falha é acionado."""
    from sdr_shared.adapters.local import broker as mod

    eventos = []

    class RedisFake:
        def xgroup_create(self, *_a, **_kw): pass
        def xreadgroup(self, _g, _c, streams, **_kw):
            if "0" in streams.values(): return []               # retomada no boot: nada pendente
            if eventos: raise KeyboardInterrupt                 # um ciclo só
            return [("s", [("1-1", {"key": "k", "body": "corpo"})])]
        def xautoclaim(self, *_a, **_kw): return ["0-0", [], []]
        def lock(self, *_a, **_kw):
            class L:
                def __enter__(self): return None
                def __exit__(self, *a): return False
            return L()
        def xack(self, *a): eventos.append(("ack", *a))

    b = mod.RedisBroker.__new__(mod.RedisBroker)
    b._r = RedisFake()
    try:
        b.consume("inbound", lambda _body: (_ for _ in ()).throw(ValueError("falhou")),
                  ao_falhar=lambda body, erro: eventos.append(("falha", body, str(erro))))
    except KeyboardInterrupt:
        pass
    assert ("falha", "corpo", "falhou") in eventos
    assert any(e[0] == "ack" for e in eventos)
