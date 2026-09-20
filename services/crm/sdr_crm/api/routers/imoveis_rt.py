"""Catálogo de imóveis e agenda de disponibilidade."""
from fastapi import APIRouter, Response

from ...db.connection import leitura
from ...dominio import custos
from ...erros import ErroDeNegocio, NaoEncontrado
from .. import auditoria, protocolo
from ..contexto import Contexto, Ctx, envelope, executar
from ..esquemas import FotosImovel, ImovelNovo, SituacaoImovel, SlotNovo

router = APIRouter(tags=["imoveis"])


def _fotos(conn, ids: list[str]) -> dict[str, list[dict]]:
    """Fotos de vários imóveis numa consulta só.

    Numa por imóvel seriam 100 idas ao banco para montar uma página de catálogo — e é o agente que
    pagina esse catálogo a cada reindexação. `ORDER BY position` porque a primeira é a capa: sem
    ordenar, a capa muda sozinha entre duas consultas.
    """
    if not ids:
        return {}
    linhas = conn.execute(
        """SELECT property_id, url, alt, position FROM property_photos
            WHERE property_id = ANY(%s) ORDER BY property_id, position, created_at""",
        (ids,)).fetchall()
    saida: dict[str, list[dict]] = {}
    for r in linhas:
        saida.setdefault(str(r["property_id"]), []).append(
            {"url": r["url"], "alt": r["alt"], "position": r["position"]})
    return saida


def _procura(conn, ids: list[str]) -> dict[str, int]:
    """Quantos clientes DIFERENTES demonstraram interesse em cada imóvel.

    Dois clientes no mesmo imóvel é normal e permitido — interesse não é posse, e a disputa real
    acontece só no horário, resolvida pelo índice único das visitas. Mas ninguém avisa o corretor
    de que três pessoas estão de olho no mesmo lugar, e isso muda a conversa e a prioridade.

    Conta só `presented` e `interested`: quem descartou o imóvel não é procura, é o contrário.
    """
    if not ids:
        return {}
    linhas = conn.execute(
        """SELECT property_id, count(DISTINCT opportunity_id) AS n FROM property_interests
            WHERE property_id = ANY(%s) AND status IN ('presented', 'interested')
            GROUP BY property_id""", (ids,)).fetchall()
    return {str(r["property_id"]): int(r["n"]) for r in linhas}


def _com_custos(linha: dict) -> dict:
    """Todo imóvel sai com os custos discriminados, nunca só com um total.

    Discriminar é o que permite a conversa acontecer: "R$ 4.000" não responde "por que é mais caro
    que o anúncio", e "aluguel 3.000 + condomínio 800 + IPTU 200" responde.
    """
    return {**linha, **custos.calcular(linha).para_json()}


@router.get("/properties")
def listar(ctx: Contexto = Ctx, code: str | None = None,
           purpose: str | None = None, city: str | None = None,
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
    # `code` é a chave que um sistema externo já conhece — é assim que a Mora resolve `SP-0001`
    # para o id do imóvel aqui, sem nenhum dos dois lados ter de adivinhar o do outro. Procurar
    # por código ignora o filtro de status: quem pergunta por um código específico quer AQUELE
    # imóvel, inclusive para descobrir que ele está indisponível.
    if code:
        onde.append("code = %s")
        valores.append(code)
        status = None
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
        ids = [str(x["id"]) for x in linhas]
        fotos, procura = _fotos(conn, ids), _procura(conn, ids)

    itens = [{**_com_custos(x), "photos": fotos.get(str(x["id"]), []),
              "interested_count": procura.get(str(x["id"]), 0)} for x in linhas]
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
        fotos = _fotos(conn, [pid]) if linha is not None else {}
        procura = _procura(conn, [pid]) if linha is not None else {}
    if linha is None:
        raise NaoEncontrado("Imóvel não encontrado.", property_id=pid)
    resposta.headers["ETag"] = protocolo.etag(linha["version"])
    return envelope({**_com_custos(linha), "photos": fotos.get(pid, []),
                     "interested_count": procura.get(pid, 0)}, ctx.request_id)


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
        # Na MESMA transação do imóvel: cadastro que grava o registro e perde as fotos deixaria um
        # imóvel mudo na vitrine sem ninguém saber que faltou alguma coisa.
        _gravar_fotos(conn, str(linha["id"]), corpo.photos)
        auditoria.registrar(conn, ator=ctx.ator, action="property.created", entity_type="property",
                            entity_id=str(linha["id"]), request_id=ctx.request_id,
                            changes={"code": corpo.code, "photos": len(corpo.photos)})
        return 201, envelope({**_com_custos(linha),
                              "photos": _fotos(conn, [str(linha["id"])]).get(str(linha["id"]), [])},
                             ctx.request_id)

    return executar(ctx, "POST", "/v1/properties", corpo.model_dump(mode="json"), acao)


def _gravar_fotos(conn, pid: str, fotos) -> None:
    """Substitui a lista inteira. A posição vem do ÍNDICE, não de um campo que o cliente manda:
    quem reordena arrastando manda a lista na ordem nova, e deixar a posição por conta de quem
    chama abriria espaço para duas fotos na mesma posição — e aí a capa vira sorteio."""
    conn.execute("DELETE FROM property_photos WHERE property_id = %s", (pid,))
    for posicao, f in enumerate(fotos):
        conn.execute(
            "INSERT INTO property_photos (property_id, url, alt, position) VALUES (%s,%s,%s,%s)",
            (pid, f.url, f.alt, posicao))


@router.put("/properties/{pid}/status")
def mudar_situacao(pid: str, corpo: SituacaoImovel, ctx: Contexto = Ctx):
    """Tira o imóvel de circulação, ou devolve ao catálogo.

    **Por que não é automático a partir do `won` da oportunidade.** São sistemas diferentes: a
    oportunidade é do cliente, o imóvel é do acervo — e um imóvel pode receber proposta de quem não
    tem oportunidade nenhuma no CRM. Amarrar os dois erra no primeiro caso fora do padrão, e erra
    para o lado ruim: sumindo com imóvel que ainda está à venda.

    **Os dois momentos.** `reserved` é a proposta aceita, antes da assinatura — é o que impede a
    Mora seguir oferecendo por semanas um imóvel que já tem dono definido. `unavailable` é a
    assinatura. E `reserved` VOLTA para `available` quando a proposta cai: situação que só anda
    para a frente faz o acervo minguar sozinho.

    **O efeito do outro lado é automático e não precisa de nada aqui.** `GET /v1/properties` filtra
    por `available`, então o imóvel deixa de chegar na reindexação e sai do índice da Mora no
    próximo ciclo. O agente não tem campo de situação: indisponível, para ele, é não existir.
    """
    ctx.ator.exigir_humano("mudar a situação do imóvel")

    def acao(conn):
        antes = conn.execute("SELECT * FROM properties WHERE id = %s FOR UPDATE", (pid,)).fetchone()
        if antes is None:
            raise NaoEncontrado("Imóvel não encontrado.", property_id=pid)
        if antes["status"] == corpo.status:
            raise ErroDeNegocio("O imóvel já está nesta situação.", status=corpo.status)
        # Visita CONFIRMADA no futuro é compromisso com uma pessoa que já reservou a tarde. Tirar o
        # imóvel do catálogo por baixo dela deixaria o corretor indo a um endereço para mostrar o
        # que não está mais à venda — e ninguém seria avisado. Cancelar primeiro é ato consciente.
        if corpo.status != "available":
            presas = conn.execute(
                """SELECT count(*) AS n FROM visits v JOIN availability_slots s ON s.id = v.slot_id
                    WHERE v.property_id = %s AND v.status = 'confirmed' AND s.starts_at > now()""",
                (pid,)).fetchone()["n"]
            if presas:
                raise ErroDeNegocio(
                    "Há visita confirmada no futuro para este imóvel. Cancele antes de tirá-lo do "
                    "catálogo.", visitas_confirmadas=int(presas))

        linha = conn.execute(
            """UPDATE properties SET status = %s, updated_at = now(), version = version + 1
                WHERE id = %s RETURNING *""", (corpo.status, pid)).fetchone()
        auditoria.registrar(conn, ator=ctx.ator, action="property.status_changed",
                            entity_type="property", entity_id=pid, request_id=ctx.request_id,
                            changes={"de": antes["status"], "para": corpo.status,
                                     "reason": corpo.reason})
        return 200, envelope({**_com_custos(linha), "photos": _fotos(conn, [pid]).get(pid, [])},
                             ctx.request_id)

    return executar(ctx, "PUT", f"/v1/properties/{pid}/status", corpo.model_dump(mode="json"), acao)


@router.put("/properties/{pid}/photos")
def substituir_fotos(pid: str, corpo: FotosImovel, ctx: Contexto = Ctx):
    """Substitui a galeria inteira — humano, como o cadastro.

    Substituir e não acrescentar porque a tela edita uma LISTA: quem tirou a terceira foto espera
    que ela suma, e um endpoint que só acrescenta obrigaria a inventar um DELETE por foto e a
    manter os dois em acordo.
    """
    ctx.ator.exigir_humano("alterar as fotos do imóvel")

    def acao(conn):
        linha = conn.execute("SELECT * FROM properties WHERE id = %s", (pid,)).fetchone()
        if linha is None:
            raise NaoEncontrado("Imóvel não encontrado.", property_id=pid)
        _gravar_fotos(conn, pid, corpo.photos)
        auditoria.registrar(conn, ator=ctx.ator, action="property.photos_replaced",
                            entity_type="property", entity_id=pid, request_id=ctx.request_id,
                            changes={"photos": len(corpo.photos)})
        return 200, envelope({**_com_custos(linha), "photos": _fotos(conn, [pid]).get(pid, [])},
                             ctx.request_id)

    return executar(ctx, "PUT", f"/v1/properties/{pid}/photos", corpo.model_dump(mode="json"), acao)


@router.get("/brokers")
def listar_corretores(ctx: Contexto = Ctx):
    """Quem pode receber um horário na agenda.

    Existe para a tela poder oferecer uma LISTA: sem ela, abrir horário exigiria digitar o uuid do
    corretor à mão, e um uuid digitado errado é um horário na agenda da pessoa errada.

    Só ativos e só quem o `POST /availability-slots` aceita (admin ou broker) — oferecer alguém que
    o servidor vai recusar é convidar o erro que a lista existia para evitar. Devolve nome e papel,
    nunca e-mail: é uma lista para escolher, não um diretório de contatos.
    """
    ctx.ator.exigir("crm:read")
    with leitura() as conn:
        linhas = conn.execute(
            """SELECT id, name, role FROM users
                WHERE active AND role IN ('admin', 'broker') ORDER BY name""").fetchall()
    return {"items": linhas, "next_cursor": None}


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
            f"""SELECT s.*, u.name AS broker_name,
                       EXISTS (SELECT 1 FROM visits v
                                WHERE v.slot_id = s.id AND v.status IN ('confirmed','completed'))
                           AS taken
                  FROM availability_slots s
                  JOIN users u ON u.id = s.broker_id
                 WHERE {' AND '.join(onde)} ORDER BY s.starts_at LIMIT %s""",
            [*valores, protocolo.limite(limit)]).fetchall()
    # `taken` só é informação quando `only_free` está desligado — e é aí que ele importa: a tela de
    # agenda precisa mostrar o horário ocupado, senão quem administra a agenda não vê o que
    # combinou e abre outro em cima.
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
