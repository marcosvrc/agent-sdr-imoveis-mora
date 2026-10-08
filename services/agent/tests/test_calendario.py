"""Agenda do corretor: disponibilidade real, double-booking e resiliência quando o Google falha.

A regra que atravessa tudo: nada aqui pode fazer o cliente perder a visita. Google fora do ar,
token revogado, credencial ausente — a visita é marcada mesmo assim, só não vai para fora.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sdr_shared.db import CorretorRepository, LeadRepository, VisitaRepository, get_pool
from sdr_shared.models import Corretor, Lead

from agent.tools.agenda import HorarioOcupado, agendar, listar_horarios


@pytest.fixture(autouse=True)
def cenario():
    with get_pool().connection() as c:
        c.execute("DELETE FROM visitas")
        c.execute("DELETE FROM notificacoes")
    CorretorRepository().upsert(Corretor(id="cor_ana", nome="Ana Souza", regioes=["zona_sul"], ativo=True))
    LeadRepository().upsert(Lead(id="l1", nome="Marcos"))
    LeadRepository().upsert(Lead(id="l2", nome="Paula"))


def _primeiro_slot() -> datetime:
    return listar_horarios()[0]


# ---------------------------------------------------------------- grade interna

def test_horario_ja_marcado_some_da_oferta():
    slot = _primeiro_slot()
    agendar("l1", None, slot, corretor_id="cor_ana")
    assert slot not in listar_horarios(), "oferecer um horário já tomado é prometer o que não temos"


def test_dois_clientes_nao_marcam_o_mesmo_horario():
    """A corrida real: os dois viram a mesma lista antes de qualquer um clicar."""
    slot = _primeiro_slot()
    agendar("l1", None, slot, corretor_id="cor_ana")
    with pytest.raises(HorarioOcupado):
        agendar("l2", None, slot, corretor_id="cor_ana")
    assert len(VisitaRepository().listar()) == 1


def test_a_visita_do_primeiro_cliente_permanece():
    slot = _primeiro_slot()
    agendar("l1", None, slot, corretor_id="cor_ana")
    try:
        agendar("l2", None, slot, corretor_id="cor_ana")
    except HorarioOcupado:
        pass
    assert VisitaRepository().listar()[0]["lead_id"] == "l1"


def test_ocupacao_do_corretor_considera_a_duracao():
    slot = _primeiro_slot()
    agendar("l1", None, slot, corretor_id="cor_ana")
    ocupacao = VisitaRepository().ocupacao_do_corretor("cor_ana", slot - timedelta(hours=1), slot + timedelta(hours=2))
    assert ocupacao == [(slot, slot + timedelta(minutes=60))]


def test_agenda_de_outro_corretor_nao_bloqueia():
    CorretorRepository().upsert(Corretor(id="cor_bruno", nome="Bruno Lima", regioes=["zona_oeste"], ativo=True))
    slot = _primeiro_slot()
    agendar("l1", None, slot, corretor_id="cor_ana")
    assert VisitaRepository().ocupacao_do_corretor("cor_bruno", slot, slot + timedelta(hours=2)) == []


# ---------------------------------------------------------------- calendário externo

class CalendarioFake:
    """Corretor com a manhã inteira comprometida no Google."""
    def __init__(self, ocupado_ate_hora=13, falha=False):
        self.ocupado_ate_hora, self.falha, self.eventos = ocupado_ate_hora, falha, []

    def ocupado(self, corretor_id, de, ate):
        if self.falha:
            raise RuntimeError("Google fora do ar")
        dia = de.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return [(dia + timedelta(days=d), dia + timedelta(days=d, hours=self.ocupado_ate_hora + 3)) for d in range(8)]

    def conectado(self, corretor_id):
        return True

    def criar_evento(self, corretor_id, **kw):
        if self.falha:
            raise RuntimeError("Google fora do ar")
        self.eventos.append(kw)
        return "evt_123"

    def cancelar_evento(self, corretor_id, evento_id):
        return None


def _usar(monkeypatch, cal):
    import sdr_shared.ports as ports
    import sdr_shared.ports.factory as f
    monkeypatch.setattr(ports, "get_calendario", lambda: cal)
    monkeypatch.setattr(f, "get_calendario", lambda: cal)


def test_compromisso_no_google_tira_o_horario_da_oferta(monkeypatch):
    _usar(monkeypatch, CalendarioFake(ocupado_ate_hora=13))
    horarios = listar_horarios(corretor_id="cor_ana")
    manha = [h for h in horarios if h.astimezone(timezone(timedelta(hours=-3))).hour == 10]
    assert manha == [], "o corretor tem a manhã ocupada no Google; não podemos oferecê-la"
    assert horarios, "a tarde continua disponível"


def test_sem_corretor_definido_usa_a_grade_da_equipe(monkeypatch):
    _usar(monkeypatch, CalendarioFake(ocupado_ate_hora=23))
    assert listar_horarios(), "sem corretor não há agenda pessoal a consultar"


def test_google_fora_do_ar_nao_esvazia_a_agenda(monkeypatch):
    """Falhar fechado aqui seria pior que o problema: nenhum horário ofertado, nenhuma visita marcada."""
    _usar(monkeypatch, CalendarioFake(falha=True))
    assert len(listar_horarios(corretor_id="cor_ana")) > 0


def test_visita_vira_evento_na_agenda_do_corretor(monkeypatch):
    cal = CalendarioFake(ocupado_ate_hora=0)
    _usar(monkeypatch, cal)
    LeadRepository().upsert(Lead(id="l1", nome="Marcos", email="marcos@exemplo.com"))
    slot = listar_horarios()[0]
    agendar("l1", "SP-0001", slot, corretor_id="cor_ana", titulo="Visita: Apto em Moema",
            local="Moema, São Paulo", email_cliente="marcos@exemplo.com")
    assert len(cal.eventos) == 1
    assert cal.eventos[0]["convidados"] == ["marcos@exemplo.com"], "o cliente recebe o convite"
    assert VisitaRepository().listar()[0].get("evento_externo_id") in ("evt_123", None)


def test_falha_do_google_nao_impede_a_visita(monkeypatch):
    _usar(monkeypatch, CalendarioFake(falha=True))
    slot = listar_horarios()[0]
    visita = agendar("l1", None, slot, corretor_id="cor_ana")
    assert visita is not None
    assert len(VisitaRepository().listar()) == 1, "o cliente não perde a visita porque o Google caiu"


def test_corretor_sem_agenda_conectada_segue_normal(monkeypatch):
    class SemConexao(CalendarioFake):
        def conectado(self, corretor_id):
            return False
    cal = SemConexao(ocupado_ate_hora=0)
    _usar(monkeypatch, cal)
    agendar("l1", None, listar_horarios()[0], corretor_id="cor_ana")
    assert cal.eventos == [] and len(VisitaRepository().listar()) == 1


# ---------------------------------------------------------------- clique repetido e corrida

def test_clique_repetido_no_mesmo_horario_devolve_a_visita_ja_marcada():
    """O cliente toca duas vezes no botão (ou o Telegram reentrega o callback): a segunda reserva
    é a MESMA visita. Antes, a revalidação contava a visita do próprio lead e respondia "esse
    horário acabou de ser pego" para quem tinha acabado de pegá-lo."""
    slot = _primeiro_slot()
    primeira = agendar("l1", None, slot, corretor_id="cor_ana")
    segunda = agendar("l1", None, slot, corretor_id="cor_ana")
    assert segunda.id == primeira.id
    assert len(VisitaRepository().listar()) == 1


def test_corrida_real_o_banco_decide(monkeypatch):
    """Os dois passaram pela revalidação ao mesmo tempo (aqui forçado: `slot_livre` diz sim aos
    dois). Sem índice único, os dois INSERTs entravam e o corretor ficava com duas visitas às 10h."""
    monkeypatch.setattr(VisitaRepository, "slot_livre", lambda self, *a, **k: True)
    slot = _primeiro_slot()
    agendar("l1", None, slot, corretor_id="cor_ana")
    with pytest.raises(HorarioOcupado):
        agendar("l2", None, slot, corretor_id="cor_ana")
    assert [v["lead_id"] for v in VisitaRepository().listar()] == ["l1"]


def test_corrida_sem_corretor_tambem_colide(monkeypatch):
    """Sem corretor, a visita é da grade da equipe — que já era tratada como uma agenda só. Num
    índice comum NULL não colide com NULL, e os dois passariam."""
    monkeypatch.setattr(VisitaRepository, "slot_livre", lambda self, *a, **k: True)
    slot = _primeiro_slot()
    agendar("l1", None, slot)
    with pytest.raises(HorarioOcupado):
        agendar("l2", None, slot)
    assert len(VisitaRepository().listar()) == 1


def test_visita_de_outro_imovel_no_mesmo_horario_nao_devolve_a_primeira():
    """Visita às 10h no imóvel A e pedido às 10h no imóvel B: devolvia a visita de A como se fosse
    a de B ("reservado"), e nada era gravado para B."""
    from sdr_shared.db import ImovelRepository
    from sdr_shared.models import Imovel
    for codigo in ("SP-CAL-A", "SP-CAL-B"):
        ImovelRepository().upsert(Imovel(id=codigo, tipo="apartamento", operacao="aluguel",
                                         cidade="São Paulo", regiao="zona_oeste", bairro="Pinheiros",
                                         quartos=2, area_m2=60.0, preco=3000.0, descricao="x"))
    slot = _primeiro_slot()
    primeira = agendar("l1", "SP-CAL-A", slot, corretor_id="cor_ana")
    try:
        segunda = agendar("l1", "SP-CAL-B", slot, corretor_id="cor_ana")
    except HorarioOcupado:
        return                                   # o corretor não está em dois lugares: recusa é honesta
    assert segunda.id != primeira.id and segunda.imovel_id == "SP-CAL-B"
