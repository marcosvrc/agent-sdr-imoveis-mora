"""Seed determinístico e cenários obrigatórios (seções 9 e 14).

O teste que importa aqui não é "gerou 100 leads": é **aplicar duas vezes deixa exatamente a mesma
base**. Um seed que duplica na segunda execução transforma todo teste seguinte numa investigação
sobre quantas cópias existem.
"""
from datetime import UTC, datetime

import pytest

from sdr_crm.db.connection import leitura
from sdr_crm.seed.aplicar import aplicar
from sdr_crm.seed.gerar import Plano

PLANO = Plano(seed=42, referencia=datetime(2026, 9, 17, 12, tzinfo=UTC), dataset_id="teste")

ESPERADO = {"users": 4, "properties": 50, "leads": 100, "opportunities": 120,
            "interactions": 300, "visits": 20, "tasks": 30, "handoffs": 10}


@pytest.fixture
def semeado(limpo):
    return aplicar(PLANO)


def _contar(tabela: str) -> int:
    with leitura() as conn:
        return conn.execute(f"SELECT count(*) AS n FROM {tabela}").fetchone()["n"]


def test_contagens_batem_com_a_especificacao(semeado):
    for tabela, quantos in ESPERADO.items():
        assert _contar(tabela) == quantos, tabela


def test_distribuicao_do_funil(semeado):
    with leitura() as conn:
        por_estagio = {x["stage"]: x["n"] for x in conn.execute(
            "SELECT stage, count(*) AS n FROM opportunities GROUP BY stage").fetchall()}
    assert por_estagio == {"new": 20, "in_service": 25, "qualified": 25, "visit_scheduled": 15,
                           "negotiation": 15, "won": 10, "lost": 10}


def test_aplicar_duas_vezes_nao_duplica_e_mantem_os_ids(semeado):
    with leitura() as conn:
        antes = [str(x["id"]) for x in conn.execute(
            "SELECT id FROM leads ORDER BY id").fetchall()]
    aplicar(PLANO)
    with leitura() as conn:
        depois = [str(x["id"]) for x in conn.execute(
            "SELECT id FROM leads ORDER BY id").fetchall()]
    assert antes == depois
    for tabela, quantos in ESPERADO.items():
        assert _contar(tabela) == quantos, tabela


def test_mesmos_parametros_geram_os_mesmos_identificadores():
    """Sem tocar no banco: o gerador tem de ser puro nos dois parâmetros."""
    from sdr_crm.seed import gerar
    a = gerar.leads(PLANO)
    b = gerar.leads(Plano(seed=42, referencia=PLANO.referencia, dataset_id="outro"))
    assert [x["id"] for x in a] == [x["id"] for x in b]
    assert [x["created_at"] for x in a] == [x["created_at"] for x in b]

    outro = gerar.leads(Plano(seed=43, referencia=PLANO.referencia, dataset_id="teste"))
    assert [x["id"] for x in a] != [x["id"] for x in outro]


def test_15_visit_scheduled_tem_visita_confirmada_e_as_outras_5_sao_solicitadas(semeado):
    with leitura() as conn:
        confirmadas = conn.execute(
            """SELECT count(*) AS n FROM visits v JOIN opportunities o ON o.id = v.opportunity_id
                WHERE v.status = 'confirmed' AND o.stage = 'visit_scheduled'""").fetchone()["n"]
        solicitadas = conn.execute(
            "SELECT count(*) AS n FROM visits WHERE status = 'requested'").fetchone()["n"]
    assert confirmadas == 15
    assert solicitadas == 5


def test_encerradas_nao_tem_visita_futura_ativa(semeado):
    with leitura() as conn:
        n = conn.execute(
            """SELECT count(*) AS n FROM visits v
                 JOIN opportunities o ON o.id = v.opportunity_id
                 JOIN availability_slots s ON s.id = v.slot_id
                WHERE o.stage IN ('won','lost') AND v.status IN ('requested','confirmed')
                  AND s.starts_at > now()""").fetchone()["n"]
    assert n == 0


@pytest.mark.parametrize(("nome", "sql"), [
    ("orçamento ausente",
     "SELECT count(*) FROM preferences WHERE budget_max_cents IS NULL"),
    ("contato bloqueado",
     "SELECT count(*) FROM leads WHERE contact_policy = 'blocked'"),
    ("lead arquivado",
     "SELECT count(*) FROM leads WHERE archived_at IS NOT NULL"),
    ("imóvel indisponível",
     "SELECT count(*) FROM properties WHERE status = 'unavailable'"),
    ("total mensal desconhecido",
     "SELECT count(*) FROM properties WHERE purpose = 'rent' AND condo_monthly_cents IS NULL"),
    ("atendimento humano",
     "SELECT count(*) FROM opportunities WHERE atendimento = 'human'"),
    ("tentativa de prompt injection",
     "SELECT count(*) FROM properties WHERE description ILIKE '%ignore as instruções%'"),
    ("investidor com duas oportunidades",
     """SELECT count(*) FROM (SELECT lead_id FROM opportunities GROUP BY lead_id
                               HAVING count(DISTINCT purpose) = 2) t"""),
    ("aluguel até R$ 3.000 de custo total",
     """SELECT count(*) FROM properties WHERE purpose = 'rent'
         AND condo_monthly_cents IS NOT NULL
         AND base_price_cents + condo_monthly_cents + coalesce(property_tax_monthly_cents,0)
             + coalesce(other_monthly_cents,0) <= 300000"""),
    ("compra com três quartos",
     "SELECT count(*) FROM properties WHERE purpose = 'buy' AND bedrooms = 3"),
])
def test_fixtures_obrigatorias_existem(semeado, nome, sql):
    with leitura() as conn:
        n = next(iter(conn.execute(sql).fetchone().values()))
    assert n >= 1, f"fixture ausente: {nome}"


def test_horarios_em_disputa_existem(semeado):
    """Dois horários do mesmo imóvel no mesmo instante, com corretores diferentes: é o cenário que
    permite testar duas confirmações concorrentes sem fabricar dado no meio do teste."""
    with leitura() as conn:
        n = conn.execute(
            """SELECT count(*) AS n FROM (
                   SELECT property_id, starts_at FROM availability_slots
                    GROUP BY property_id, starts_at HAVING count(*) > 1) t""").fetchone()["n"]
    assert n >= 1


def test_nenhum_follow_up_para_contato_bloqueado(semeado):
    """A massa não pode violar a própria regra de negócio: um `follow_up` semeado num lead
    bloqueado faria o primeiro teste de regressão falhar sem existir bug nenhum no código."""
    with leitura() as conn:
        n = conn.execute(
            """SELECT count(*) AS n FROM tasks t
                 JOIN opportunities o ON o.id = t.opportunity_id
                 JOIN leads l ON l.id = o.lead_id
                WHERE t.kind = 'follow_up' AND l.contact_policy = 'blocked'""").fetchone()["n"]
    assert n == 0


def test_tudo_e_sintetico_e_sem_dado_real(semeado):
    with leitura() as conn:
        assert conn.execute("SELECT count(*) AS n FROM leads WHERE NOT synthetic").fetchone()["n"] == 0
        fora = conn.execute(
            "SELECT count(*) AS n FROM leads WHERE email NOT LIKE '%@example.com'").fetchone()["n"]
        assert fora == 0
        # Telefone nulo na base comum: só os dois do cenário de conflito têm número.
        com_telefone = conn.execute(
            "SELECT count(*) AS n FROM leads WHERE phone_e164 IS NOT NULL").fetchone()["n"]
        assert com_telefone == 2
