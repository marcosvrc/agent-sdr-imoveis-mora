"""Como o agendador usa (e deixa de usar) o CRM.

A verdade da integração — pedido é `requested`, oportunidade não vai para `visit_scheduled` — é
provada contra o CRM real em `shared/tests/test_visitas_crm.py`. Aqui fica só a ligação: de onde
vem a grade de horários, o que sobrevive no estado entre os dois turnos, e o que acontece quando o
CRM não responde. São dublês porque é isso que está sob prova.
"""
from datetime import UTC, datetime, timedelta

import pytest
from sdr_shared.crm import Horario
from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
from sdr_shared.models import Estagio, ImovelCard, Intencao, Lead

from agent.nodes import agendador


def entrada(texto: str) -> MensagemNormalizada:
    return MensagemNormalizada(lead_id="lead-ag", canal=Canal.WEB, tipo=TipoMensagem.TEXTO,
                               identificador_canal="s", conteudo=texto)


@pytest.fixture
def lead_no_banco():
    """A reserva grava uma visita de verdade no banco da Mora, e visita tem chave estrangeira para
    lead. Sem isto os testes de escolha falham no banco, e não no comportamento."""
    from sdr_shared.db import LeadRepository
    lead = Lead(id="lead-ag", nome="Cliente", estagio=Estagio.QUALIFICADO)
    lead.cartao.intencao = Intencao.ALUGUEL
    return LeadRepository().upsert(lead)


def estado(texto: str, **extra) -> dict:
    lead = Lead(id="lead-ag", nome="Cliente", estagio=Estagio.QUALIFICADO)
    lead.cartao.intencao = Intencao.ALUGUEL
    card = ImovelCard(id="SP-0001", titulo="Apartamento 2q · Pinheiros", preco=3000.0,
                      foto=None, motivo="perto do metrô")
    return {"lead": lead, "entrada": entrada(texto), "messages": [], "saltos": 0,
            "imoveis_sugeridos": [card], **extra}


@pytest.fixture
def grade(monkeypatch):
    """Horários do CRM, com `slot_id` — que é o que distingue de uma grade da agenda do corretor."""
    base = (datetime.now(UTC) + timedelta(days=2)).replace(hour=14, minute=0, second=0,
                                                           microsecond=0)
    horarios = [Horario(inicio=base + timedelta(days=i), slot_id=f"slot-{i}") for i in range(3)]
    monkeypatch.setattr(agendador, "horarios_do_imovel", lambda codigo, *a, **k: horarios)
    return horarios


@pytest.fixture
def pedidos(monkeypatch):
    registrados = []
    monkeypatch.setattr(agendador, "pedir_visita",
                        lambda lead, codigo, slot, **k: registrados.append((codigo, slot)) or True)
    return registrados


# --------------------------------------------------------------------------- de onde vem a grade

def test_com_imovel_a_grade_vem_do_crm(infra, grade, monkeypatch):
    """Horário de visita a um imóvel é dado comercial da imobiliária: quem sabe é o CRM."""
    monkeypatch.setattr(agendador, "listar_horarios",
                        lambda **k: pytest.fail("não devia ter usado a agenda do corretor"))
    out = agendador.run(estado("quero visitar"))
    assert out["horarios_oferecidos"] == [h.inicio.isoformat() for h in grade]
    assert out["slots_crm"] == {h.inicio.isoformat(): h.slot_id for h in grade}


def test_sem_resposta_do_crm_cai_na_agenda_do_corretor(infra, monkeypatch):
    """Lista vazia é "não sei", nunca "não há". Recusar visita por falha de integração seria
    inventar indisponibilidade — e o agendamento tem de funcionar sem CRM nenhum."""
    monkeypatch.setattr(agendador, "horarios_do_imovel", lambda *a, **k: [])
    out = agendador.run(estado("quero visitar"))
    assert out["horarios_oferecidos"], "a oferta não pode ficar vazia"
    assert out["slots_crm"] == {}, "sem slot do CRM não há o que pedir depois"


# --------------------------------------------------------------------------- do turno 1 ao turno 2

def test_o_slot_escolhido_vira_o_pedido(infra, grade, pedidos, lead_no_banco):
    """O `slot_id` precisa atravessar os dois turnos: a grade é oferecida num, a escolha vem no
    outro. Sem isso, o pedido nasceria sem horário e o CRM o recusaria."""
    escolhido = grade[1]
    out = agendador.run(estado(f"slot:{escolhido.inicio.isoformat()}",
                               horarios_oferecidos=[h.inicio.isoformat() for h in grade],
                               slots_crm={h.inicio.isoformat(): h.slot_id for h in grade}))
    assert pedidos == [("SP-0001", escolhido.slot_id)]
    assert out["slots_crm"] == {}, "a grade não pode sobrar para o próximo agendamento"


def test_horario_da_agenda_do_corretor_nao_inventa_slot(infra, pedidos, monkeypatch, lead_no_banco):
    """Quando a grade veio do corretor não há `slot_id`. A reserva da Mora vale do mesmo jeito; o
    pedido fica sem onde ser pendurado, e inventar um identificador seria pior que não pedir."""
    monkeypatch.setattr(agendador, "horarios_do_imovel", lambda *a, **k: [])
    quando = (datetime.now(UTC) + timedelta(days=2)).replace(hour=14, minute=0, second=0,
                                                             microsecond=0)
    agendador.run(estado(f"slot:{quando.isoformat()}",
                         horarios_oferecidos=[quando.isoformat()], slots_crm={}))
    assert pedidos == [("SP-0001", None)]


def test_falha_do_pedido_nao_desfaz_a_reserva(infra, grade, monkeypatch, lead_no_banco):
    """O cliente tem o horário e o corretor recebe a notificação da Mora de qualquer jeito. O que
    se perde é o pedido aparecer no painel do CRM — ruim, e muito menos ruim que derrubar o
    atendimento por causa disso."""
    def recusar(*a, **k):
        return False
    monkeypatch.setattr(agendador, "pedir_visita", recusar)
    escolhido = grade[0]
    out = agendador.run(estado(f"slot:{escolhido.inicio.isoformat()}",
                               horarios_oferecidos=[h.inicio.isoformat() for h in grade],
                               slots_crm={h.inicio.isoformat(): h.slot_id for h in grade}))
    assert out["resposta"].texto
    assert out["lead"].estagio == Estagio.AGENDADO


def test_erro_do_crm_nao_derruba_o_turno(infra, grade, monkeypatch, lead_no_banco):
    def explodir(*a, **k):
        raise RuntimeError("CRM caiu no meio")
    monkeypatch.setattr(agendador, "pedir_visita", explodir)
    escolhido = grade[0]
    with pytest.raises(RuntimeError):
        # O módulo de visitas engole a própria falha; aqui o dublê levanta de propósito para
        # documentar que o nó NÃO tem try próprio — a garantia mora em `sdr_shared.crm.visitas`,
        # e este teste existe para que mover essa responsabilidade não passe despercebido.
        agendador.run(estado(f"slot:{escolhido.inicio.isoformat()}",
                             horarios_oferecidos=[h.inicio.isoformat() for h in grade],
                             slots_crm={h.inicio.isoformat(): h.slot_id for h in grade}))
