"""Cortes de dia/mês no fuso do negócio, índices das consultas quentes e saúde sem fantasma."""
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

os.environ.setdefault("SDR_DATABASE_DSN", "postgresql://sdr:sdr@localhost:5433/sdr_test")
from sdr_shared.db.guarda_teste import exigir_banco_de_teste; exigir_banco_de_teste()   # noqa: E702

from sdr_shared.db import UsoRepository, get_pool
from sdr_shared.db import governanca, monitoramento as mon, painel

SP = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def banco_em_utc(monkeypatch):
    """O Postgres do compose roda em UTC (padrão da imagem oficial); o de teste pode não rodar.
    Força a sessão em UTC para o teste valer igual nos dois — é em UTC que `em::date` erra."""
    @contextmanager
    def conn_utc():
        with get_pool().connection() as c:
            c.execute("SET TIME ZONE 'UTC'")
            try:
                yield c
            finally:
                c.execute("RESET TIME ZONE")
    monkeypatch.setattr(governanca, "_conn", conn_utc)
    monkeypatch.setattr(painel, "_conn", conn_utc)


# ------------------------------------------------------------------ B17: fuso

def test_cortes_de_dia_e_mes_sao_no_horario_de_brasilia():
    """31/10 às 22h em Brasília já é 01/11 em UTC: o orçamento do mês zerava às 21h do último dia
    e o teto diário de tokens virava às 21h todo dia."""
    agora = datetime(2026, 10, 31, 22, 0, tzinfo=SP).astimezone(timezone.utc)
    mes, hoje = governanca.cortes(agora)
    assert mes == datetime(2026, 10, 1, tzinfo=SP)
    assert hoje == datetime(2026, 10, 31, tzinfo=SP)


def test_serie_diaria_do_consumo_agrupa_pelo_dia_de_brasilia(banco_em_utc):
    """Uso às 22h de ontem (Brasília) é de ONTEM — em UTC já é hoje, e caía no dia errado."""
    with get_pool().connection() as c:
        c.execute("DELETE FROM uso_llm")
    ontem_sp = datetime.now(SP).date() - timedelta(days=1)
    em = datetime.combine(ontem_sp, datetime.min.time(), SP) + timedelta(hours=22)
    with get_pool().connection() as c:
        c.execute("""INSERT INTO uso_llm (em, provider, modelo, tokens_saida, custo_usd)
                     VALUES (%s, 'x', 'm', 123, 0)""", (em,))
    serie = {d["dia"]: d["saida"] for d in UsoRepository().resumo(dias=7)["serie"]}
    assert serie.get(ontem_sp.isoformat()) == 123, serie


def test_serie_do_painel_agrupa_pelo_dia_de_brasilia(banco_em_utc):
    from sdr_shared.db import LeadRepository, MetricasRepository
    from sdr_shared.models import Lead
    ontem_sp = datetime.now(SP).date() - timedelta(days=1)
    em = datetime.combine(ontem_sp, datetime.min.time(), SP) + timedelta(hours=22, minutes=30)
    LeadRepository().upsert(Lead(id="l_fuso_painel"))
    with get_pool().connection() as c:
        antes = {d["dia"]: d["leads"] for d in MetricasRepository().resumo(dias=7)["serie"]}
        c.execute("UPDATE leads SET criado_em = %s WHERE id = 'l_fuso_painel'", (em,))
    depois = {d["dia"]: d["leads"] for d in MetricasRepository().resumo(dias=7)["serie"]}
    with get_pool().connection() as c:
        c.execute("DELETE FROM leads WHERE id = 'l_fuso_painel'")
    assert depois[ontem_sp.isoformat()] == antes.get(ontem_sp.isoformat(), 0) + 1


# ------------------------------------------------------------------ B14: índices

@pytest.mark.parametrize("tabela,colunas", [
    ("eventos_navegacao", "session_id"),
    ("canais", "lead_id"),
    ("visitas", "lead_id"),
    ("leads", "corretor_id"),
    ("mensagens", "direcao, em"),
])
def test_consultas_quentes_tem_indice(tabela, colunas):
    """`imoveis_vistos` roda em todo turno do site filtrando `eventos_navegacao` por sessão; sem
    índice, cada turno varria a tabela inteira de cliques — que só cresce."""
    with get_pool().connection() as c:
        defs = [r["indexdef"] for r in c.execute(
            "SELECT indexdef FROM pg_indexes WHERE tablename = %s", (tabela,)).fetchall()]
    assert any(f"({colunas}" in d for d in defs), defs


# ------------------------------------------------------------------ B18: serviço aposentado

@pytest.fixture
def sem_batimentos():
    with get_pool().connection() as c:
        c.execute("DELETE FROM batimentos")
    yield
    with get_pool().connection() as c:
        c.execute("DELETE FROM batimentos")


def test_servico_desligado_ha_muito_tempo_nao_derruba_a_saude_para_sempre(sem_batimentos):
    """telegram-in bateu ponto uma vez e foi desligado (tiraram o token). O carimbo ficava lá e o
    /health respondia 503 para sempre — e o healthcheck que sempre falha é ignorado por todos."""
    mon.bater("telegram-in")
    with get_pool().connection() as c:
        c.execute("UPDATE batimentos SET em = now() - make_interval(secs => %s)",
                  (mon.ABANDONADO_S + 60,))
    assert mon.servicos_parados() == []
    linha = mon.batimentos()[0]
    assert linha["vivo"] is False and linha["abandonado"] is True, "a tela continua mostrando"


def test_servico_que_parou_agora_continua_derrubando_a_saude(sem_batimentos):
    mon.bater("agent")
    with get_pool().connection() as c:
        c.execute("UPDATE batimentos SET em = now() - make_interval(secs => %s)", (mon.PARADO_S + 30,))
    assert [p["servico"] for p in mon.servicos_parados()] == ["agent"]


def test_servico_que_sabe_que_nao_vai_rodar_tira_o_proprio_carimbo(sem_batimentos):
    mon.bater("telegram-in")
    mon.encerrar_batimento("telegram-in")
    assert mon.batimentos() == []
