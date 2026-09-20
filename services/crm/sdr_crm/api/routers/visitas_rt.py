"""Visitas: solicitar (agente) e confirmar/concluir (humano)."""
from fastapi import APIRouter, Response

from ...db.connection import leitura
from ...dominio import funil
from ...erros import AtendimentoHumano, ErroDeNegocio, NaoEncontrado, SlotIndisponivel
from .. import auditoria, protocolo
from ..contexto import Contexto, Ctx, envelope, executar
from ..esquemas import Remarcacao, TransicaoVisita, VisitaNova

router = APIRouter(tags=["visitas"])

# requested → confirmed/cancelled; confirmed → completed/cancelled/no_show. Estados finais não são
# editáveis: reagendar é cancelar e solicitar de novo, o que mantém o histórico do que foi tentado.
PERMITIDAS = {
    "requested": frozenset({"confirmed", "cancelled"}),
    "confirmed": frozenset({"completed", "cancelled", "no_show"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
    "no_show": frozenset(),
}


def _visita(conn, vid: str, *, para_alterar: bool = False) -> dict:
    linha = conn.execute(
        f"""SELECT v.*, s.starts_at, s.ends_at, o.stage, o.atendimento
              FROM visits v JOIN availability_slots s ON s.id = v.slot_id
              JOIN opportunities o ON o.id = v.opportunity_id
             WHERE v.id = %s {'FOR UPDATE OF v' if para_alterar else ''}""", (vid,)).fetchone()
    if linha is None:
        raise NaoEncontrado("Visita não encontrada.", visit_id=vid)
    return linha


@router.get("/visits")
def listar(ctx: Contexto = Ctx, opportunity_id: str | None = None, status: str | None = None,
           limit: int | None = None):
    ctx.ator.exigir("crm:read")
    onde, valores = ["true"], []
    if opportunity_id:
        onde.append("v.opportunity_id = %s")
        valores.append(opportunity_id)
    if status:
        onde.append("v.status = %s")
        valores.append(status)
    with leitura() as conn:
        linhas = conn.execute(
            f"""SELECT v.*, s.starts_at, s.ends_at FROM visits v
                  JOIN availability_slots s ON s.id = v.slot_id
                 WHERE {' AND '.join(onde)} ORDER BY s.starts_at LIMIT %s""",
            [*valores, protocolo.limite(limit)]).fetchall()
    return {"items": linhas, "next_cursor": None}


@router.get("/visits/{vid}")
def detalhe(vid: str, resposta: Response, ctx: Contexto = Ctx):
    ctx.ator.exigir("crm:read")
    with leitura() as conn:
        linha = _visita(conn, vid)
    resposta.headers["ETag"] = protocolo.etag(linha["version"])
    return envelope(linha, ctx.request_id)


@router.post("/visits", status_code=201)
def solicitar(corpo: VisitaNova, ctx: Contexto = Ctx):
    """Solicitar NÃO agenda e NÃO reserva o horário.

    É a distinção mais importante deste módulo: o agente pede, o corretor confirma. Sem ela, o
    agente marcaria compromissos na agenda de uma pessoa que não foi consultada — e o estágio da
    oportunidade diria "visita marcada" sem que ninguém tivesse combinado nada.
    """
    ctx.ator.exigir("visits:request")

    def acao(conn):
        op = conn.execute("SELECT * FROM opportunities WHERE id = %s FOR UPDATE",
                          (corpo.opportunity_id,)).fetchone()
        if op is None:
            raise NaoEncontrado("Oportunidade não encontrada.", opportunity_id=corpo.opportunity_id)
        if op["atendimento"] in {"human_pending", "human"} and not ctx.ator.humano:
            raise AtendimentoHumano("O atendimento está com um corretor: o agente não pede visitas.")
        if op["stage"] in {"new", "in_service"}:
            faltam = funil.campos_faltantes(funil.Contexto(
                stage=op["stage"], purpose=op["purpose"], atendimento=op["atendimento"],
                preferencias=dict(conn.execute(
                    "SELECT * FROM preferences WHERE opportunity_id = %s",
                    (corpo.opportunity_id,)).fetchone() or {})))
            raise ErroDeNegocio(
                "Visita exige oportunidade qualificada — colete o que falta antes.",
                stage=op["stage"], missing_fields=faltam)
        if op["stage"] in {"won", "lost"}:
            raise ErroDeNegocio("Oportunidade encerrada não recebe visita.", stage=op["stage"])

        imovel = conn.execute("SELECT * FROM properties WHERE id = %s",
                              (corpo.property_id,)).fetchone()
        if imovel is None:
            raise NaoEncontrado("Imóvel não encontrado.", property_id=corpo.property_id)
        if imovel["status"] != "available":
            raise ErroDeNegocio("Imóvel não está disponível para visita.", status=imovel["status"])
        if imovel["purpose"] != op["purpose"]:
            raise ErroDeNegocio("Imóvel e oportunidade têm propósitos diferentes.")

        slot = conn.execute("SELECT * FROM availability_slots WHERE id = %s",
                            (corpo.slot_id,)).fetchone()
        if slot is None or str(slot["property_id"]) != corpo.property_id:
            raise NaoEncontrado("Horário não pertence a este imóvel.", slot_id=corpo.slot_id)
        futuro = conn.execute("SELECT %s > now() AS ok", (slot["starts_at"],)).fetchone()
        if not futuro["ok"]:
            raise ErroDeNegocio("Horário no passado.", slot_id=corpo.slot_id)

        linha = conn.execute(
            """INSERT INTO visits (opportunity_id, property_id, slot_id, notes)
               VALUES (%s, %s, %s, %s) RETURNING *""",
            (corpo.opportunity_id, corpo.property_id, corpo.slot_id, corpo.notes)).fetchone()
        auditoria.registrar(conn, ator=ctx.ator, action="visit.requested", entity_type="visit",
                            entity_id=str(linha["id"]), request_id=ctx.request_id,
                            changes={"opportunity_id": corpo.opportunity_id,
                                     "property_id": corpo.property_id, "slot_id": corpo.slot_id})
        return 201, envelope(linha, ctx.request_id)

    return executar(ctx, "POST", "/v1/visits", corpo.model_dump(mode="json"), acao)


@router.post("/visits/{vid}/reschedule")
def remarcar(vid: str, corpo: Remarcacao, ctx: Contexto = Ctx):
    """Cancela a visita e cria a nova, ligadas, numa transação só.

    **Por que não basta cancelar e pedir de novo**, que é o que dava para fazer antes: no histórico
    ficavam dois eventos soltos, ninguém sabia que era a mesma visita que andou, e a cancelada
    parecia cliente perdido. Aqui a antiga aponta para a nova.

    **Quem remarca uma visita CONFIRMADA já é quem confirma**, então a nova nasce confirmada — é a
    fricção que a remarcação existia para tirar. Vindo do agente, ou de uma visita que ainda era só
    solicitação, a nova nasce solicitada como qualquer outra: confirmar continua sendo ato humano.

    Se o horário novo já tiver visita confirmada, o índice único do banco recusa e nada acontece —
    nem o cancelamento da antiga. É a razão de ser uma transação só.
    """
    ctx.ator.exigir("visits:request")

    def acao(conn):
        visita = _visita(conn, vid, para_alterar=True)
        if visita["status"] not in {"requested", "confirmed"}:
            raise ErroDeNegocio("Só visita solicitada ou confirmada pode ser remarcada.",
                                status=visita["status"])
        era_confirmada = visita["status"] == "confirmed"
        if era_confirmada and not ctx.ator.humano:
            # Mesma regra do cancelamento: quebrar compromisso já combinado é ato de gente.
            raise ErroDeNegocio("O agente não remarca visita já confirmada.", status=visita["status"])

        slot = conn.execute("SELECT * FROM availability_slots WHERE id = %s",
                            (corpo.slot_id,)).fetchone()
        if slot is None or str(slot["property_id"]) != str(visita["property_id"]):
            raise NaoEncontrado("Horário não pertence a este imóvel.", slot_id=corpo.slot_id)
        if str(slot["id"]) == str(visita["slot_id"]):
            raise ErroDeNegocio("O horário novo é o mesmo da visita atual.", slot_id=corpo.slot_id)
        if not conn.execute("SELECT %s > now() AS ok", (slot["starts_at"],)).fetchone()["ok"]:
            raise ErroDeNegocio("Horário no passado.", slot_id=corpo.slot_id)

        try:
            nova = conn.execute(
                """INSERT INTO visits (opportunity_id, property_id, slot_id, status, notes)
                   VALUES (%s, %s, %s, %s, %s) RETURNING *""",
                (visita["opportunity_id"], visita["property_id"], corpo.slot_id,
                 "confirmed" if era_confirmada else "requested", corpo.notes)).fetchone()
        except Exception as exc:
            if "visits_slot_confirmado_uk" in str(exc):
                raise SlotIndisponivel("O horário já foi reservado.", slot_id=corpo.slot_id)
            raise

        conn.execute(
            """UPDATE visits SET status = 'cancelled', cancellation_reason = %s,
                   rescheduled_to = %s, updated_at = now(), version = version + 1
                WHERE id = %s""", (corpo.reason, nova["id"], vid))
        auditoria.registrar(conn, ator=ctx.ator, action="visit.rescheduled", entity_type="visit",
                            entity_id=vid, request_id=ctx.request_id,
                            changes={"para_visita": str(nova["id"]), "slot_id": corpo.slot_id,
                                     "reason": corpo.reason, "status_novo": nova["status"]})
        return 201, envelope(nova, ctx.request_id)

    return executar(ctx, "POST", f"/v1/visits/{vid}/reschedule", corpo.model_dump(mode="json"), acao)


@router.post("/visits/{vid}/transitions")
def transicionar(vid: str, corpo: TransicaoVisita, ctx: Contexto = Ctx):
    """Confirmar, concluir e marcar falta são humanas. Cancelar o agente pode — e só o que está
    apenas solicitado, que é o pedido dele mesmo."""
    esperada = protocolo.versao_do_if_match(ctx.if_match)

    def acao(conn):
        visita = _visita(conn, vid, para_alterar=True)
        protocolo.conferir_versao(visita["version"], esperada)
        if corpo.target_status not in PERMITIDAS[visita["status"]]:
            raise ErroDeNegocio(
                f"De '{visita['status']}' não se vai para '{corpo.target_status}'.",
                allowed=sorted(PERMITIDAS[visita["status"]]))

        if corpo.target_status in {"confirmed", "completed", "no_show"}:
            ctx.ator.exigir_humano(f"marcar visita como '{corpo.target_status}'")
        elif corpo.target_status == "cancelled":
            ctx.ator.exigir("visits:request")
            if not ctx.ator.humano and visita["status"] != "requested":
                raise ErroDeNegocio("O agente só cancela visita ainda não confirmada.",
                                    status=visita["status"])
            if not (corpo.reason or "").strip():
                raise ErroDeNegocio("Cancelar exige motivo.")

        try:
            depois = conn.execute(
                """UPDATE visits SET status = %s,
                       cancellation_reason = CASE WHEN %s = 'cancelled' THEN %s ELSE cancellation_reason END,
                       updated_at = now(), version = version + 1
                   WHERE id = %s RETURNING *""",
                (corpo.target_status, corpo.target_status, corpo.reason, vid)).fetchone()
        except Exception as exc:
            # A corrida real: duas confirmações simultâneas no mesmo horário. Quem perde recebe
            # 409 SLOT_UNAVAILABLE porque o índice único parcial do banco decidiu — não a aplicação.
            if "visits_slot_confirmado_uk" in str(exc):
                raise SlotIndisponivel("O horário já foi reservado.", slot_id=str(visita["slot_id"]))
            raise

        estagio = None
        if corpo.target_status == "confirmed":
            # Confirmar PODE avançar `qualified` → `visit_scheduled`, e nunca regride negociação.
            if visita["stage"] == "qualified":
                conn.execute("UPDATE opportunities SET stage = 'visit_scheduled', "
                             "updated_at = now(), version = version + 1 WHERE id = %s",
                             (visita["opportunity_id"],))
                estagio = "visit_scheduled"
        elif corpo.target_status == "cancelled":
            restam = conn.execute(
                """SELECT count(*) AS n FROM visits v JOIN availability_slots s ON s.id = v.slot_id
                    WHERE v.opportunity_id = %s AND v.status = 'confirmed' AND s.starts_at > now()""",
                (visita["opportunity_id"],)).fetchone()
            novo = funil.estagio_apos_cancelar_visita(funil.Contexto(
                stage=visita["stage"], purpose="", atendimento=visita["atendimento"],
                preferencias={}, tem_visita_confirmada_futura=restam["n"] > 0))
            if novo:
                conn.execute("UPDATE opportunities SET stage = %s, updated_at = now(), "
                             "version = version + 1 WHERE id = %s",
                             (novo, visita["opportunity_id"]))
                estagio = novo

        auditoria.registrar(conn, ator=ctx.ator, action=f"visit.{corpo.target_status}",
                            entity_type="visit", entity_id=vid, request_id=ctx.request_id,
                            changes={"de": visita["status"], "para": corpo.target_status,
                                     "estagio_da_oportunidade": estagio})
        return 200, envelope({**depois, "opportunity_stage": estagio}, ctx.request_id)

    return executar(ctx, "POST", f"/v1/visits/{vid}/transitions", corpo.model_dump(mode="json"), acao)
