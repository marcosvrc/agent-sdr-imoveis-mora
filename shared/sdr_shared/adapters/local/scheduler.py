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

    def vencidos(self) -> list[tuple[str, str]]:
        with get_pool().connection() as c:
            rows = c.execute("""DELETE FROM followups_agendados WHERE disparar_em <= now()
                                RETURNING lead_id, payload""").fetchall()
        return [(r[0], r[1]) for r in rows]
