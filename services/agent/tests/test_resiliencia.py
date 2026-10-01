"""O cliente nunca pode ficar esperando em silêncio: falha do modelo/grafo vira resposta + handoff."""
import pytest
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


def test_sem_barramento_o_turno_falha_antes_de_comecar(infra, monkeypatch):
    """Sem Redis, o despacho estourava no FIM: modelo chamado, lead gravado, histórico registrado —
    e a resposta perdida em silêncio. Agora um PING no início recusa o turno, alto e barato."""
    import agent.dispatch as d
    from agent.handler import processar
    from sdr_shared.db import LeadRepository
    from sdr_shared.messaging import Canal, MensagemNormalizada

    class Morto:
        def publish(self, *a, **k): raise AssertionError("não devia chegar ao despacho")
        def ping(self): raise ConnectionError("redis fora")
    monkeypatch.setattr(d, "get_broker", lambda: Morto())
    with pytest.raises(RuntimeError, match="barramento"):
        processar(MensagemNormalizada(lead_id="l-sem-redis", canal=Canal.WEB, identificador_canal="s",
                                      conteudo="oi"))
    assert LeadRepository().get("l-sem-redis") is None, "nada foi gravado para um turno que não aconteceu"


def test_resumidor_sem_historico_nao_chama_o_modelo(monkeypatch):
    """Briefing de conversa vazia não existe — e pedi-lo ao modelo é pior que não pedir.

    A Anthropic recusa (400: só sobra o system), o provedor reserva aceita e devolve um resumo
    inventado, que chega à tela do corretor indistinguível de um briefing real. O caso não é
    hipotético: quando o turno falha, o estágio muda, o evento de briefing sai e o checkpoint está
    vazio.
    """
    from agent.nodes import resumidor
    from sdr_shared.models import Lead

    chamou = []
    monkeypatch.setattr(resumidor, "llm_analise", lambda: chamou.append(1))
    lead = Lead(id="l_vazio", nome="Sem Conversa")
    saida = resumidor.run({"lead": lead, "messages": []})
    assert chamou == [], "modelo não pode ser chamado sem nada para resumir"
    assert saida["lead"].resumo is None and saida["lead"].analisado_em is None


def test_resumidor_manda_a_conversa_como_transcricao_terminando_no_usuario(monkeypatch):
    """Um lead real: a conversa terminava na fala da Mora, a Anthropic a tratou como o início da
    resposta, o modelo emendou três tokens e o briefing do corretor saiu como o texto de reserva
    do filtro ("Deixa eu te ajudar direito…")."""
    from langchain_core.messages import AIMessage, HumanMessage
    from agent.nodes import resumidor
    from sdr_shared.models import Lead

    pedidos = []

    class _Falso:
        def invoke(self, msgs):
            pedidos.append(msgs)
            return AIMessage(content="- Busca aluguel em Pinheiros até R$ 5 mil.")

        def with_structured_output(self, _):
            return self

    monkeypatch.setattr(resumidor, "llm_analise", lambda: _Falso())
    monkeypatch.setattr(resumidor, "notificar", lambda **k: None)
    historico = [HumanMessage(content="quero alugar em Pinheiros"),
                 AIMessage(content="Qual o valor máximo?"),
                 HumanMessage(content="até 5 mil"),
                 AIMessage(content="Encontrei duas opções para você.")]
    saida = resumidor.run({"lead": Lead(id="l_transcricao"), "messages": historico})

    for msgs in pedidos:                            # o briefing e a análise
        assert len(msgs) == 2 and isinstance(msgs[-1], HumanMessage), "tem de terminar no usuário"
        texto = msgs[-1].content
        assert "Cliente: quero alugar em Pinheiros" in texto and "Mora: Encontrei duas opções" in texto
    assert len(pedidos) == 2
    assert saida["lead"].resumo.startswith("- Busca aluguel")


def test_ciclo_do_scheduler_que_falha_nao_derruba_o_laco(monkeypatch):
    """O banco reiniciando debaixo do worker (`AdminShutdown`) encerrava o processo em silêncio, e
    o follow-up parava até alguém reparar no batimento parado."""
    from sdr_scheduler import local_worker

    class SchQuebrado:
        def vencidos(self): raise RuntimeError("terminating connection due to administrator command")

    class BrokerFake:
        def publish(self, *_a, **_kw): pass

    voltas = []
    monkeypatch.setattr(local_worker, "get_scheduler", lambda: SchQuebrado())
    monkeypatch.setattr(local_worker, "get_broker", lambda: BrokerFake())
    monkeypatch.setattr(local_worker, "iniciar_batimento", lambda *_a, **_kw: None)
    monkeypatch.setattr(local_worker, "configurar_log", lambda *_a, **_kw: None)

    def dormir(_s):
        voltas.append(1)
        if len(voltas) >= 3:
            raise KeyboardInterrupt                      # só para encerrar o teste
    monkeypatch.setattr(local_worker.time, "sleep", dormir)

    with pytest.raises(KeyboardInterrupt):
        local_worker.main()
    assert len(voltas) == 3, "o laço tem de continuar depois do ciclo que falhou"
