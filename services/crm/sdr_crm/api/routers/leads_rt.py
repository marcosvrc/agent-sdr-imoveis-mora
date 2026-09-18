"""Clientes e histórico de interação."""
from fastapi import APIRouter, Response

from ...dominio import contatos
from ...erros import ConflitoDeIdempotencia, LeadDuplicado, NaoEncontrado
from .. import auditoria, protocolo
from ..contexto import Contexto, Ctx, envelope, executar
from ..esquemas import InteracaoNova, LeadAlteracao, LeadNovo

router = APIRouter(tags=["leads"])

CAMPOS_RESUMO = "id, name, email, phone_e164, external_contact_id, source, contact_policy, archived_at, created_at, version"


def _lead(conn, lead_id: str, *, para_alterar: bool = False) -> dict:
    linha = conn.execute(
        f"SELECT * FROM leads WHERE id = %s {'FOR UPDATE' if para_alterar else ''}",
        (lead_id,)).fetchone()
    if linha is None:
        raise NaoEncontrado("Lead não encontrado.", lead_id=lead_id)
    return linha


def _procurar_por_identificadores(conn, ids: dict[str, str]) -> list[dict]:
    """Devolve os leads que casam com QUALQUER identificador informado.

    Mais de um resultado significa que e-mail e telefone apontam para pessoas diferentes — 409 e
    revisão humana, nunca merge automático (seção 5). Juntar dois históricos comerciais não tem
    desfazer: some a informação de quem disse o quê.
    """
    if not ids:
        return []
    onde, valores = [], []
    if "email" in ids:
        onde.append("lower(btrim(email)) = %s")
        valores.append(ids["email"])
    if "phone_e164" in ids:
        onde.append("phone_e164 = %s")
        valores.append(ids["phone_e164"])
    if "external_contact_id" in ids:
        onde.append("external_contact_id = %s")
        valores.append(ids["external_contact_id"])
    return conn.execute(f"SELECT * FROM leads WHERE {' OR '.join(onde)} ORDER BY created_at",
                        valores).fetchall()


@router.get("/leads")
def listar(ctx: Contexto = Ctx, email: str | None = None, phone: str | None = None,
           external_contact_id: str | None = None, name: str | None = None,
           include_archived: bool = False, limit: int | None = None, cursor: str | None = None):
    """Filtros exatos por identificador e busca por nome.

    Nome é `ILIKE`, e só serve para procurar — nunca para identificar. Arquivados ficam fora por
    padrão e continuam acessíveis por ID (seção 7).
    """
    ctx.ator.exigir("crm:read")
    onde, valores = ["true"], []
    if email:
        onde.append("lower(btrim(leads.email)) = %s")
        valores.append(contatos.normalizar_email(email))
    if phone:
        onde.append("phone_e164 = %s")
        valores.append(contatos.normalizar_telefone(phone))
    if external_contact_id:
        onde.append("external_contact_id = %s")
        valores.append(external_contact_id.strip())
    if name:
        onde.append("name ILIKE %s")
        valores.append(f"%{name.strip()}%")
    if not include_archived:
        onde.append("archived_at IS NULL")

    n = protocolo.limite(limit)
    if (marca := protocolo.decifrar_cursor(cursor)) is not None:
        onde.append("(created_at, id) < (%s, %s)")
        valores.extend(marca)

    from ...db.connection import leitura
    with leitura() as conn:
        linhas = conn.execute(
            f"SELECT {CAMPOS_RESUMO} FROM leads WHERE {' AND '.join(onde)} "
            f"ORDER BY created_at DESC, id DESC LIMIT %s", [*valores, n + 1]).fetchall()
    proximo = None
    if len(linhas) > n:
        linhas = linhas[:n]
        proximo = protocolo.cifrar_cursor(linhas[-1]["created_at"], linhas[-1]["id"])
    return {"items": linhas, "next_cursor": proximo}


@router.post("/leads", status_code=201)
def criar(corpo: LeadNovo, ctx: Contexto = Ctx):
    ctx.ator.exigir("leads:write")

    def acao(conn):
        ids = contatos.identificadores(
            {"email": corpo.email, "phone_e164": corpo.phone,
             "external_contact_id": corpo.external_contact_id})
        if not ids:
            # Chegou aqui com identificador sintaticamente presente mas inválido (telefone que não
            # vira E.164, por exemplo). 422 seria mentira: o corpo estava bem formado.
            raise ConflitoDeIdempotencia(
                "Nenhum identificador utilizável: verifique o formato do telefone ou do e-mail.")

        existentes = _procurar_por_identificadores(conn, ids)
        if len({str(x["id"]) for x in existentes}) > 1:
            raise LeadDuplicado(
                "Os identificadores informados apontam para clientes diferentes — revise à mão.",
                lead_ids=[str(x["id"]) for x in existentes])
        if existentes:
            # Cliente que volta: devolve o que já existe em vez de criar um segundo cadastro. 200,
            # e não 201, para o chamador saber que não nasceu nada.
            return 200, envelope(existentes[0], ctx.request_id)

        linha = conn.execute(
            """INSERT INTO leads (name, email, phone_e164, external_contact_id, source,
                                  contact_policy, synthetic)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (corpo.name.strip(), ids.get("email"), ids.get("phone_e164"),
             ids.get("external_contact_id"), corpo.source.strip(), corpo.contact_policy,
             corpo.synthetic)).fetchone()
        auditoria.registrar(conn, ator=ctx.ator, action="lead.created", entity_type="lead",
                            entity_id=str(linha["id"]), request_id=ctx.request_id,
                            changes={"source": corpo.source, "identificadores": sorted(ids)})
        return 201, envelope(linha, ctx.request_id)

    return executar(ctx, "POST", "/v1/leads", corpo.model_dump(mode="json"), acao)


@router.get("/leads/{lead_id}")
def detalhe(lead_id: str, resposta: Response, ctx: Contexto = Ctx):
    ctx.ator.exigir("crm:read")
    from ...db.connection import leitura
    with leitura() as conn:
        linha = _lead(conn, lead_id)
        oportunidades = conn.execute(
            "SELECT id, purpose, stage, atendimento, version FROM opportunities "
            "WHERE lead_id = %s ORDER BY created_at", (lead_id,)).fetchall()
    resposta.headers["ETag"] = protocolo.etag(linha["version"])
    return envelope({**linha, "opportunities": oportunidades}, ctx.request_id)


@router.patch("/leads/{lead_id}")
def alterar(lead_id: str, corpo: LeadAlteracao, ctx: Contexto = Ctx):
    ctx.ator.exigir("leads:write")
    esperada = protocolo.versao_do_if_match(ctx.if_match)

    def acao(conn):
        antes = _lead(conn, lead_id, para_alterar=True)
        protocolo.conferir_versao(antes["version"], esperada)

        campos: dict[str, object] = {}
        if corpo.name is not None:
            campos["name"] = corpo.name.strip()
        if corpo.email is not None:
            campos["email"] = contatos.normalizar_email(corpo.email)
        if corpo.phone is not None:
            campos["phone_e164"] = contatos.normalizar_telefone(corpo.phone)

        if corpo.contact_policy is not None and corpo.contact_policy != antes["contact_policy"]:
            # O agente PODE bloquear a pedido do cliente e não pode desbloquear nem promover
            # `unknown` para `allowed` (seção 4). Permissão de contato tem de vir com evidência
            # humana — é o tipo de mudança que ninguém consegue desfazer depois de uma mensagem
            # indevida ter saído.
            if corpo.contact_policy != "blocked":
                ctx.ator.exigir_humano("liberar contato")
            campos["contact_policy"] = corpo.contact_policy

        if corpo.archived is not None:
            ctx.ator.exigir_humano("arquivar cliente")
            campos["archived_at"] = "now()" if corpo.archived else None

        if not campos:
            return 200, envelope(antes, ctx.request_id)

        atribuicoes = ", ".join(
            f"{k} = now()" if v == "now()" else f"{k} = %s" for k, v in campos.items())
        valores = [v for v in campos.values() if v != "now()"]
        depois = conn.execute(
            f"UPDATE leads SET {atribuicoes}, updated_at = now(), version = version + 1 "
            f"WHERE id = %s RETURNING *", [*valores, lead_id]).fetchone()
        auditoria.registrar(conn, ator=ctx.ator, action="lead.updated", entity_type="lead",
                            entity_id=lead_id, request_id=ctx.request_id,
                            changes=auditoria.diferenca(dict(antes), dict(depois)))
        return 200, envelope(depois, ctx.request_id)

    return executar(ctx, "PATCH", f"/v1/leads/{lead_id}", corpo.model_dump(mode="json"), acao,
                    exigir_chave=False)


@router.get("/leads/{lead_id}/interactions")
def historico(lead_id: str, ctx: Contexto = Ctx, limit: int | None = None, cursor: str | None = None):
    ctx.ator.exigir("crm:read")
    n = protocolo.limite(limit)
    onde, valores = ["lead_id = %s"], [lead_id]
    if (marca := protocolo.decifrar_cursor(cursor)) is not None:
        onde.append("(occurred_at, id) < (%s, %s)")
        valores.extend(marca)
    from ...db.connection import leitura
    with leitura() as conn:
        _lead(conn, lead_id)
        linhas = conn.execute(
            f"SELECT * FROM interactions WHERE {' AND '.join(onde)} "
            f"ORDER BY occurred_at DESC, id DESC LIMIT %s", [*valores, n + 1]).fetchall()
    proximo = None
    if len(linhas) > n:
        linhas = linhas[:n]
        proximo = protocolo.cifrar_cursor(linhas[-1]["occurred_at"], linhas[-1]["id"])
    return {"items": linhas, "next_cursor": proximo}


@router.post("/leads/{lead_id}/interactions", status_code=201)
def registrar_interacao(lead_id: str, corpo: InteracaoNova, ctx: Contexto = Ctx):
    """Registrar o que ENTROU é sempre permitido — inclusive com contato bloqueado e com o
    atendimento em mãos humanas. Bloqueio impede contato ativo, não impede ouvir o cliente; perder
    a mensagem de quem pediu para não ser incomodado seria o pior dos dois mundos."""
    ctx.ator.exigir("interactions:write")

    def acao(conn):
        _lead(conn, lead_id)
        if corpo.external_event_id:
            ja = conn.execute(
                "SELECT * FROM interactions WHERE channel = %s AND external_event_id = %s",
                (corpo.channel, corpo.external_event_id)).fetchone()
            if ja is not None:
                # Mesmo evento reentregue pelo canal: devolve o registro original. Sem isto, uma
                # reentrega do Telegram viraria duas linhas no histórico do cliente.
                return 200, envelope(ja, ctx.request_id)
        if corpo.opportunity_id:
            dona = conn.execute("SELECT lead_id FROM opportunities WHERE id = %s",
                                (corpo.opportunity_id,)).fetchone()
            if dona is None or str(dona["lead_id"]) != lead_id:
                raise NaoEncontrado("Oportunidade não pertence a este lead.",
                                    opportunity_id=corpo.opportunity_id)
        linha = conn.execute(
            """INSERT INTO interactions (lead_id, opportunity_id, channel, direction, summary,
                                         external_event_id, occurred_at, actor_type, actor_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *""",
            (lead_id, corpo.opportunity_id, corpo.channel, corpo.direction, corpo.summary,
             corpo.external_event_id, corpo.occurred_at, ctx.ator.tipo, ctx.ator.id)).fetchone()
        return 201, envelope(linha, ctx.request_id)

    return executar(ctx, "POST", f"/v1/leads/{lead_id}/interactions",
                    corpo.model_dump(mode="json"), acao)

