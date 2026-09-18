"""Números do funil e auditoria."""
from datetime import UTC, datetime

from fastapi import APIRouter

from ...db.connection import leitura
from .. import protocolo
from ..contexto import Contexto, Ctx, envelope

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def painel(ctx: Contexto = Ctx):
    """Contagens por estágio, tarefas vencidas, visitas futuras e encaminhamentos pendentes.

    `generated_at` vai junto porque a tela precisa dizer de quando é o número. Dashboard sem
    carimbo de hora é a forma mais fácil de alguém tomar decisão com dado de ontem.
    """
    ctx.ator.exigir("crm:read")
    with leitura() as conn:
        estagios = conn.execute(
            "SELECT stage, count(*) AS n FROM opportunities GROUP BY stage").fetchall()
        numeros = conn.execute("""
            SELECT
              (SELECT count(*) FROM leads WHERE archived_at IS NULL)                      AS leads_ativos,
              (SELECT count(*) FROM tasks WHERE status = 'open' AND due_at < now())        AS tarefas_vencidas,
              (SELECT count(*) FROM visits v JOIN availability_slots s ON s.id = v.slot_id
                WHERE v.status = 'confirmed' AND s.starts_at > now())                      AS visitas_futuras,
              (SELECT count(*) FROM visits WHERE status = 'requested')                     AS visitas_solicitadas,
              (SELECT count(*) FROM handoffs WHERE status = 'pending')                     AS handoffs_pendentes,
              (SELECT count(*) FROM properties WHERE status = 'available')                 AS imoveis_disponiveis
        """).fetchone()
    por_estagio = {linha["stage"]: linha["n"] for linha in estagios}
    return envelope({"por_estagio": por_estagio, **numeros,
                     "generated_at": datetime.now(UTC).isoformat()}, ctx.request_id)


@router.get("/audit-events")
def auditoria(ctx: Contexto = Ctx, entity_type: str | None = None, entity_id: str | None = None,
              actor_id: str | None = None, limit: int | None = None, cursor: str | None = None):
    """Só administrador. Auditoria mostra quem fez o quê — inclusive sobre o próprio corretor que
    estivesse consultando."""
    ctx.ator.exigir("admin")
    onde, valores = ["true"], []
    for coluna, valor in (("entity_type", entity_type), ("entity_id", entity_id),
                          ("actor_id", actor_id)):
        if valor:
            onde.append(f"{coluna} = %s")
            valores.append(valor)
    n = protocolo.limite(limit)
    if (marca := protocolo.decifrar_cursor(cursor)) is not None:
        onde.append("(occurred_at, id) < (%s, %s)")
        valores.extend(marca)
    with leitura() as conn:
        linhas = conn.execute(
            f"SELECT * FROM audit_events WHERE {' AND '.join(onde)} "
            f"ORDER BY occurred_at DESC, id DESC LIMIT %s", [*valores, n + 1]).fetchall()
    proximo = None
    if len(linhas) > n:
        linhas = linhas[:n]
        proximo = protocolo.cifrar_cursor(linhas[-1]["occurred_at"], linhas[-1]["id"])
    return {"items": linhas, "next_cursor": proximo}
