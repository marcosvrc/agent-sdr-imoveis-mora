"""Encaminhamento ao corretor — a transferência de controle do atendimento."""
from fastapi import APIRouter, Response

from ...db.connection import leitura
from ...erros import ErroDeNegocio, NaoEncontrado
from .. import auditoria, protocolo
from ..contexto import Contexto, Ctx, envelope, executar
from ..esquemas import HandoffNovo, TransicaoHandoff

router = APIRouter(tags=["handoffs"])


@router.get("/handoffs")
def listar(ctx: Contexto = Ctx, status: str | None = "pending", limit: int | None = None):
    ctx.ator.exigir("crm:read")
    onde, valores = ["true"], []
    if status:
        onde.append("h.status = %s")
        valores.append(status)
    with leitura() as conn:
        linhas = conn.execute(
            f"""SELECT h.*, o.stage, o.purpose, l.name AS lead_name, l.id AS lead_id
                  FROM handoffs h JOIN opportunities o ON o.id = h.opportunity_id
                  JOIN leads l ON l.id = o.lead_id
                 WHERE {' AND '.join(onde)} ORDER BY h.created_at LIMIT %s""",
            [*valores, protocolo.limite(limit)]).fetchall()
    return {"items": linhas, "next_cursor": None}


@router.get("/handoffs/{hid}")
def detalhe(hid: str, resposta: Response, ctx: Contexto = Ctx):
    ctx.ator.exigir("crm:read")
    with leitura() as conn:
        linha = conn.execute("SELECT * FROM handoffs WHERE id = %s", (hid,)).fetchone()
    if linha is None:
        raise NaoEncontrado("Encaminhamento não encontrado.", handoff_id=hid)
    resposta.headers["ETag"] = protocolo.etag(linha["version"])
    return envelope(linha, ctx.request_id)


@router.post("/handoffs", status_code=201)
def solicitar(corpo: HandoffNovo, ctx: Contexto = Ctx):
    """Cria UM encaminhamento pendente e passa o atendimento para `human_pending`.

    O resumo é obrigatório porque é ele que economiza a releitura da conversa inteira: o corretor
    precisa saber em trinta segundos o que a pessoa quer e por que o agente parou.
    """
    ctx.ator.exigir("handoffs:write")

    def acao(conn):
        op = conn.execute("SELECT * FROM opportunities WHERE id = %s FOR UPDATE",
                          (corpo.opportunity_id,)).fetchone()
        if op is None:
            raise NaoEncontrado("Oportunidade não encontrada.", opportunity_id=corpo.opportunity_id)
        aberto = conn.execute(
            "SELECT * FROM handoffs WHERE opportunity_id = %s AND status IN ('pending','accepted')",
            (corpo.opportunity_id,)).fetchone()
        if aberto is not None:
            # Repetir o pedido não cria uma segunda fila: devolve o encaminhamento que já existe.
            # Duas filas para o mesmo atendimento é como dois corretores ligam para a mesma pessoa.
            return 200, envelope(aberto, ctx.request_id)
        if corpo.assignee_id:
            # Mesma conferência que os horários fazem com `broker_id`: destinatário inexistente ou
            # inativo transformaria o encaminhamento numa fila que ninguém vê.
            dono = conn.execute(
                "SELECT id FROM users WHERE id = %s AND active AND role IN ('admin','broker')",
                (corpo.assignee_id,)).fetchone()
            if dono is None:
                raise ErroDeNegocio("Destinatário não é um corretor ativo.",
                                    assignee_id=corpo.assignee_id)
        linha = conn.execute(
            """INSERT INTO handoffs (opportunity_id, reason, summary, assignee_id)
               VALUES (%s, %s, %s, %s) RETURNING *""",
            (corpo.opportunity_id, corpo.reason, corpo.summary, corpo.assignee_id)).fetchone()
        conn.execute("UPDATE opportunities SET atendimento = 'human_pending', updated_at = now(), "
                     "version = version + 1 WHERE id = %s", (corpo.opportunity_id,))
        auditoria.registrar(conn, ator=ctx.ator, action="handoff.requested", entity_type="handoff",
                            entity_id=str(linha["id"]), request_id=ctx.request_id,
                            changes={"opportunity_id": corpo.opportunity_id, "reason": corpo.reason})
        return 201, envelope(linha, ctx.request_id)

    return executar(ctx, "POST", "/v1/handoffs", corpo.model_dump(mode="json"), acao)


@router.post("/handoffs/{hid}/transitions")
def transicionar(hid: str, corpo: TransicaoHandoff, ctx: Contexto = Ctx):
    """Aceitar e resolver são humanas.

    Na resolução, `return_to` é **obrigatório**: resolver não devolve o atendimento ao agente
    sozinho (seção 6). O corretor que atendeu é quem sabe se a conversa pode voltar ao automático
    ou se ele continua nela — e deixar isso implícito significaria o agente voltando a escrever
    para um cliente no meio de uma negociação conduzida por gente.
    """
    ctx.ator.exigir_humano(f"marcar encaminhamento como '{corpo.target_status}'")
    esperada = protocolo.versao_do_if_match(ctx.if_match)

    def acao(conn):
        antes = conn.execute("SELECT * FROM handoffs WHERE id = %s FOR UPDATE", (hid,)).fetchone()
        if antes is None:
            raise NaoEncontrado("Encaminhamento não encontrado.", handoff_id=hid)
        protocolo.conferir_versao(antes["version"], esperada)
        permitidas = {"pending": {"accepted", "resolved"}, "accepted": {"resolved"}, "resolved": set()}
        if corpo.target_status not in permitidas[antes["status"]]:
            raise ErroDeNegocio(f"De '{antes['status']}' não se vai para '{corpo.target_status}'.",
                                allowed=sorted(permitidas[antes["status"]]))
        if corpo.target_status == "resolved" and corpo.return_to is None:
            raise ErroDeNegocio(
                "Ao resolver, diga explicitamente se o atendimento volta para 'agent' ou fica em 'human'.",
                field="return_to")

        depois = conn.execute(
            """UPDATE handoffs SET status = %s, assignee_id = coalesce(%s, assignee_id),
                   updated_at = now(), version = version + 1 WHERE id = %s RETURNING *""",
            (corpo.target_status, corpo.assignee_id or ctx.ator.id, hid)).fetchone()

        atendimento = {"accepted": "human"}.get(corpo.target_status) or corpo.return_to
        conn.execute("UPDATE opportunities SET atendimento = %s, updated_at = now(), "
                     "version = version + 1 WHERE id = %s",
                     (atendimento, antes["opportunity_id"]))
        auditoria.registrar(conn, ator=ctx.ator, action=f"handoff.{corpo.target_status}",
                            entity_type="handoff", entity_id=hid, request_id=ctx.request_id,
                            changes={"de": antes["status"], "para": corpo.target_status,
                                     "atendimento": atendimento})
        return 200, envelope({**depois, "atendimento": atendimento}, ctx.request_id)

    return executar(ctx, "POST", f"/v1/handoffs/{hid}/transitions", corpo.model_dump(mode="json"),
                    acao)
