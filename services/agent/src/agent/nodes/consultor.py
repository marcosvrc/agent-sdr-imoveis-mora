"""Busca imóveis (RAG híbrido) e explica por que combinam."""
import logging

from sdr_shared.db import InteresseRepository
from sdr_shared.messaging import RespostaAgente
from sdr_shared.models import Estagio
from ..llm import llm_conversa
from ..prompts import carregar
from ..state import AgentState
from ..tools.buscar_imoveis import buscar_com_contexto
from ..guardrails.saida import sanear

log = logging.getLogger("agent.consultor")


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

    busca = buscar_com_contexto(lead.cartao, preferencia=state["entrada"].conteudo, limite=6)
    todos = [c for c in busca["cards"] if c.id not in descartados]
    cards = [c for c in todos if c.id not in ja_vistos][:3] or todos[:3]     # esgotou novidades → repete as melhores
    resumo = "\n".join(f"- {c.id}: {c.titulo} — R$ {c.preco:,.0f} — {c.motivo}" for c in cards) or "(nenhum)"
    # O agente só pode falar de disponibilidade com base nisto — nunca deduzir do que não veio na lista.
    contexto = _contexto_da_busca(busca, cards)
    msg = llm_conversa().invoke([carregar("consultor", nome=lead.nome or "cliente",
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
            "resposta": RespostaAgente(lead_id=lead.id, texto=sanear(msg.content, lead.id), imoveis=cards,
                                       opcoes=["Agendar visita", "Ver outros", "Falar com corretor"] if cards else [])}
