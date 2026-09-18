"""Tarefas do corretor."""
from fastapi import APIRouter, Response

from ...db.connection import leitura
from ...erros import ContatoBloqueado, ErroDeNegocio, NaoEncontrado
from .. import auditoria, protocolo
from ..contexto import Contexto, Ctx, envelope, executar
from ..esquemas import TarefaAlteracao, TarefaNova

router = APIRouter(tags=["tarefas"])


@router.get("/tasks")
def listar(ctx: Contexto = Ctx, opportunity_id: str | None = None, status: str | None = "open",
           overdue: bool = False, limit: int | None = None):
    ctx.ator.exigir("crm:read")
    onde, valores = ["true"], []
    if opportunity_id:
        onde.append("opportunity_id = %s")
        valores.append(opportunity_id)
    if status:
        onde.append("status = %s")
        valores.append(status)
    if overdue:
        onde.append("due_at < now() AND status = 'open'")
    with leitura() as conn:
        linhas = conn.execute(
            f"SELECT * FROM tasks WHERE {' AND '.join(onde)} "
            f"ORDER BY due_at NULLS LAST, created_at LIMIT %s",
            [*valores, protocolo.limite(limit)]).fetchall()
    return {"items": linhas, "next_cursor": None}


@router.get("/tasks/{tid}")
def detalhe(tid: str, resposta: Response, ctx: Contexto = Ctx):
    ctx.ator.exigir("crm:read")
    with leitura() as conn:
        linha = conn.execute("SELECT * FROM tasks WHERE id = %s", (tid,)).fetchone()
    if linha is None:
        raise NaoEncontrado("Tarefa não encontrada.", task_id=tid)
    resposta.headers["ETag"] = protocolo.etag(linha["version"])
    return envelope(linha, ctx.request_id)


@router.post("/tasks", status_code=201)
def criar(corpo: TarefaNova, ctx: Contexto = Ctx):
    """`follow_up` é contato ativo; `internal` é trabalho da casa.

    A diferença decide quem pode ser alvo: com contato bloqueado, o `follow_up` é recusado com
    `CONTACT_BLOCKED` e o `internal` passa. Tratar os dois igual impediria o corretor de anotar
    "ligar para o síndico" só porque o cliente pediu para não ser incomodado.
    """
    ctx.ator.exigir("tasks:write")

    def acao(conn):
        op = conn.execute(
            """SELECT o.*, l.contact_policy, l.id AS lead_id FROM opportunities o
                 JOIN leads l ON l.id = o.lead_id WHERE o.id = %s""",
            (corpo.opportunity_id,)).fetchone()
        if op is None:
            raise NaoEncontrado("Oportunidade não encontrada.", opportunity_id=corpo.opportunity_id)
        if corpo.kind == "follow_up" and op["contact_policy"] == "blocked":
            raise ContatoBloqueado("Este cliente pediu para não ser contatado.",
                                   lead_id=str(op["lead_id"]))
        if corpo.assignee_id:
            dono = conn.execute("SELECT active, role FROM users WHERE id = %s",
                                (corpo.assignee_id,)).fetchone()
            if dono is None or not dono["active"]:
                raise ErroDeNegocio("Responsável precisa ser um usuário ativo.",
                                    assignee_id=corpo.assignee_id)
        linha = conn.execute(
            """INSERT INTO tasks (opportunity_id, assignee_id, title, due_at, kind)
               VALUES (%s, %s, %s, %s, %s) RETURNING *""",
            (corpo.opportunity_id, corpo.assignee_id, corpo.title, corpo.due_at,
             corpo.kind)).fetchone()
        auditoria.registrar(conn, ator=ctx.ator, action="task.created", entity_type="task",
                            entity_id=str(linha["id"]), request_id=ctx.request_id,
                            changes={"kind": corpo.kind, "opportunity_id": corpo.opportunity_id})
        return 201, envelope(linha, ctx.request_id)

    return executar(ctx, "POST", "/v1/tasks", corpo.model_dump(mode="json"), acao)


@router.patch("/tasks/{tid}")
def alterar(tid: str, corpo: TarefaAlteracao, ctx: Contexto = Ctx):
    ctx.ator.exigir("tasks:write")
    esperada = protocolo.versao_do_if_match(ctx.if_match)

    def acao(conn):
        antes = conn.execute("SELECT * FROM tasks WHERE id = %s FOR UPDATE", (tid,)).fetchone()
        if antes is None:
            raise NaoEncontrado("Tarefa não encontrada.", task_id=tid)
        protocolo.conferir_versao(antes["version"], esperada)
        if antes["status"] in {"done", "cancelled"} and corpo.status not in (None, antes["status"]):
            raise ErroDeNegocio("Tarefa encerrada não volta a ser editada.", status=antes["status"])
        campos = {k: v for k, v in
                  {"status": corpo.status, "title": corpo.title, "due_at": corpo.due_at,
                   "assignee_id": corpo.assignee_id}.items() if v is not None}
        if not campos:
            return 200, envelope(antes, ctx.request_id)
        atribuicoes = ", ".join(f"{k} = %s" for k in campos)
        depois = conn.execute(
            f"UPDATE tasks SET {atribuicoes}, updated_at = now(), version = version + 1 "
            f"WHERE id = %s RETURNING *", [*campos.values(), tid]).fetchone()
        auditoria.registrar(conn, ator=ctx.ator, action="task.updated", entity_type="task",
                            entity_id=tid, request_id=ctx.request_id,
                            changes=auditoria.diferenca(dict(antes), dict(depois)))
        return 200, envelope(depois, ctx.request_id)

    return executar(ctx, "PATCH", f"/v1/tasks/{tid}", corpo.model_dump(mode="json"), acao,
                    exigir_chave=False)
