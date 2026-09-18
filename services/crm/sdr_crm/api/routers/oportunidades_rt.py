"""Oportunidades: preferências, transições do funil e interesse em imóveis."""
from fastapi import APIRouter, Response

from ...db.connection import leitura
from ...dominio import funil
from ...erros import (
    AtendimentoHumano,
    ErroDeNegocio,
    NaoEncontrado,
    QualificacaoIncompleta,
    SemPermissao,
    TransicaoInvalida,
)
from .. import auditoria, protocolo
from ..contexto import Contexto, Ctx, envelope, executar
from ..esquemas import Interesse, OportunidadeNova, Preferencias, Transicao

router = APIRouter(tags=["oportunidades"])

# O `code` do veredito do domínio vira a exceção HTTP certa. Tabela, e não `if`, porque assim um
# código novo no domínio sem tradução aqui falha alto (KeyError no teste) em vez de virar 409 genérico.
POR_CODIGO = {
    "INVALID_TRANSITION": TransicaoInvalida,
    "QUALIFICATION_INCOMPLETE": QualificacaoIncompleta,
    "HUMAN_IN_CONTROL": AtendimentoHumano,
    "FORBIDDEN": SemPermissao,
    "REASON_REQUIRED": ErroDeNegocio,
    "VISIT_NOT_CONFIRMED": ErroDeNegocio,
}


def _oportunidade(conn, oid: str, *, para_alterar: bool = False) -> dict:
    linha = conn.execute(
        f"SELECT * FROM opportunities WHERE id = %s {'FOR UPDATE' if para_alterar else ''}",
        (oid,)).fetchone()
    if linha is None:
        raise NaoEncontrado("Oportunidade não encontrada.", opportunity_id=oid)
    return linha


def _preferencias(conn, oid: str) -> dict:
    return conn.execute("SELECT * FROM preferences WHERE opportunity_id = %s", (oid,)).fetchone() or {}


def _tem_visita_confirmada_futura(conn, oid: str) -> bool:
    linha = conn.execute(
        """SELECT count(*) AS n FROM visits v JOIN availability_slots s ON s.id = v.slot_id
            WHERE v.opportunity_id = %s AND v.status = 'confirmed' AND s.starts_at > now()""",
        (oid,)).fetchone()
    return linha["n"] > 0


def _contexto_funil(conn, op: dict) -> funil.Contexto:
    return funil.Contexto(stage=op["stage"], purpose=op["purpose"], atendimento=op["atendimento"],
                          preferencias=dict(_preferencias(conn, str(op["id"]))),
                          tem_visita_confirmada_futura=_tem_visita_confirmada_futura(conn, str(op["id"])))


@router.get("/opportunities")
def listar(ctx: Contexto = Ctx, stage: str | None = None, owner_id: str | None = None,
           lead_id: str | None = None, limit: int | None = None, cursor: str | None = None):
    ctx.ator.exigir("crm:read")
    onde, valores = ["true"], []
    for coluna, valor in (("stage", stage), ("owner_id", owner_id), ("lead_id", lead_id)):
        if valor:
            onde.append(f"{coluna} = %s")
            valores.append(valor)
    n = protocolo.limite(limit)
    if (marca := protocolo.decifrar_cursor(cursor)) is not None:
        onde.append("(created_at, id) < (%s, %s)")
        valores.extend(marca)
    with leitura() as conn:
        linhas = conn.execute(
            f"SELECT * FROM opportunities WHERE {' AND '.join(onde)} "
            f"ORDER BY created_at DESC, id DESC LIMIT %s", [*valores, n + 1]).fetchall()
    proximo = None
    if len(linhas) > n:
        linhas = linhas[:n]
        proximo = protocolo.cifrar_cursor(linhas[-1]["created_at"], linhas[-1]["id"])
    return {"items": linhas, "next_cursor": proximo}


@router.post("/opportunities", status_code=201)
def criar(corpo: OportunidadeNova, ctx: Contexto = Ctx):
    ctx.ator.exigir("opportunities:write")

    def acao(conn):
        lead = conn.execute("SELECT * FROM leads WHERE id = %s", (corpo.lead_id,)).fetchone()
        if lead is None:
            raise NaoEncontrado("Lead não encontrado.", lead_id=corpo.lead_id)
        if lead["archived_at"] is not None:
            # Arquivado continua acessível por ID e não recebe oportunidade nova (seção 7).
            # Desarquivar é ato humano — e é ele que deve preceder qualquer atendimento novo.
            raise ErroDeNegocio("Lead arquivado não recebe novas oportunidades.",
                                lead_id=corpo.lead_id)
        linha = conn.execute(
            "INSERT INTO opportunities (lead_id, owner_id, purpose) VALUES (%s, %s, %s) RETURNING *",
            (corpo.lead_id, corpo.owner_id, corpo.purpose)).fetchone()
        # Linha de preferências nasce junto, vazia: assim `PUT /preferences` é sempre substituição
        # e nunca precisa decidir entre inserir e atualizar.
        conn.execute("INSERT INTO preferences (opportunity_id) VALUES (%s)", (linha["id"],))
        auditoria.registrar(conn, ator=ctx.ator, action="opportunity.created",
                            entity_type="opportunity", entity_id=str(linha["id"]),
                            request_id=ctx.request_id,
                            changes={"lead_id": corpo.lead_id, "purpose": corpo.purpose})
        return 201, envelope(linha, ctx.request_id)

    return executar(ctx, "POST", "/v1/opportunities", corpo.model_dump(mode="json"), acao)


@router.get("/opportunities/{oid}")
def detalhe(oid: str, resposta: Response, ctx: Contexto = Ctx):
    ctx.ator.exigir("crm:read")
    with leitura() as conn:
        op = _oportunidade(conn, oid)
        prefs = _preferencias(conn, oid)
        interesses = conn.execute(
            """SELECT i.*, p.code, p.title, p.status AS property_status
                 FROM property_interests i JOIN properties p ON p.id = i.property_id
                WHERE i.opportunity_id = %s ORDER BY i.created_at""", (oid,)).fetchall()
        visitas = conn.execute(
            """SELECT v.*, s.starts_at, s.ends_at FROM visits v
                 JOIN availability_slots s ON s.id = v.slot_id
                WHERE v.opportunity_id = %s ORDER BY s.starts_at""", (oid,)).fetchall()
        tarefas = conn.execute("SELECT * FROM tasks WHERE opportunity_id = %s ORDER BY due_at",
                               (oid,)).fetchall()
        handoffs = conn.execute("SELECT * FROM handoffs WHERE opportunity_id = %s ORDER BY created_at",
                                (oid,)).fetchall()
    resposta.headers["ETag"] = protocolo.etag(op["version"])
    return envelope({**op, "preferences": prefs or None, "interests": interesses,
                     "visits": visitas, "tasks": tarefas, "handoffs": handoffs}, ctx.request_id)


@router.put("/opportunities/{oid}/preferences")
def salvar_preferencias(oid: str, corpo: Preferencias, ctx: Contexto = Ctx):
    """Substituição completa, com a versão da OPORTUNIDADE como precondição.

    A versão é a da oportunidade, e não uma da tabela de preferências, porque é a oportunidade que
    o cliente leu e é o ETag dela que ele tem na mão (seção 8). Duas tabelas com dois contadores
    obrigariam o agente a acompanhar duas versões do mesmo agregado.
    """
    ctx.ator.exigir("opportunities:write")
    esperada = protocolo.versao_do_if_match(ctx.if_match)

    def acao(conn):
        op = _oportunidade(conn, oid, para_alterar=True)
        protocolo.conferir_versao(op["version"], esperada)
        if op["atendimento"] in {"human_pending", "human"} and not ctx.ator.humano:
            raise AtendimentoHumano("O atendimento está com um corretor.")
        if corpo.budget_basis == "monthly_total" and op["purpose"] != "rent":
            raise ErroDeNegocio("budget_basis='monthly_total' só existe para aluguel.",
                                purpose=op["purpose"])
        antes = dict(_preferencias(conn, oid))
        depois = conn.execute(
            """INSERT INTO preferences (opportunity_id, city, neighborhoods, property_types,
                   budget_min_cents, budget_max_cents, budget_basis, bedrooms_min, parking_min,
                   move_by, requirements, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
               ON CONFLICT (opportunity_id) DO UPDATE SET
                   city = EXCLUDED.city, neighborhoods = EXCLUDED.neighborhoods,
                   property_types = EXCLUDED.property_types,
                   budget_min_cents = EXCLUDED.budget_min_cents,
                   budget_max_cents = EXCLUDED.budget_max_cents,
                   budget_basis = EXCLUDED.budget_basis, bedrooms_min = EXCLUDED.bedrooms_min,
                   parking_min = EXCLUDED.parking_min, move_by = EXCLUDED.move_by,
                   requirements = EXCLUDED.requirements, updated_at = now()
               RETURNING *""",
            (oid, corpo.city, corpo.neighborhoods, corpo.property_types, corpo.budget_min_cents,
             corpo.budget_max_cents, corpo.budget_basis, corpo.bedrooms_min, corpo.parking_min,
             corpo.move_by, corpo.requirements)).fetchone()
        nova = conn.execute(
            "UPDATE opportunities SET version = version + 1, updated_at = now() "
            "WHERE id = %s RETURNING version", (oid,)).fetchone()
        auditoria.registrar(conn, ator=ctx.ator, action="preferences.replaced",
                            entity_type="opportunity", entity_id=oid, request_id=ctx.request_id,
                            changes=auditoria.diferenca(antes, dict(depois)))
        return 200, envelope({**depois, "opportunity_version": nova["version"]}, ctx.request_id)

    return executar(ctx, "PUT", f"/v1/opportunities/{oid}/preferences",
                    corpo.model_dump(mode="json"), acao, exigir_chave=False)


@router.post("/opportunities/{oid}/transitions")
def transicionar(oid: str, corpo: Transicao, ctx: Contexto = Ctx):
    ctx.ator.exigir("opportunities:write")
    # A versão é lida ANTES, mas conferida DEPOIS do replay de idempotência (ver `executar`): a
    # repetição de uma transição já aplicada devolve o resultado original em vez de 412.
    esperada = protocolo.versao_do_if_match(ctx.if_match)

    def acao(conn):
        op = _oportunidade(conn, oid, para_alterar=True)
        protocolo.conferir_versao(op["version"], esperada)
        veredito = funil.avaliar(_contexto_funil(conn, op), corpo.target_stage,
                                 humano=ctx.ator.humano, motivo=corpo.reason)
        if not veredito.ok:
            erro = POR_CODIGO[veredito.code]
            excecao = erro(veredito.mensagem, **(veredito.detalhes or {}))
            if erro is ErroDeNegocio:
                excecao.code = veredito.code
            raise excecao

        fecha = corpo.target_stage in {"won", "lost"}
        depois = conn.execute(
            """UPDATE opportunities
                  SET stage = %s,
                      lost_reason = CASE WHEN %s = 'lost' THEN %s ELSE NULL END,
                      closed_at = CASE WHEN %s THEN now() ELSE NULL END,
                      updated_at = now(), version = version + 1
                WHERE id = %s RETURNING *""",
            (corpo.target_stage, corpo.target_stage, corpo.reason, fecha, oid)).fetchone()
        auditoria.registrar(conn, ator=ctx.ator, action="opportunity.transitioned",
                            entity_type="opportunity", entity_id=oid, request_id=ctx.request_id,
                            changes={"de": op["stage"], "para": corpo.target_stage,
                                     "motivo": corpo.reason})
        return 200, envelope(depois, ctx.request_id)

    return executar(ctx, "POST", f"/v1/opportunities/{oid}/transitions",
                    corpo.model_dump(mode="json"), acao)


@router.put("/opportunities/{oid}/interests/{property_id}")
def registrar_interesse(oid: str, property_id: str, corpo: Interesse, ctx: Contexto = Ctx):
    ctx.ator.exigir("opportunities:write")
    esperada = protocolo.versao_do_if_match(ctx.if_match)

    def acao(conn):
        op = _oportunidade(conn, oid, para_alterar=True)
        protocolo.conferir_versao(op["version"], esperada)
        imovel = conn.execute("SELECT * FROM properties WHERE id = %s", (property_id,)).fetchone()
        if imovel is None:
            raise NaoEncontrado("Imóvel não encontrado.", property_id=property_id)
        if imovel["purpose"] != op["purpose"]:
            # Associar um imóvel de venda a uma oportunidade de aluguel é sempre engano, e é o tipo
            # de engano que só aparece na frente do cliente.
            raise ErroDeNegocio("Imóvel e oportunidade têm propósitos diferentes.",
                                property_purpose=imovel["purpose"], opportunity_purpose=op["purpose"])
        linha = conn.execute(
            """INSERT INTO property_interests (opportunity_id, property_id, status, notes)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (opportunity_id, property_id)
               DO UPDATE SET status = EXCLUDED.status, notes = EXCLUDED.notes, updated_at = now()
               RETURNING *""", (oid, property_id, corpo.status, corpo.notes)).fetchone()
        nova = conn.execute(
            "UPDATE opportunities SET version = version + 1, updated_at = now() "
            "WHERE id = %s RETURNING version", (oid,)).fetchone()
        auditoria.registrar(conn, ator=ctx.ator, action="interest.recorded",
                            entity_type="opportunity", entity_id=oid, request_id=ctx.request_id,
                            changes={"property_id": property_id, "status": corpo.status})
        return 200, envelope({**linha, "opportunity_version": nova["version"]}, ctx.request_id)

    return executar(ctx, "PUT", f"/v1/opportunities/{oid}/interests/{property_id}",
                    corpo.model_dump(mode="json"), acao, exigir_chave=False)
