"""Seed determinístico e cenários obrigatórios (seções 9 e 14).

O teste que importa aqui não é "gerou 100 leads": é **aplicar duas vezes deixa exatamente a mesma
base**. Um seed que duplica na segunda execução transforma todo teste seguinte numa investigação
sobre quantas cópias existem.
"""
from datetime import UTC, datetime

import pytest

from sdr_crm.db.connection import leitura
from sdr_crm.seed.aplicar import aplicar
from sdr_crm.seed import gerar
from sdr_crm.seed.gerar import Plano, ler_acervo, ler_equipe, usuarios

PLANO = Plano(seed=42, referencia=datetime(2026, 9, 17, 12, tzinfo=UTC), dataset_id="teste")

# Nada de literal aqui: cada número sai da mesma fonte que o seed usa — o acervo e a equipe vêm de
# arquivo, os volumes são constantes do gerador. Um 200 fixo transformaria "o acervo mudou" em "o
# seed quebrou", e foi exatamente o que aconteceu quando entraram os imóveis comerciais.
VISITAS = dict(gerar.ESTAGIOS)["visit_scheduled"] + gerar.VISITAS_SOLICITADAS
ESPERADO = {"users": len(usuarios(PLANO)), "properties": len(ler_acervo()), "leads": gerar.LEADS,
            "opportunities": gerar.OPORTUNIDADES, "interactions": gerar.INTERACOES,
            "visits": VISITAS, "tasks": gerar.TAREFAS, "handoffs": gerar.HANDOFFS}


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
    assert por_estagio == dict(gerar.ESTAGIOS)


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


def test_toda_visit_scheduled_tem_visita_confirmada_e_as_qualified_ficam_solicitadas(semeado):
    with leitura() as conn:
        confirmadas = conn.execute(
            """SELECT count(*) AS n FROM visits v JOIN opportunities o ON o.id = v.opportunity_id
                WHERE v.status = 'confirmed' AND o.stage = 'visit_scheduled'""").fetchone()["n"]
        solicitadas = conn.execute(
            "SELECT count(*) AS n FROM visits WHERE status = 'requested'").fetchone()["n"]
    assert confirmadas == dict(gerar.ESTAGIOS)["visit_scheduled"]
    assert solicitadas == gerar.VISITAS_SOLICITADAS


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


def test_a_equipe_do_arquivo_virou_usuario_do_crm(semeado):
    """O vínculo entre os dois sistemas é o e-mail (data/equipe/README.md). Se a equipe do arquivo
    não existir como `users` aqui, `semear_corretores.py --vincular-crm` não casa com ninguém e o
    encaminhamento sobe sem destinatário — falha silenciosa, do tipo que só aparece na demonstração.
    """
    equipe = ler_equipe()
    assert equipe, "data/equipe/corretores.json ausente ou vazio"
    with leitura() as conn:
        emails = {r["email"] for r in conn.execute("SELECT email FROM users").fetchall()}
    assert {x["email"] for x in equipe} <= emails


def test_a_carteira_se_espalha_pela_equipe_inteira(semeado):
    """A massa maior existe para mostrar distribuição. Toda oportunidade em três donos seria o
    mesmo dado de antes, com mais linhas."""
    with leitura() as conn:
        donos = conn.execute(
            "SELECT count(DISTINCT owner_id) AS n FROM opportunities").fetchone()["n"]
    assert donos >= 20


def test_reset_apaga_tambem_o_que_foi_criado_em_uso_sobre_o_lote(semeado):
    """A Mora marca visita num horário do seed com `dataset_id` nulo. O reset apagava só o lote e
    morria em ForeignKeyViolation (visits → availability_slots) — depois de qualquer uso real."""
    from sdr_crm.db.connection import transacao
    from sdr_crm.seed.__main__ import _resetar
    with transacao() as conn:
        base = conn.execute("""SELECT s.id AS slot, s.property_id AS imovel, o.id AS oportunidade
                                 FROM availability_slots s, opportunities o
                                WHERE s.dataset_id = 'teste' AND o.dataset_id = 'teste'
                                  AND NOT EXISTS (SELECT 1 FROM visits v WHERE v.slot_id = s.id)
                                LIMIT 1""").fetchone()
        conn.execute("""INSERT INTO visits (opportunity_id, property_id, slot_id, status)
                        VALUES (%s, %s, %s, 'requested')""",
                     (base["oportunidade"], base["imovel"], base["slot"]))
    apagados = _resetar("teste")
    assert apagados["visits"] == VISITAS + 1
    assert _contar("visits") == 0 and _contar("availability_slots") == 0
