"""Acionado pelo scheduler. Retoma a conversa de ONDE ELA PAROU; o canal cuida da janela de 24h.

Antes o prompt recebia só o cartão e pedia "um gancho novo (uma opção nova, uma condição, uma dúvida
útil)". Sem saber o que faltava, o modelo inventava: um lead parado na pergunta do bairro — o único
dado que faltava para a busca — recebeu "você prefere mobiliado ou sem mobília?", um atributo que o
cartão não guarda e a busca não filtra. A resposta, se viesse, não levaria a imóvel nenhum.

Agora a mensagem é TEXTO FIXO, escolhido por duas coisas que o código sabe:

* a SITUAÇÃO — faltava um campo (retomar AQUELA pergunta), ou ele já tinha visto imóveis (perguntar
  por eles, ou trazer um que entrou no perfil desde então);
* a TENTATIVA — a primeira retoma, a segunda facilita, a última se despede sem perguntar.

E sai com botões: quem sumiu raramente volta digitando. "Já encontrei" e "Agora não" encerram a
cadência na hora, em vez de o cliente receber as tentativas que faltam.
"""
import logging

from langchain_core.messages import AIMessage

from sdr_shared import followup as politica_followup
from sdr_shared.db import auditar
from sdr_shared.messaging import RespostaAgente
from sdr_shared.models import Estagio
from ..state import AgentState
from ..guardrails.saida import sanear

log = logging.getLogger("agent.followup")

# Botões de saída. O prefixo é o que o supervisor reconhece; o rótulo é o que o cliente vê.
SAIDA = "followup:"
ENCONTREI = f"{SAIDA}encontrei|Já encontrei"
AGORA_NAO = f"{SAIDA}depois|Agora não"
CONTINUAR = "Quero continuar"


def _opcoes_do_campo(campo: str, intencao) -> list[str]:
    """Respostas de um toque para o campo que falta. O texto do botão é o que entra na conversa,
    então ele tem de ser legível pela extração ("Zona Leste", "Até R$ 2 mil") — e é."""
    aluguel = str(getattr(intencao, "value", intencao)) == "aluguel"
    return {
        "intencao": ["Comprar", "Alugar", "Investir"],
        "regiao": ["Zona Sul", "Zona Oeste", "Zona Leste", "Zona Norte", "Centro"],
        "preco_max": (["Até R$ 2 mil por mês", "Até R$ 4 mil por mês", "Até R$ 7 mil por mês"] if aluguel
                      else ["Até R$ 500 mil", "Até R$ 1 milhão", "Até R$ 2 milhões"]),
        "quartos": ["1 quarto", "2 quartos", "3 quartos ou mais"],
        "urgencia": ["É urgente", "Em até 3 meses", "Sem pressa"],
        "perfil_investidor": ["Conservador", "Moderado", "Arrojado"],
    }.get(campo, [])


def _imovel_novo(state: AgentState, lead):
    """Um imóvel do perfil que ele AINDA NÃO viu, ou None. É o único "gancho novo" que não é
    invenção: saiu da busca agora, com os mesmos filtros de sempre."""
    try:
        from sdr_shared.db import InteresseRepository
        from ..tools.buscar_imoveis import buscar_com_contexto
        vistos = {c.id for c in state.get("imoveis_sugeridos") or []}
        for ids in InteresseRepository().por_situacao(lead.id).values():
            vistos |= ids                     # sugerido, interessado ou descartado: nada disso é novo
        busca = buscar_com_contexto(lead.cartao, limite=6)
        if busca["nivel"] not in ("bairro", "regiao"):
            return None                           # longe do que ele pediu não é novidade, é ruído
        return next((c for c in busca["cards"] if c.id not in vistos), None)
    except Exception:
        log.warning("follow-up do lead %s sem busca de imóvel novo", lead.id, exc_info=True)
        return None


def _ola(nome: str | None) -> str:
    return f"Oi, {nome}!" if nome else "Oi!"


def _chamando(nome: str | None, frase: str) -> str:
    """"Marcos, se ficar mais fácil…" com nome; "Se ficar mais fácil…" sem."""
    return f"{nome}, {frase}" if nome else frase[0].upper() + frase[1:]


def _o_que_mostrar(intencao) -> str:
    v = str(getattr(intencao, "value", intencao))
    return {"aluguel": "os imóveis para alugar", "compra": "os imóveis à venda",
            "investimento": "as opções para investir"}.get(v, "as opções")


# A pergunta pendente, dita como quem retoma — uma por campo. "Só falta" é o que dá sentido ao
# contato: o cliente entende que está a um passo de ver imóveis, e não no começo de um formulário.
_FALTA = {
    "regiao": "Ficou faltando só a região para eu te mostrar {mostrar}. Onde você prefere?",
    "preco_max": "Para eu separar {mostrar} certos, só falta o valor: até quanto você pensa em pagar{mes}?",
    "quartos": "Para eu separar {mostrar} certos, só falta saber quantos quartos você precisa.",
    "urgencia": "Já estou quase com {mostrar} separados: só me diz se é urgente ou se dá para ir com calma.",
    "area_min": "Para eu separar {mostrar} certos, só falta saber quantos metros quadrados você precisa.",
    "intencao": "Me conta: você quer comprar, alugar ou investir? Daí eu já te mostro as opções.",
    "perfil_investidor": "Para eu indicar as opções certas, só falta entender seu perfil: mais conservador, moderado ou arrojado?",
    "ticket": "Para eu indicar as opções certas, só falta saber quanto você pretende investir.",
    "retorno_esperado": "Para eu indicar as opções certas, só falta saber que retorno você espera.",
}


def _plano(state: AgentState, lead, tentativa: int, total: int) -> tuple[str, list[str], list]:
    """(texto, botões, cards). Texto FIXO por situação e tentativa — sem modelo.

    Retomar uma conversa parada é sempre uma de poucas situações, e para cada uma há uma frase certa.
    Pedir ao modelo custava uma chamada, variava a cada envio e, quando ele não sabia o que dizer,
    inventava (a pergunta sobre mobília) ou devolvia vazio — e o filtro de saída trocava pelo texto
    de reserva, que pergunta "comprar, alugar ou investir?" a quem já tinha dito que quer alugar.
    """
    nome, c = lead.nome, lead.cartao
    aluguel = str(getattr(c.intencao, "value", c.intencao)) == "aluguel"
    faltantes = c.campos_faltantes()
    ids_tela = set(state.get("ultimos_sugeridos") or [])
    vistos = ([x for x in state.get("imoveis_sugeridos") or [] if x.id in ids_tela]
              or (state.get("imoveis_sugeridos") or [])[-3:])

    if tentativa >= total:
        despedida = f"Vou deixar você à vontade, {nome}." if nome else "Vou deixar você à vontade."
        return (f"{despedida} Quando quiser retomar a busca, é só me mandar uma mensagem por aqui.",
                [CONTINUAR, ENCONTREI], [])

    if faltantes:
        campo = faltantes[0]
        botoes = [*_opcoes_do_campo(campo, c.intencao), ENCONTREI]
        if tentativa == 1:
            frase = _FALTA.get(campo, "Para eu te mostrar as opções, só falta um detalhe.").format(
                mostrar=_o_que_mostrar(c.intencao), mes=" por mês" if aluguel else "")
            return f"{_ola(nome)} {frase}", botoes, []
        return _chamando(nome, "se ficar mais fácil, é só tocar numa das opções aqui embaixo que eu sigo daí."), botoes, []

    if tentativa >= 2 and (novo := _imovel_novo(state, lead)):
        return (_chamando(nome, "entrou um imóvel no seu perfil que você ainda não viu. Quer dar uma olhada?"),
                ["Agendar visita", "Ver outros", ENCONTREI], [novo])

    if vistos:
        if tentativa == 1:
            um = "O imóvel" if len(vistos) == 1 else "Algum dos imóveis"
            return (f"{_ola(nome)} {um} que te mostrei chamou sua atenção? Se quiser, já vejo um "
                    "horário para você visitar.", ["Agendar visita", "Ver outros", ENCONTREI], [])
        return (_chamando(nome, "se aqueles não serviram, posso buscar outras opções ou te passar para um "
                                "dos nossos corretores."),
                ["Ver outros", "Falar com corretor", ENCONTREI], [])

    return (f"{_ola(nome)} Já separei algumas opções dentro do que você pediu. Quer ver?",
            ["Ver opções", ENCONTREI], [])


def _encerrar(state: AgentState, lead, motivo: str) -> dict:
    """"Já encontrei" / "Agora não": sai do fluxo AGORA. FRIO é o estágio que o handler usa para
    cancelar o que estiver na fila (ENCERRADOS); a reativação continua podendo chamá-lo no futuro,
    com as regras dela — inclusive a de quem pediu para sair."""
    lead.estagio = Estagio.FRIO
    texto = ("Que ótimo, fico feliz que deu certo! Se precisar de algo mais, é só me chamar por aqui."
             if motivo == "encontrei" else
             "Sem problema! Não vou mais te chamar por enquanto. Quando quiser retomar, é só me mandar uma mensagem.")
    auditar(acao="lead.followup_encerrado", entidade="lead", entidade_id=lead.id, ator_tipo="cliente",
            ator_nome=lead.nome, dados={"motivo": motivo})
    return {"lead": lead, "messages": [AIMessage(content=texto)],
            "resposta": RespostaAgente(lead_id=lead.id, texto=texto)}


def run(state: AgentState) -> dict:
    lead = state["lead"]
    conteudo = state["entrada"].conteudo or ""
    if conteudo.startswith(SAIDA):                        # botão "Já encontrei" / "Agora não"
        return _encerrar(state, lead, conteudo[len(SAIDA):].split("|")[0].strip())

    tentativa = lead.followups_enviados + 1
    total = len(politica_followup.politica_cacheada()["tempos_min"])
    texto, opcoes, cards = _plano(state, lead, tentativa, total)
    msg = AIMessage(content=texto)
    lead.followups_enviados = tentativa
    # esgotou as tentativas → frio (sai do fluxo); ainda há o que tentar → inativo
    lead.estagio = Estagio.FRIO if tentativa >= total else Estagio.INATIVO
    auditar(acao="lead.followup_enviado", entidade="lead", entidade_id=lead.id, ator_tipo="agente",
            ator_nome="Mora", dados={"tentativa": tentativa, "de": total, "estagio": str(lead.estagio.value),
                                     "imovel_novo": cards[0].id if cards else None})
    saida = {"lead": lead, "messages": [msg],
             "resposta": RespostaAgente(lead_id=lead.id, texto=sanear(texto, lead.id),
                                        opcoes=opcoes, imoveis=cards)}
    if cards:                                             # o card novo vira o lote na tela: "Agendar visita" é dele
        saida |= {"imoveis_sugeridos": (state.get("imoveis_sugeridos") or []) + cards,
                  "ultimos_sugeridos": [c.id for c in cards], "imovel_escolhido": None}
    return saida
