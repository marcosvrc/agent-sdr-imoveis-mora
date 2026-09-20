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


# ------------------------------------------------- diagnóstico: por que está lento

def recorte_de_turnos(horas: int = 24, campo: str = "canal") -> list[dict]:
    """Espera e falha por canal ou por estágio.

    O p95 global diz que ESTÁ lento; este recorte começa a dizer ONDE. Telegram lento com a web
    rápida aponta para o canal; lentidão só na qualificação aponta para o prompt daquele nó.
    """
    if campo not in ("canal", "estagio"):                      # o valor vai concatenado no SQL
        raise ValueError(f"recorte desconhecido: {campo}")
    with _conn() as c:
        rows = c.execute(f"""
            SELECT coalesce({campo}, 'sem registro') AS chave, count(*) AS turnos,
                   coalesce(percentile_disc(0.5)  WITHIN GROUP (ORDER BY duracao_ms), 0) AS p50,
                   coalesce(percentile_disc(0.95) WITHIN GROUP (ORDER BY duracao_ms), 0) AS p95,
                   count(*) FILTER (WHERE resultado <> 'ok') AS falhas
              FROM turnos WHERE em >= now() - make_interval(hours => %s)
             GROUP BY 1 ORDER BY turnos DESC""", (horas,)).fetchall()
    return [{"chave": r["chave"], "turnos": int(r["turnos"]), "p50_ms": int(r["p50"]),
             "p95_ms": int(r["p95"]), "falhas": int(r["falhas"])} for r in rows]


def nos_dos_turnos_lentos(horas: int = 24) -> dict:
    """Quais nós do grafo aparecem nos 5% de turnos mais lentos, comparados com o resto.

    ATENÇÃO ao que este número é e ao que ele não é: `turnos.nos` guarda o CAMINHO percorrido, não
    o tempo de cada nó. Então isto mede **presença**, não duração — um nó que aparece em 90% dos
    turnos lentos e em 20% dos rápidos é um suspeito, não um culpado. Apresentar isso como "o nó X
    gastou 4s" seria inventar uma medição que o projeto não faz; quem quiser a duração por nó
    precisa passar a gravá-la.

    O corte é o p95 do próprio período, e não um limiar fixo: num dia bom, 30s nunca seria atingido
    e a tabela ficaria sempre vazia, escondendo o nó que está fazendo o dia bom ser pior.
    """
    with _conn() as c:
        r = c.execute("""SELECT count(*) AS total,
                                coalesce(percentile_disc(0.95) WITHIN GROUP (ORDER BY duracao_ms), 0) AS p95
                           FROM turnos WHERE em >= now() - make_interval(hours => %s)""", (horas,)).fetchone()
        total, corte = int(r["total"]), int(r["p95"])
        if not total:
            return {"corte_ms": 0, "lentos": 0, "nos": []}
        rows = c.execute("""
            SELECT no, count(*) AS total,
                   count(*) FILTER (WHERE t.duracao_ms >= %(corte)s) AS em_lentos
              FROM turnos t, unnest(t.nos) AS no
             WHERE t.em >= now() - make_interval(hours => %(h)s)
             GROUP BY no""", {"corte": corte, "h": horas}).fetchall()
        lentos = int(c.execute("""SELECT count(*) AS n FROM turnos
                                   WHERE em >= now() - make_interval(hours => %s) AND duracao_ms >= %s""",
                               (horas, corte)).fetchone()["n"])
    rapidos = total - lentos
    nos = [{"no": r["no"],
            "em_lentos": int(r["em_lentos"]),
            "em_rapidos": int(r["total"]) - int(r["em_lentos"]),
            "pct_lentos": round(100 * int(r["em_lentos"]) / lentos, 1) if lentos else 0.0,
            "pct_rapidos": round(100 * (int(r["total"]) - int(r["em_lentos"])) / rapidos, 1) if rapidos else 0.0}
           for r in rows]
    # Ordena pelo tamanho da DIFERENÇA: um nó presente em todo turno (o supervisor) aparece em 100%
    # dos dois lados e não explica nada; o que informa é quem aparece muito mais de um lado.
    nos.sort(key=lambda n: n["pct_lentos"] - n["pct_rapidos"], reverse=True)
    return {"corte_ms": corte, "lentos": lentos, "nos": nos}


def serie_de_amostras(horas: int = 24) -> list[dict]:
    """Profundidade de fila e conexões do banco AO LONGO do tempo, não só na última amostra.

    Fila estável em 40 e fila subindo de 0 a 40 têm exatamente a mesma aparência quando se olha um
    número só — e são situações opostas: uma é ritmo, a outra é represamento.

    Máximo por balde, não média: o pico é o que dói. Uma fila que encheu por dois minutos some
    inteira numa média horária.
    """
    balde = 600 if horas <= 12 else 3600                       # 10 min em janela curta, 1 h nas longas
    with _conn() as c:
        rows = c.execute("""
            SELECT to_timestamp(floor(extract(epoch FROM em) / %(b)s) * %(b)s) AS bucket,
                   max(coalesce((SELECT sum(v::int) FROM jsonb_each_text(filas) AS e(k, v)), 0)) AS filas,
                   max(conexoes_db) AS conexoes
              FROM saude WHERE em >= now() - make_interval(hours => %(h)s)
             GROUP BY 1 ORDER BY 1""", {"b": balde, "h": horas}).fetchall()
    return [{"em": r["bucket"].isoformat(), "filas": int(r["filas"] or 0),
             "conexoes": int(r["conexoes"]) if r["conexoes"] is not None else None} for r in rows]


def saude_dos_provedores(horas: int = 24) -> list[dict]:
    """Falha e latência por provedor de LLM.

    Mora em Governança porque lá se olha custo; aqui se olha disponibilidade. É a mesma tabela
    respondendo outra pergunta: quando o agente fica lento sem a fila crescer, costuma ser isto.
    """
    with _conn() as c:
        rows = c.execute("""
            SELECT provider, count(*) AS chamadas,
                   count(*) FILTER (WHERE erro IS NOT NULL) AS erros,
                   coalesce(percentile_disc(0.95) WITHIN GROUP (ORDER BY latencia_ms)
                            FILTER (WHERE erro IS NULL), 0) AS p95
              FROM uso_llm WHERE em >= now() - make_interval(hours => %s)
             GROUP BY 1 ORDER BY chamadas DESC""", (horas,)).fetchall()
    return [{"provedor": r["provider"], "chamadas": int(r["chamadas"]), "erros": int(r["erros"]),
             "p95_ms": int(r["p95"]),
             "taxa_erro": round(100 * int(r["erros"]) / int(r["chamadas"]), 1) if r["chamadas"] else 0.0}
            for r in rows]
