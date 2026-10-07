"""Follow-ups na tabela `followups_agendados`; um worker (services/scheduler/local_worker.py) faz polling a cada 30 s."""
from datetime import datetime, timedelta, timezone
from ...db import get_pool


class PostgresScheduler:
    def schedule(self, lead_id: str, delay_min: int, payload: str) -> None:
        quando = datetime.now(timezone.utc) + timedelta(minutes=delay_min)
        with get_pool().connection() as c:
            c.execute("""INSERT INTO followups_agendados (lead_id, disparar_em, payload) VALUES (%s, %s, %s)
                         ON CONFLICT (lead_id) DO UPDATE SET disparar_em = EXCLUDED.disparar_em, payload = EXCLUDED.payload""",
                      (lead_id, quando, payload))

    def cancel(self, lead_id: str) -> None:
        with get_pool().connection() as c:
            c.execute("DELETE FROM followups_agendados WHERE lead_id = %s", (lead_id,))

    def devolver(self, lead_id: str, payload: str, delay_min: int = 1) -> None:
        """Repõe um follow-up que saiu de `vencidos()` mas não pôde ser publicado. Não sobrescreve
        um agendamento mais novo do mesmo lead, que vale mais que o antigo."""
        quando = datetime.now(timezone.utc) + timedelta(minutes=delay_min)
        with get_pool().connection() as c:
            c.execute("""INSERT INTO followups_agendados (lead_id, disparar_em, payload) VALUES (%s, %s, %s)
                         ON CONFLICT (lead_id) DO NOTHING""", (lead_id, quando, payload))

    def vencidos(self) -> list[tuple[str, str]]:
        """Tira da tabela e devolve o que venceu. Quem chama publica cada um e, se a publicação
        falhar, devolve o item com `devolver` — senão o follow-up some (ver `local_worker.ciclo`).

        O pool entrega linhas como dicionário (`dict_row`): ler por posição levantava `KeyError`
        DEPOIS do DELETE já gravado (autocommit), e todo follow-up vencido era apagado sem nunca
        ser enviado. O laço do scheduler engolia o erro como "ciclo falhou"."""
        with get_pool().connection() as c:
            rows = c.execute("""DELETE FROM followups_agendados WHERE disparar_em <= now()
                                RETURNING lead_id, payload""").fetchall()
        return [(r["lead_id"], r["payload"]) for r in rows]
