"""Busca imóveis (RAG híbrido) e explica por que combinam."""
import logging
import re

from langchain_core.messages import AIMessage

from sdr_shared.db import InteresseRepository
from sdr_shared.messaging import RespostaAgente
from sdr_shared.models import Estagio
from ..llm import llm_conversa
from ..prompts import carregar
from ..state import AgentState
from ..tools.buscar_imoveis import buscar_com_contexto
from ..guardrails.saida import sanear

log = logging.getLogger("agent.consultor")


def _linha(c, fichas: dict) -> str:
    """Uma linha de imóvel para o prompt: identidade, preço, FATOS e por que casa com o cartão.

    Antes ia só `id · título · preço · descrição do anúncio truncada`, e o prompt pedia "um
    diferencial de cada" — o modelo tinha de inventar o diferencial ou repetir o anunciante. Os
    fatos vêm do banco e os motivos do mesmo cálculo determinístico da reativação (ADR-0013).
    """
    f = fichas.get(c.id) or {}
    partes = [f"- {c.id}: {c.titulo} — R$ {c.preco:,.0f}"]
    if f.get("ficha"):
        partes.append(f["ficha"])
    if f.get("motivos"):
        partes.append("casa porque: " + "; ".join(f["motivos"]))
    elif c.motivo:
        partes.append(c.motivo)
    return " — ".join(partes)


def _contexto_da_busca(busca: dict, cards: list) -> str:
    """Traduz o nível da cascata em instrução explícita — a fonte da verdade sobre o que foi encontrado."""
    pedidos = ", ".join(busca["bairros_pedidos"]) or "a região pedida"
    achados = ", ".join(busca["bairros_encontrados"])
    alt = busca.get("alternativa_no_bairro") or []
    sugestao_alt = ("" if not alt else
                    f" Em {pedidos} existem estas opções FORA do perfil pedido: "
                    + "; ".join(f"{c.titulo} por R$ {c.preco:,.0f}" for c in alt[:2])
                    + ". Ofereça-as como alternativa concreta.")
    nivel = busca["nivel"]
    local = busca.get("local")
    if nivel == "fora_de_cobertura":
        onde = getattr(local, "cidade", None) or getattr(local, "termo", "esse lugar")
        return (f"ATENÇÃO: {onde} está FORA da nossa área de cobertura (atendemos São Paulo capital). "
                f"Diga isso em uma frase, sem rodeio, e apresente os imóveis abaixo ({achados}) como a "
                "alternativa mais próxima que temos. Não invente que há imóveis lá.")
    if nivel == "regiao" and not busca["bairros_pedidos"]:
        return (f"Estes imóveis são da região que o cliente pediu ({achados}). Cite o bairro de cada um "
                "e nunca diga que não há opções.")
    if nivel == "bairro":
        return (f"Estes imóveis são exatamente em {pedidos}, no perfil pedido. Cite o bairro de cada um "
                "e nunca diga que não há opções.")
    if nivel == "vizinhos":
        return (f"ATENÇÃO: no perfil pedido não há imóvel em {pedidos}. Os abaixo ficam em bairros vizinhos "
                f"({achados}). Diga isso com clareza numa frase antes de apresentá-los; não afirme que "
                "'não temos imóveis' nem invente motivo (reserva, atualização de sistema), e não sugira "
                "que ficam no bairro pedido." + sugestao_alt)
    if nivel == "regiao":
        return (f"ATENÇÃO: não há imóvel no perfil pedido em {pedidos}. Os abaixo são de outros bairros da "
                f"mesma região ({achados}). Deixe isso explícito antes de apresentá-los." + sugestao_alt)
    if nivel == "cidade":
        return (f"ATENÇÃO: não há nada no perfil pedido nem na região de {pedidos}. Os abaixo são de outras "
                f"partes da cidade ({achados}). Diga isso com honestidade e pergunte se a região é flexível."
                + sugestao_alt)
    return ("Nenhum imóvel atende a esses critérios na nossa base agora — nem no bairro, nem na região, nem "
            "na cidade. Diga isso de forma direta, sem inventar motivo, e proponha flexibilizar UM critério "
            "(preço, bairro ou quartos)." + sugestao_alt)


AJUSTE = "ajuste:"
# Como o cliente pode querer ampliar a busca, e o que isso vira no histórico da conversa.
AJUSTES = {"preco": "Pode mostrar acima do valor que eu falei",
           "vizinhos": "Pode mostrar em bairros vizinhos",
           "quartos": "Pode mostrar com menos quartos"}
_AJUSTE_POR_TEXTO = (("vizinhos", re.compile(r"vizinh|perto|pr[oó]xim|outros? bairros?|regi[aã]o", re.I)),
                     ("quartos", re.compile(r"quarto|menor|studio|kitnet", re.I)),
                     ("preco", re.compile(r"valor|pre[cç]o|aument|acima|mais caro|teto|or[cç]amento|pagar mais", re.I)))


def _criterio(cartao) -> list:
    """O que define a busca. Se mudar, a ampliação escolhida antes deixa de valer."""
    return [cartao.intencao, sorted(cartao.bairros or []), cartao.regiao, cartao.preco_max, cartao.quartos,
            cartao.area_min, cartao.tipo_imovel]


def _valor(v: float | None) -> str:
    if not v:
        return ""
    if v >= 1_000_000:
        return f"R$ {v / 1_000_000:.1f} milhão".replace(".0 ", " ").replace(".", ",")
    if v >= 1000:
        return f"R$ {v / 1000:.0f} mil"
    return f"R$ {v:.0f}"


def _ajuste_escolhido(state: AgentState, mensagem: str, criterio: list) -> str | None:
    if mensagem.startswith(AJUSTE):
        tipo = mensagem[len(AJUSTE):].split("|")[0].strip()
        return tipo if tipo in AJUSTES else None
    if state.get("ajuste_pendente") == criterio:          # respondeu à pergunta por escrito
        return next((tipo for tipo, regra in _AJUSTE_POR_TEXTO if regra.search(mensagem)), None)
    return None


def _perguntar_ajuste(state: AgentState, lead, busca: dict, criterio: list) -> dict:
    """Sem imóvel no perfil exato, PERGUNTA como ampliar em vez de despejar alternativas.

    Um lead pediu 2 quartos em Moema até R$ 6 mil e recebeu, num parágrafo só, um studio de Moema
    que não servia e três imóveis na Mooca e no Butantã que ele não pediu. Ele queria Moema: tirar o
    teto teria mostrado um de 3 quartos lá mesmo. Quem decide o que ceder é o cliente.
    Texto fixo: é uma bifurcação, e as opções vão em botões.
    """
    c = lead.cartao
    onde = ", ".join(busca["bairros_pedidos"])
    aluguel = str(c.intencao) == "aluguel" or getattr(c.intencao, "value", "") == "aluguel"
    teto = _valor(c.preco_max or c.ticket) + ("/mês" if aluguel and (c.preco_max or c.ticket) else "")
    perfil = (c.tipo_imovel or "imóvel") + (f" de {c.quartos} quartos" if c.quartos and c.quartos > 1 else "")
    nome = f"{lead.nome}, " if lead.nome else ""
    texto = (f"{nome}em {onde} não encontrei {perfil}{' até ' + teto if teto else ''} agora.\n\n"
             "Como prefere que eu continue?")
    opcoes = []
    if c.preco_max or c.ticket:
        opcoes.append(f"{AJUSTE}preco|{onde} acima de {_valor(c.preco_max or c.ticket)}")
    opcoes.append(f"{AJUSTE}vizinhos|Bairros vizinhos" + (f" até {_valor(c.preco_max or c.ticket)}" if teto else ""))
    if c.quartos and c.quartos > 1:
        opcoes.append(f"{AJUSTE}quartos|{onde} com menos quartos")
    return {"lead": lead, "messages": [AIMessage(content=texto)], "ajuste_pendente": criterio,
            "resposta": RespostaAgente(lead_id=lead.id, texto=texto, opcoes=opcoes)}


def _absorver_mudanca(lead, mensagem: str) -> None:
    """Deixa o cliente MUDAR DE IDEIA depois de qualificado.

    O cartão só era extraído no qualificador. Quando ele fica completo, o supervisor passa a mandar
    a conversa para cá — e a partir daí "agora quero ver na Vila Mariana e na Vila Madalena" não
    entrava em lugar nenhum. A busca rodava com os bairros ANTIGOS, devolvia os mesmos imóveis de
    antes, e o modelo, que lê a mensagem crua, escrevia por cima "claro, posso buscar na Vila
    Madalena também". Os cards diziam uma coisa e o texto dizia outra, na mesma resposta.

    É uma extração a mais por turno, no modelo barato. O que ela compra: um cliente qualificado
    deixa de ficar preso ao primeiro pedido dele.
    """
    from .qualificador import _extrair, _normalizar_local
    if not mensagem:
        return
    try:
        novo, _fora = _normalizar_local(_extrair(lead.cartao, mensagem), mensagem)
        # A intenção NÃO é tocada aqui: mudar de aluguel para compra abre outra oportunidade, e
        # quem sabe fazer isso é o qualificador. Aqui é ajuste de critério dentro da mesma busca.
        lead.cartao = novo.model_copy(update={"intencao": lead.cartao.intencao})
    except Exception:
        log.warning("não consegui atualizar o cartão do lead %s; sigo com o anterior", lead.id, exc_info=True)


def run(state: AgentState) -> dict:
    lead = state["lead"]
    mensagem = state["entrada"].conteudo or ""
    # Quando o qualificador acabou de extrair esta mesma frase e passou o turno para cá, o cartão
    # já está atualizado: extrair de novo era uma chamada de modelo repetida em todo turno que
    # completava o cartão (introduzida junto com `_absorver_mudanca`, sem ninguém medir).
    if state.get("cartao_extraido_de") != mensagem:
        _absorver_mudanca(lead, mensagem)
    # O estado do grafo só conhece esta conversa. `interesses` atravessa sessões: quem voltou
    # duas semanas depois não recebe os mesmos três imóveis de novo, e o que foi descartado
    # não reaparece nunca — reoferecer o que a pessoa já recusou é o que faz um bot parecer burro.
    conhecidos = InteresseRepository().por_situacao(lead.id)
    descartados = conhecidos.get("descartado", set())
    ja_vistos = {c.id for c in state.get("imoveis_sugeridos") or []} | conhecidos.get("sugerido", set())

    criterio = _criterio(lead.cartao)
    ajuste = state.get("ajuste") if (state.get("ajuste") or {}).get("criterio") == criterio else None
    if (tipo := _ajuste_escolhido(state, mensagem, criterio)):
        ajuste = {"tipo": tipo, "criterio": criterio}
    cartao_busca = lead.cartao
    if ajuste and ajuste["tipo"] == "preco":
        cartao_busca = lead.cartao.model_copy(update={"preco_max": None, "ticket": None})
    elif ajuste and ajuste["tipo"] == "quartos":
        cartao_busca = lead.cartao.model_copy(update={"quartos": None})
    preferencia = "" if mensagem.startswith(AJUSTE) else state["entrada"].conteudo
    busca = buscar_com_contexto(cartao_busca, preferencia=preferencia, limite=6)
    if (busca.get("ampliou") and busca["nivel"] in ("vizinhos", "regiao", "cidade")
            and busca["bairros_pedidos"] and ajuste is None):
        return _perguntar_ajuste(state, lead, busca, criterio)
    todos = [c for c in busca["cards"] if c.id not in descartados]
    cards = [c for c in todos if c.id not in ja_vistos][:3] or todos[:3]     # esgotou novidades → repete as melhores
    resumo = "\n".join(_linha(c, busca.get("fichas") or {}) for c in cards) or "(nenhum)"
    # O agente só pode falar de disponibilidade com base nisto — nunca deduzir do que não veio na lista.
    contexto = _contexto_da_busca(busca, cards)
    if ajuste and ajuste["tipo"] == "preco":
        contexto += ("\nO cliente aceitou ver opções ACIMA do valor que ele tinha dito. Deixe claro, em meia frase, "
                     "que estas passam do teto dele.")
    elif ajuste and ajuste["tipo"] == "quartos":
        contexto += "\nO cliente aceitou ver opções com MENOS quartos do que pediu. Deixe isso claro em meia frase."
    if cards and not (lead.telefone or lead.cartao.tem_contato()):
        # A vitrine é o momento em que o contato vale alguma coisa para o cliente. Opcional aqui; a
        # trava de verdade é na reserva da visita (ver agendador).
        contexto += ("\nO cliente ainda não deixou contato. Depois da pergunta final, numa linha separada e curta, "
                     "diga que o corretor manda mais fotos e detalhes se ele deixar um telefone — sem insistir.")
    msg = llm_conversa().invoke([carregar("consultor", memoria=lead.resumo, nome=lead.nome or "cliente",
                                          cartao=lead.cartao.model_dump(exclude_defaults=True), imoveis=resumo,
                                          contexto_busca=contexto), *state["messages"]])
    if lead.estagio in (Estagio.NOVO, Estagio.QUALIFICANDO) and lead.cartao.completo():
        lead.estagio = Estagio.QUALIFICADO

    # Best-effort: a resposta já foi montada e vai sair de qualquer jeito. Falhar o turno do cliente
    # porque um INSERT de interesse não passou seria trocar o atendimento pelo registro dele.
    try:
        InteresseRepository().registrar_varios(lead.id, [(c.id, c.motivo) for c in cards])
    except Exception:
        log.warning("não consegui registrar os interesses do lead %s", lead.id, exc_info=True)
    return {"lead": lead, "imoveis_sugeridos": (state.get("imoveis_sugeridos") or []) + cards, "messages": [msg],
            "ultimos_sugeridos": [c.id for c in cards] or (state.get("ultimos_sugeridos") or []),
            "ajuste": ajuste, "ajuste_pendente": None,
            "imovel_escolhido": None,                  # lote novo na tela: a escolha anterior não vale mais
            "resposta": RespostaAgente(lead_id=lead.id, texto=sanear(msg.content, lead.id), imoveis=cards,
                                       opcoes=["Agendar visita", "Ver outros", "Falar com corretor"] if cards else [])}
