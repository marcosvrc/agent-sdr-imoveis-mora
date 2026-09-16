"""Observabilidade leve (ADR-0011): grava no Postgres que já roda, sem coletor nem exporter.

Três coisas, todas baratas:
  • `registrar_turno`  — um INSERT por turno, com o tempo que o CLIENTE esperou. É o número que
    faltava: `uso_llm.latencia_ms` mede uma chamada de LLM isolada, não o turno inteiro.
  • `amostrar`         — uma linha a cada 30s (profundidade das filas, conexões do banco), escrita
    pelo laço do scheduler que já existe. Nenhum processo novo.
  • `bater`/`iniciar_batimento` — carimbo de vida por serviço. Processo morto não reporta a própria
    morte, então quem detecta é outro processo lendo `batimentos` (ver /health da api).

Nada aqui pode derrubar o atendimento: toda escrita é best-effort e engole a própria exceção.
"""
import logging
import threading
import time
from datetime import datetime, timedelta, timezone

from .connection import get_pool

log = logging.getLogger("monitoramento")

RETENCAO_DIAS = 7                 # o suficiente para investigar; a tabela nunca vira problema
BATIMENTO_S = 30
PARADO_S = 120                    # sem carimbo por mais que isto = serviço considerado parado


def _conn():
    return get_pool().connection()


# ------------------------------------------------------------------ turnos

def registrar_turno(lead_id: str, canal: str, resultado: str, duracao_ms: int,
                    estagio: str | None = None, nos: list[str] | None = None) -> None:
    try:
        with _conn() as c:
            c.execute("""INSERT INTO turnos (lead_id, canal, resultado, duracao_ms, estagio, nos)
                         VALUES (%s, %s, %s, %s, %s, %s)""",
                      (lead_id, canal, resultado, int(duracao_ms), estagio, nos or []))
    except Exception:
        log.debug("falha ao registrar turno", exc_info=True)      # observar nunca atrapalha atender


def resumo_de_turnos(horas: int = 24) -> dict:
    """p50/p95 da espera do cliente e distribuição por resultado. É a leitura principal da tela."""
    with _conn() as c:
        r = c.execute("""
            SELECT count(*)                                                        AS total,
                   coalesce(percentile_disc(0.5) WITHIN GROUP (ORDER BY duracao_ms), 0)  AS p50,
                   coalesce(percentile_disc(0.95) WITHIN GROUP (ORDER BY duracao_ms), 0) AS p95,
                   coalesce(max(duracao_ms), 0)                                    AS pior,
                   count(*) FILTER (WHERE resultado <> 'ok')                       AS nao_ok,
                   count(*) FILTER (WHERE duracao_ms > 30000)                      AS lentos
              FROM turnos WHERE em >= now() - make_interval(hours => %s)""", (horas,)).fetchone()
        por_resultado = c.execute("""SELECT resultado, count(*) AS n FROM turnos
                                     WHERE em >= now() - make_interval(hours => %s)
                                     GROUP BY resultado ORDER BY n DESC""", (horas,)).fetchall()
        serie = c.execute("""SELECT date_trunc('hour', em) AS hora, count(*) AS n,
                                    coalesce(percentile_disc(0.95) WITHIN GROUP (ORDER BY duracao_ms), 0) AS p95,
                                    count(*) FILTER (WHERE resultado <> 'ok') AS falhas
                               FROM turnos WHERE em >= now() - make_interval(hours => %s)
                              GROUP BY 1 ORDER BY 1""", (horas,)).fetchall()
    total = int(r["total"])
    return {"total": total, "p50_ms": int(r["p50"]), "p95_ms": int(r["p95"]), "pior_ms": int(r["pior"]),
            "taxa_falha": round(100 * int(r["nao_ok"]) / total, 1) if total else 0.0,
            "acima_de_30s": int(r["lentos"]),
            "por_resultado": {x["resultado"]: int(x["n"]) for x in por_resultado},
            "serie": [{"hora": x["hora"].isoformat(), "turnos": int(x["n"]),
                       "p95_ms": int(x["p95"]), "falhas": int(x["falhas"])} for x in serie]}


# ------------------------------------------------------------------ amostra

def amostrar(filas: dict[str, int] | None = None) -> None:
    """Uma linha por tique do scheduler. Também apara o que passou da retenção — sem cron extra."""
    try:
        import json
        with _conn() as c:
            conexoes = c.execute("SELECT count(*) AS n FROM pg_stat_activity WHERE datname = current_database()").fetchone()["n"]
            c.execute("INSERT INTO saude (filas, conexoes_db) VALUES (%s, %s)",
                      (json.dumps(filas or {}), int(conexoes)))
            if datetime.now(timezone.utc).minute == 0:            # uma vez por hora basta
                corte = datetime.now(timezone.utc) - timedelta(days=RETENCAO_DIAS)
                c.execute("DELETE FROM saude WHERE em < %s", (corte,))
                c.execute("DELETE FROM turnos WHERE em < %s", (corte,))
    except Exception:
        log.debug("falha ao amostrar saúde", exc_info=True)


def ultima_amostra() -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT em, filas, conexoes_db FROM saude ORDER BY em DESC LIMIT 1").fetchone()
    return {"em": r["em"].isoformat(), "filas": r["filas"], "conexoes_db": r["conexoes_db"]} if r else None


# --------------------------------------------------------------- batimentos

def bater(servico: str, detalhe: dict | None = None) -> None:
    try:
        import json
        with _conn() as c:
            c.execute("""INSERT INTO batimentos (servico, em, detalhe) VALUES (%s, now(), %s)
                         ON CONFLICT (servico) DO UPDATE SET em = now(), detalhe = EXCLUDED.detalhe""",
                      (servico, json.dumps(detalhe or {})))
    except Exception:
        log.debug("falha ao bater ponto de %s", servico, exc_info=True)


def iniciar_batimento(servico: str, intervalo_s: int = BATIMENTO_S) -> None:
    """Thread daemon: bate a cada 30s independente do formato do laço do worker.

    Daemon de propósito — se o processo principal morre, a thread morre junto e o carimbo para de
    ser atualizado. É exatamente o sinal que se quer detectar."""
    def laco():
        while True:
            bater(servico)
            time.sleep(intervalo_s)
    bater(servico)
    threading.Thread(target=laco, name=f"batimento-{servico}", daemon=True).start()


def servicos_parados() -> list[dict]:
    """Quem deveria estar batendo e não bate. Lido pelo /health por OUTRO processo."""
    try:
        with _conn() as c:
            rows = c.execute("""SELECT servico, em, extract(epoch FROM now() - em)::int AS ha_segundos
                                  FROM batimentos ORDER BY servico""").fetchall()
    except Exception:
        return []
    return [{"servico": r["servico"], "ha_segundos": int(r["ha_segundos"]), "em": r["em"].isoformat()}
            for r in rows if int(r["ha_segundos"]) > PARADO_S]


def batimentos() -> list[dict]:
    with _conn() as c:
        rows = c.execute("""SELECT servico, em, detalhe, extract(epoch FROM now() - em)::int AS ha_segundos
                              FROM batimentos ORDER BY servico""").fetchall()
    return [{"servico": r["servico"], "em": r["em"].isoformat(), "ha_segundos": int(r["ha_segundos"]),
             "vivo": int(r["ha_segundos"]) <= PARADO_S, "detalhe": r["detalhe"]} for r in rows]
