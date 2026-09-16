"""O corretor precisa ficar sabendo. O agente promete ao cliente que alguém continua o atendimento."""
from datetime import datetime, timedelta, timezone

import pytest
from sdr_shared.db import CorretorRepository, LeadRepository, NotificacaoRepository, get_pool, notificar
from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
from sdr_shared.models import CartaoQualificacao, Corretor, Estagio, Intencao, Lead, Temperatura

from agent.scoring import calcular, respondeu_rapido


@pytest.fixture(autouse=True)
def limpa():
    with get_pool().connection() as c:
        c.execute("DELETE FROM notificacoes")
    # Os corretores existem de verdade no cadastro: desde que leads/visitas/notificações têm chave
    # estrangeira para `corretores`, um id inventado no teste não passa — que é exatamente a
    # proteção contra o lead atribuído a um corretor que não existe.
    # Cada um com sua região: um corretor "sem região" atende todas e passa na frente no
    # roteamento, o que mudaria o corretor escolhido nos testes de handoff por um detalhe de fixture.
    for cid, nome, regioes in (("cor_ana", "Ana Souza", ["zona_sul"]), ("cor_bruno", "Bruno Lima", ["zona_norte"])):
        CorretorRepository().upsert(Corretor(id=cid, nome=nome, regioes=regioes, ativo=True))


def _msg(lead_id: str, texto: str) -> MensagemNormalizada:
    return MensagemNormalizada(lead_id=lead_id, canal=Canal.WHATSAPP, identificador_canal="5511999990000",
                               conteudo=texto, tipo=TipoMensagem.TEXTO)


# ---------------------------------------------------------------- sinal de resposta rápida

def test_cliente_que_volta_logo_pontua():
    agora = datetime.now(timezone.utc)
    assert respondeu_rapido(agora - timedelta(minutes=2), agora)
    assert not respondeu_rapido(agora - timedelta(hours=3), agora)
    assert not respondeu_rapido(None, agora), "primeira mensagem não tem intervalo para medir"


def test_o_sinal_entra_no_score():
    lead = Lead(id="l", cartao=CartaoQualificacao(intencao=Intencao.COMPRA, regiao="zona_sul"))
    sem, _ = calcular(lead)
    com, _ = calcular(lead, respondeu_rapido=True)
    assert com - sem == 5


def test_o_sinal_chega_do_fluxo_real(infra):
    """Antes este parâmetro nunca era acionado — o teste existe para não voltar a ser código morto."""
    from agent.handler import processar
    processar(_msg("l_rapido", "quero um apartamento na zona sul"))
    antes = LeadRepository().get("l_rapido").score
    processar(_msg("l_rapido", "até 800 mil, 2 quartos, é urgente"))   # responde na sequência
    depois = LeadRepository().get("l_rapido")
    assert depois.score > antes and depois.temperatura == Temperatura.QUENTE


# ---------------------------------------------------------------- avisos

def test_handoff_avisa_o_corretor(infra):
    from agent.handler import processar
    processar(_msg("l_hand", "quero falar com um corretor"))
    avisos = NotificacaoRepository().listar()
    assert [a["tipo"] for a in avisos] == ["lead.encaminhado"]
    assert avisos[0]["corretor_id"] == "cor_ana" and avisos[0]["lead_id"] == "l_hand"


def test_cliente_que_responde_em_handoff_avisa_de_novo(infra):
    from agent.handler import processar
    LeadRepository().upsert(Lead(id="l_resp", estagio=Estagio.HANDOFF, corretor_id="cor_ana", nome="Marcos"))
    processar(_msg("l_resp", "consegue me mandar as fotos?"))
    avisos = NotificacaoRepository().listar()
    assert avisos[0]["tipo"] == "lead.respondeu"
    assert "fotos" in (avisos[0]["detalhe"] or ""), "o corretor vê do que se trata sem abrir a conversa"


def test_visita_agendada_avisa(infra):
    from agent.tools.agenda import agendar
    LeadRepository().upsert(Lead(id="l_vis", nome="Marcos"))
    inicio = datetime.now(timezone.utc) + timedelta(days=1)
    agendar("l_vis", None, inicio, corretor_id="cor_ana")
    avisos = NotificacaoRepository().listar()
    assert avisos[0]["tipo"] == "visita.agendada" and avisos[0]["corretor_id"] == "cor_ana"


def test_o_mesmo_fato_nao_vira_dois_avisos():
    for _ in range(3):
        notificar(tipo="visita.agendada", corretor_id="cor_ana", lead_id="l1", titulo="Visita marcada", chave="vis_1")
    assert len(NotificacaoRepository().listar()) == 1, "reprocessar a fila não pode encher o sino"


def test_leitura_zera_o_contador():
    repo = NotificacaoRepository()
    notificar(tipo="lead.encaminhado", corretor_id="cor_ana", lead_id="l1", titulo="Lead esperando", chave="a")
    notificar(tipo="lead.encaminhado", corretor_id="cor_ana", lead_id="l2", titulo="Outro lead", chave="b")
    assert repo.nao_lidas() == 2
    repo.marcar_lida(repo.listar()[0]["id"])
    assert repo.nao_lidas() == 1
    assert repo.marcar_todas() == 1 and repo.nao_lidas() == 0


def test_corretor_ve_os_seus_e_os_sem_dono():
    repo = NotificacaoRepository()
    notificar(tipo="lead.encaminhado", corretor_id="cor_ana", lead_id="l1", titulo="Da Ana", chave="a")
    notificar(tipo="lead.encaminhado", corretor_id="cor_bruno", lead_id="l2", titulo="Do Bruno", chave="b")
    notificar(tipo="lead.encaminhado", corretor_id=None, lead_id="l3", titulo="Sem dono", chave="c")
    titulos = {n["titulo"] for n in repo.listar("cor_ana")}
    assert titulos == {"Da Ana", "Sem dono"}, "lead sem responsável é problema de todo mundo"


def test_falha_ao_avisar_nao_derruba_o_atendimento(monkeypatch):
    import sdr_shared.db.notificacoes as mod
    monkeypatch.setattr(mod, "_conn", lambda: (_ for _ in ()).throw(RuntimeError("banco fora")))
    notificar(tipo="lead.encaminhado", lead_id="l1", titulo="não vai gravar")      # não deve levantar
