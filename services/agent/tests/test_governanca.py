"""Governança de LLM: cálculo de custo, registro de uso e degradação por orçamento."""
import pytest
from sdr_shared.db import UsoRepository, estado_do_orcamento, invalidar_cache_orcamento
from sdr_shared.governanca import custo_usd, normalizar


def test_normalizacao_de_modelo():
    assert normalizar("us.anthropic.claude-sonnet-4-5-20250929") == "claude-sonnet-4-5"
    assert normalizar("anthropic.claude-haiku-4-5") == "claude-haiku-4-5"
    assert normalizar("claude-sonnet-4-5") == "claude-sonnet-4-5"


def test_custo_por_modelo():
    # Sonnet 4.5: US$ 3 por 1M de entrada, US$ 15 por 1M de saída
    assert custo_usd("claude-sonnet-4-5", entrada=1_000_000, saida=0) == 3.0
    assert custo_usd("claude-sonnet-4-5", entrada=0, saida=1_000_000) == 15.0
    assert custo_usd("anthropic.claude-haiku-4-5", entrada=500_000, saida=100_000) == pytest.approx(1.0)
    assert custo_usd("claude-sonnet-4-5", cache_leitura=1_000_000) == 0.30
    assert custo_usd("modelo-que-nao-existe", entrada=1_000_000) == 0.0          # desconhecido não inventa custo
    # preço sobrescrito pelo painel vence o padrão
    assert custo_usd("claude-sonnet-4-5", entrada=1_000_000, tabela={"claude-sonnet-4-5": [9, 9, 0, 0]}) == 9.0


def _uso(repo, **kw):
    base = dict(lead_id="l1", no="qualificador", papel="conversa", provider="anthropic", modelo="claude-sonnet-4-5",
                entrada=1000, saida=200, cache_escrita=0, cache_leitura=0, custo=0.006, latencia_ms=800, erro=None)
    repo.registrar(**{**base, **kw})


def test_registro_e_resumo(db_limpo):
    repo = UsoRepository()
    _uso(repo)
    _uso(repo, no="consultor", modelo="claude-haiku-4-5", papel="roteamento", custo=0.002, entrada=500, saida=50)
    r = repo.resumo(dias=7)
    assert r["kpis"]["chamadas"]["atual"] == 2
    assert r["kpis"]["tokens"]["atual"] == 1750 and r["kpis"]["custo"]["atual"] == pytest.approx(0.008)
    assert r["kpis"]["leads"]["atual"] == 1 and r["kpis"]["custo_por_lead"]["atual"] == pytest.approx(0.008)
    assert {m["chave"] for m in r["por_modelo"]} == {"claude-sonnet-4-5", "claude-haiku-4-5"}
    assert {n["chave"] for n in r["por_no"]} == {"qualificador", "consultor"}
    assert len(r["serie"]) == 7 and r["serie"][-1]["custo"] == pytest.approx(0.008)
    assert r["recentes"][0]["modelo"] in ("claude-sonnet-4-5", "claude-haiku-4-5")


def test_degradacao_por_orcamento(db_limpo):
    repo = UsoRepository()
    repo.salvar_limites({"orcamento_mensal_usd": 1.0, "teto_tokens_dia": 0, "alerta_pct": 80,
                         "acao_ao_estourar": "degradar", "cotacao_brl": 5.12})
    invalidar_cache_orcamento()
    assert estado_do_orcamento(0)["modo"] == "normal"

    _uso(repo, custo=0.85)                                    # 85% → alerta, mas ainda normal
    invalidar_cache_orcamento()
    e = estado_do_orcamento(0)
    assert e["em_alerta"] and not e["estourado"] and e["modo"] == "normal"

    _uso(repo, custo=0.30)                                    # 115% → degrada para o modelo barato
    invalidar_cache_orcamento()
    assert estado_do_orcamento(0)["modo"] == "degradado"

    _uso(repo, custo=0.50)                                    # 165% → teto duro: entrega ao corretor
    invalidar_cache_orcamento()
    assert estado_do_orcamento(0)["modo"] == "bloqueado"


def test_teto_de_tokens_diario(db_limpo):
    repo = UsoRepository()
    repo.salvar_limites({"orcamento_mensal_usd": 0, "teto_tokens_dia": 1000, "alerta_pct": 80,
                         "acao_ao_estourar": "bloquear", "cotacao_brl": 5.12})
    _uso(repo, entrada=900, saida=200, custo=0)               # 1100 > 1000
    invalidar_cache_orcamento()
    e = estado_do_orcamento(0)
    assert e["estourado"] and e["modo"] == "bloqueado" and e["tokens_hoje"] == 1100
