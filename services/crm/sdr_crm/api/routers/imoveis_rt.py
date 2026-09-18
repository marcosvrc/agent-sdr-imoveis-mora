"""Catálogo de imóveis e agenda de disponibilidade."""
from fastapi import APIRouter, Response

from ...db.connection import leitura
from ...dominio import custos
from ...erros import ErroDeNegocio, NaoEncontrado
from .. import auditoria, protocolo
from ..contexto import Contexto, Ctx, envelope, executar
from ..esquemas import ImovelNovo, SlotNovo

router = APIRouter(tags=["imoveis"])


def _com_custos(linha: dict) -> dict:
    """Todo imóvel sai com os custos discriminados, nunca só com um total.

    Discriminar é o que permite a conversa acontecer: "R$ 4.000" não responde "por que é mais caro
    que o anúncio", e "aluguel 3.000 + condomínio 800 + IPTU 200" responde.
    """
    return {**linha, **custos.calcular(linha).para_json()}


@router.get("/properties")
def listar(ctx: Contexto = Ctx, purpose: str | None = None, city: str | None = None,
           neighborhood: str | None = None, bedrooms_min: int | None = None,
           parking_min: int | None = None, max_price_cents: int | None = None,
           budget_basis: str = "base_price", status: str | None = "available",
           limit: int | None = None, cursor: str | None = None):
    """O filtro de preço é aplicado em Python, não em SQL, quando a base é `monthly_total`.

    Motivo: o total mensal pode ser DESCONHECIDO, e SQL não tem como devolver "não dá para afirmar".
    Uma comparação em SQL trataria o nulo como falso e sumiria com o imóvel silenciosamente — que é
    exatamente o que a seção 6 proíbe. Aqui ele aparece marcado como incompleto.
    """
    ctx.ator.exigir("crm:read")
    onde, valores = ["true"], []
    for coluna, valor in (("purpose", purpose), ("city", city), ("neighborhood", neighborhood),
                          ("status", status)):
        if valor:
            onde.append(f"{coluna} = %s")
            valores.append(valor)
    if bedrooms_min is not None:
        onde.append("bedrooms >= %s")
        valores.append(bedrooms_min)
    if parking_min is not None:
        onde.append("parking >= %s")
        valores.append(parking_min)
    if max_price_cents is not None and budget_basis == "base_price":
        onde.append("base_price_cents <= %s")
        valores.append(max_price_cents)

    n = protocolo.limite(limit)
    if (marca := protocolo.decifrar_cursor(cursor)) is not None:
        onde.append("(created_at, id) < (%s, %s)")
        valores.extend(marca)

    with leitura() as conn:
        linhas = conn.execute(
            f"SELECT * FROM properties WHERE {' AND '.join(onde)} "
            f"ORDER BY created_at DESC, id DESC LIMIT %s", [*valores, n + 1]).fetchall()

    itens = [_com_custos(x) for x in linhas]
    if max_price_cents is not None and budget_basis == "monthly_total":
        itens = [x for x in itens
                 if custos.cabe_no_orcamento(x, max_price_cents, "monthly_total") is not False]
    proximo = None
    if len(itens) > n:
        itens = itens[:n]
        proximo = protocolo.cifrar_cursor(linhas[n - 1]["created_at"], linhas[n - 1]["id"])
    return {"items": itens, "next_cursor": proximo}


@router.get("/properties/{pid}")
def detalhe(pid: str, resposta: Response, ctx: Contexto = Ctx):
    ctx.ator.exigir("crm:read")
    with leitura() as conn:
        linha = conn.execute("SELECT * FROM properties WHERE id = %s", (pid,)).fetchone()
    if linha is None:
        raise NaoEncontrado("Imóvel não encontrado.", property_id=pid)
    resposta.headers["ETag"] = protocolo.etag(linha["version"])
    return envelope(_com_custos(linha), ctx.request_id)


@router.post("/properties", status_code=201)
def criar(corpo: ImovelNovo, ctx: Contexto = Ctx):
    """Administração do catálogo: humana. O agente lê o catálogo e não o escreve — cadastro de
    imóvel vindo de uma conversa seria o caminho mais curto para um anúncio inventado."""
    ctx.ator.exigir_humano("cadastrar imóvel")

    def acao(conn):
        if conn.execute("SELECT 1 FROM properties WHERE code = %s", (corpo.code,)).fetchone():
            raise ErroDeNegocio("Já existe imóvel com este código.", code=corpo.code)
        linha = conn.execute(
            """INSERT INTO properties (code, title, description, city, neighborhood, type, purpose,
                   base_price_cents, condo_monthly_cents, property_tax_monthly_cents,
                   other_monthly_cents, bedrooms, parking, area_m2, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (corpo.code, corpo.title, corpo.description, corpo.city, corpo.neighborhood,
             corpo.type, corpo.purpose, corpo.base_price_cents, corpo.condo_monthly_cents,
             corpo.property_tax_monthly_cents, corpo.other_monthly_cents, corpo.bedrooms,
             corpo.parking, corpo.area_m2, corpo.status)).fetchone()
        auditoria.registrar(conn, ator=ctx.ator, action="property.created", entity_type="property",
                            entity_id=str(linha["id"]), request_id=ctx.request_id,
                            changes={"code": corpo.code})
        return 201, envelope(_com_custos(linha), ctx.request_id)

    return executar(ctx, "POST", "/v1/properties", corpo.model_dump(mode="json"), acao)


@router.get("/availability-slots")
def listar_slots(ctx: Contexto = Ctx, property_id: str | None = None, from_: str | None = None,
                 to: str | None = None, only_free: bool = True, limit: int | None = None):
    """Horários do imóvel no período. Com `only_free`, esconde os que já têm visita confirmada.

    "Livre" aqui é ausência de confirmação — solicitação não ocupa nada (seção 6). Se solicitar
    reservasse, um agente conseguiria bloquear a agenda inteira de um corretor sem nenhum cliente
    do outro lado.
    """
    ctx.ator.exigir("crm:read")
    onde, valores = ["true"], []
    if property_id:
        onde.append("s.property_id = %s")
        valores.append(property_id)
    if from_:
        onde.append("s.starts_at >= %s")
        valores.append(from_)
    if to:
        onde.append("s.ends_at <= %s")
        valores.append(to)
    if only_free:
        onde.append("""NOT EXISTS (SELECT 1 FROM visits v
                                    WHERE v.slot_id = s.id AND v.status IN ('confirmed','completed'))""")
    with leitura() as conn:
        linhas = conn.execute(
            f"""SELECT s.*, u.name AS broker_name FROM availability_slots s
                  JOIN users u ON u.id = s.broker_id
                 WHERE {' AND '.join(onde)} ORDER BY s.starts_at LIMIT %s""",
            [*valores, protocolo.limite(limit)]).fetchall()
    return {"items": linhas, "next_cursor": None}


@router.post("/availability-slots", status_code=201)
def criar_slot(corpo: SlotNovo, ctx: Contexto = Ctx):
    ctx.ator.exigir_humano("abrir horário na agenda")

    def acao(conn):
        corretor = conn.execute("SELECT * FROM users WHERE id = %s", (corpo.broker_id,)).fetchone()
        if corretor is None or not corretor["active"] or corretor["role"] not in {"admin", "broker"}:
            raise ErroDeNegocio("Horário precisa de um corretor ativo.", broker_id=corpo.broker_id)
        try:
            linha = conn.execute(
                """INSERT INTO availability_slots (property_id, broker_id, starts_at, ends_at)
                   VALUES (%s, %s, %s, %s) RETURNING *""",
                (corpo.property_id, corpo.broker_id, corpo.starts_at, corpo.ends_at)).fetchone()
        except Exception as exc:
            if "availability_sem_sobreposicao" in str(exc):
                raise ErroDeNegocio("O corretor já tem horário neste intervalo.",
                                    broker_id=corpo.broker_id)
            raise
        return 201, envelope(linha, ctx.request_id)

    return executar(ctx, "POST", "/v1/availability-slots", corpo.model_dump(mode="json"), acao)
