"""Repositório de governança de LLM: registro de uso, agregações para o painel, limites e preços."""
import json
from datetime import datetime, timedelta, timezone

from .connection import get_pool

LIMITES_PADRAO = {
    "orcamento_mensal_usd": 50.0,      # teto de custo do mês (0 = sem teto)
    "teto_tokens_dia": 1_000_000,      # teto de tokens por dia (0 = sem teto)
    "alerta_pct": 80,                  # a partir daqui o painel alerta
    "acao_ao_estourar": "degradar",    # degradar | alertar | bloquear
    "cotacao_brl": 5.12,               # R$ por US$ (editável no painel)
}


def _conn():
    return get_pool().connection()


class UsoRepository:
    def registrar(self, *, lead_id: str | None, no: str | None, papel: str | None, provider: str, modelo: str,
                  entrada: int, saida: int, cache_escrita: int, cache_leitura: int, custo: float,
                  latencia_ms: int, erro: str | None) -> None:
        with _conn() as c:
            c.execute("""INSERT INTO uso_llm (lead_id, no, papel, provider, modelo, tokens_entrada, tokens_saida,
                                              tokens_cache_escrita, tokens_cache_leitura, custo_usd, latencia_ms, erro)
                         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                      (lead_id, no, papel, provider, modelo, entrada, saida, cache_escrita, cache_leitura,
                       custo, latencia_ms, erro))

    # ---- leitura para o painel ----
    def resumo(self, dias: int = 30) -> dict:
        agora = datetime.now(timezone.utc)
        ini, ini_ant = agora - timedelta(days=dias), agora - timedelta(days=2 * dias)
        mes = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        hoje = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        with _conn() as c:
            def periodo(a, b) -> dict:
                r = c.execute("""SELECT count(*) AS chamadas,
                                        coalesce(sum(tokens_entrada + tokens_saida + tokens_cache_escrita + tokens_cache_leitura),0) AS tokens,
                                        coalesce(sum(tokens_entrada),0) AS entrada, coalesce(sum(tokens_saida),0) AS saida,
                                        coalesce(sum(tokens_cache_leitura),0) AS cache_leitura,
                                        coalesce(sum(custo_usd),0) AS custo, coalesce(avg(latencia_ms),0) AS latencia,
                                        count(*) FILTER (WHERE erro IS NOT NULL) AS erros,
                                        count(DISTINCT lead_id) FILTER (WHERE lead_id IS NOT NULL) AS leads
                                 FROM uso_llm WHERE em >= %s AND em < %s""", (a, b)).fetchone()
                d = {k: (float(v) if k in ("custo", "latencia") else int(v)) for k, v in dict(r).items()}
                d["custo_por_lead"] = round(d["custo"] / d["leads"], 4) if d["leads"] else 0.0
                return d

            atual, anterior = periodo(ini, agora), periodo(ini_ant, ini)
            serie = c.execute("""WITH dias AS (SELECT generate_series((now() - make_interval(days => %(d)s - 1))::date, now()::date, '1 day')::date AS dia)
                                 SELECT d.dia,
                                        coalesce((SELECT sum(tokens_entrada + tokens_cache_leitura + tokens_cache_escrita) FROM uso_llm WHERE em::date = d.dia),0) AS entrada,
                                        coalesce((SELECT sum(tokens_saida) FROM uso_llm WHERE em::date = d.dia),0) AS saida,
                                        coalesce((SELECT sum(custo_usd) FROM uso_llm WHERE em::date = d.dia),0) AS custo
                                 FROM dias d ORDER BY d.dia""", {"d": dias}).fetchall()
            por = lambda campo: [dict(r) for r in c.execute(f"""
                SELECT {campo} AS chave, count(*) AS chamadas,
                       coalesce(sum(tokens_entrada + tokens_saida + tokens_cache_escrita + tokens_cache_leitura),0) AS tokens,
                       coalesce(sum(custo_usd),0) AS custo, coalesce(avg(latencia_ms),0) AS latencia
                FROM uso_llm WHERE em >= %s AND {campo} IS NOT NULL GROUP BY 1 ORDER BY custo DESC""", (ini,)).fetchall()]
            modelos, nos, papeis = por("modelo"), por("no"), por("papel")
            recentes = [dict(r) for r in c.execute("""
                SELECT id, em, lead_id, no, papel, modelo, tokens_entrada, tokens_saida, tokens_cache_leitura,
                       custo_usd, latencia_ms, erro
                FROM uso_llm ORDER BY em DESC LIMIT 60""").fetchall()]
            gasto_mes = float(c.execute("SELECT coalesce(sum(custo_usd),0) AS v FROM uso_llm WHERE em >= %s", (mes,)).fetchone()["v"])
            tokens_hoje = int(c.execute("""SELECT coalesce(sum(tokens_entrada + tokens_saida + tokens_cache_escrita + tokens_cache_leitura),0) AS v
                                           FROM uso_llm WHERE em >= %s""", (hoje,)).fetchone()["v"])

        limpar = lambda xs: [{**x, "custo": float(x["custo"]), "tokens": int(x["tokens"]), "latencia": float(x["latencia"])} for x in xs]
        return {
            "periodo_dias": dias, "gerado_em": agora.isoformat(),
            "kpis": {k: {"atual": atual[k], "anterior": anterior[k]} for k in atual},
            "serie": [{"dia": r["dia"].isoformat(), "entrada": int(r["entrada"]), "saida": int(r["saida"]), "custo": float(r["custo"])} for r in serie],
            "por_modelo": limpar(modelos), "por_no": limpar(nos), "por_papel": limpar(papeis),
            "recentes": [{**r, "em": r["em"].isoformat(), "custo_usd": float(r["custo_usd"])} for r in recentes],
            "consumo": {"gasto_mes_usd": round(gasto_mes, 4), "tokens_hoje": tokens_hoje},
        }

    def gasto_do_mes(self) -> float:
        mes = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        with _conn() as c:
            return float(c.execute("SELECT coalesce(sum(custo_usd),0) AS v FROM uso_llm WHERE em >= %s", (mes,)).fetchone()["v"])

    def tokens_de_hoje(self) -> int:
        hoje = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        with _conn() as c:
            return int(c.execute("""SELECT coalesce(sum(tokens_entrada + tokens_saida + tokens_cache_escrita + tokens_cache_leitura),0) AS v
                                    FROM uso_llm WHERE em >= %s""", (hoje,)).fetchone()["v"])

    # ---- limites e preços (tabela `configuracoes`) ----
    def limites(self) -> dict:
        with _conn() as c:
            r = c.execute("SELECT valor FROM configuracoes WHERE chave = 'governanca'").fetchone()
        return {**LIMITES_PADRAO, **((r["valor"] if r else None) or {})}

    def salvar_limites(self, valor: dict) -> dict:
        with _conn() as c:
            c.execute("""INSERT INTO configuracoes (chave, valor, atualizado_em) VALUES ('governanca', %s, now())
                         ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, atualizado_em = now()""", (json.dumps(valor),))
        return self.limites()

    def precos(self) -> dict:
        with _conn() as c:
            r = c.execute("SELECT valor FROM configuracoes WHERE chave = 'precos'").fetchone()
        return (r["valor"] if r else None) or {}

    def salvar_precos(self, valor: dict) -> dict:
        with _conn() as c:
            c.execute("""INSERT INTO configuracoes (chave, valor, atualizado_em) VALUES ('precos', %s, now())
                         ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor, atualizado_em = now()""", (json.dumps(valor),))
        return self.precos()


_cache: dict = {"em": 0.0, "valor": None}
TETO_DURO = 1.5      # a partir de 150% do limite o agente para de chamar o LLM e entrega ao corretor


def estado_do_orcamento(cache_segundos: float = 60) -> dict:
    """Versão cacheada para o caminho quente (cada chamada de LLM consulta isto)."""
    import time as _t
    if _cache["valor"] is not None and _t.time() - _cache["em"] < cache_segundos:
        return _cache["valor"]
    v = _calcular_orcamento()
    _cache.update(em=_t.time(), valor=v)
    return v


def invalidar_cache_orcamento() -> None:
    _cache.update(em=0.0, valor=None)


def _calcular_orcamento() -> dict:
    """Quanto do orçamento já foi usado e o que isso implica para o agente (ver ports/factory)."""
    repo = UsoRepository()
    lim = repo.limites()
    gasto, tokens = repo.gasto_do_mes(), repo.tokens_de_hoje()
    teto_usd, teto_tok = float(lim.get("orcamento_mensal_usd") or 0), int(lim.get("teto_tokens_dia") or 0)
    pct_usd = gasto / teto_usd if teto_usd else 0.0
    pct_tok = tokens / teto_tok if teto_tok else 0.0
    pct = max(pct_usd, pct_tok)
    alerta = float(lim.get("alerta_pct") or 80) / 100
    acao = lim.get("acao_ao_estourar", "degradar")
    estourado = pct >= 1
    return {"limites": lim, "gasto_mes_usd": round(gasto, 4), "tokens_hoje": tokens,
            "pct_orcamento": round(pct_usd, 4), "pct_tokens": round(pct_tok, 4), "pct": round(pct, 4),
            "em_alerta": alerta <= pct < 1, "estourado": estourado, "acao": acao,
            # o que o agente faz agora: normal | degradado (só modelo barato) | bloqueado (entrega ao corretor)
            "modo": "bloqueado" if estourado and (acao == "bloquear" or (acao == "degradar" and pct >= TETO_DURO))
                    else "degradado" if estourado and acao == "degradar" else "normal"}
