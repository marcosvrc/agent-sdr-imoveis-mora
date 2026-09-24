"""Roteador. Regras determinísticas primeiro (baratas, previsíveis); LLM (Haiku) só na ambiguidade."""
import re
from sdr_shared.messaging import TipoMensagem, Canal
from sdr_shared.models import Estagio
from ..guardrails import escopo
from ..llm import llm_roteamento
from ..prompts import texto
from ..state import AgentState
from . import reativador

PEDE_HUMANO = re.compile(r"\b(corretor|atendente|humano|pessoa de verdade|falar com alguém)\b", re.I)
PEDE_VISITA = re.compile(r"\b(visitar|visita|agendar|marcar|conhecer o im[oó]vel|hor[aá]rio)\b", re.I)
ESCOLHE_HORARIO = re.compile(r"(\b\d{1,2}\s*(h|hs|hrs|horas|:\d{2})\b|\b(seg|ter|qua|qui|sex|segunda|ter[çc]a|quarta|quinta|sexta|amanh[ãa]|primeir[oa]|segund[oa]|terceir[oa]|[úu]ltim[oa])\b|\b\d{1,2}/\d{1,2}\b)", re.I)
PEDE_OPCOES = re.compile(r"\b(op[çc][õo]es|me mostra|mostrar|o que (voc[eê]s? )?tem|outros? im[oó]ve(l|is)|ver outros)\b", re.I)

# Pergunta sobre COMO A IMOBILIÁRIA TRABALHA — vai para o RAG institucional.
#
# Dois grupos, e a separação não é preciosismo. Termos FORTES (fiador, IPTU, vistoria, ITBI) só
# aparecem em pergunta institucional; termos FRACOS (taxa, prazo, entrada, contrato, comissão)
# aparecem também em conversa de imóvel — "quero um apê de entrada até 300 mil" não é pergunta
# sobre política. Por isso o fraco exige uma marca de pergunta ao lado.
INSTITUCIONAL_FORTE = re.compile(
    r"\b(fiador|avalista|cau[çc][ãa]o|seguro.fian[çc]a|vistoria|iptu|itbi|escritura|financiamento|"
    r"documenta[çc][ãa]o|documentos? (necess[áa]rios?|preciso|exigidos?)|reajuste|rescis[ãa]o|"
    r"pet|cachorro|gato|animal de estima[çc][ãa]o)\b", re.I)
PERGUNTA = (r"(como funciona|qual|quais|quanto|precis[oa]|posso|pode|tem|h[áa]|existe|"
            r"voc[eê]s? (cobra|aceita|exige|pede|trabalha))")
INSTITUCIONAL_FRACO = re.compile(
    rf"{PERGUNTA}[^?]{{0,60}}\b(taxa|prazo|entrada|contrato|comiss[ãa]o|garantia|multa|repasse)\b", re.I)


# Pergunta que pede JUÍZO ou dado de mercado: "esse bairro é bom para família?", "quanto costuma
# ser o condomínio por aqui?", "vale a pena comprar agora?".
#
# Elas não casavam com nada e caíam no qualificador ou no consultor — que não têm fonte para isso e
# respondem com a média do mercado: plausível, específica e frequentemente falsa. É o problema que
# o nó `informacoes` foi escrito para resolver, e ele estava do lado errado da porta. Mandadas para
# lá, não encontram trecho acima do piso e viram "vou confirmar com o corretor", que é a resposta
# certa: a Vértice não publica perfil de bairro nem índice de mercado, e inventar um é pior que
# dizer que não sabe.
CONSULTIVA = re.compile(
    r"\b(vale a pena|compensa|voc[eê] (acha|recomenda|indica|aconselha)|o que voc[eê] acha|"
    r"melhor bairro|melhor regi[ãa]o|vai valorizar|valoriza[çc][ãa]o|mercado imobili[áa]rio|"
    r"pre[çc]o m[ée]dio|m[ée]dia de (pre[çc]o|condom[íi]nio)|quanto costuma|costuma ser quanto|"
    r"[ée] (um )?bom (investimento|neg[óo]cio|momento))\b", re.I)
# "esse bairro é bom?", "a região é tranquila?", "é bom para família?" — qualidade de lugar, que é
# opinião com cara de fato.
LUGAR_QUALIDADE = re.compile(
    r"\b(bairro|regi[ãa]o|vizinhan[çc]a|lugar|local)\b[^?]{0,40}\b(bom|boa|melhor|segur[oa]|"
    r"tranquil[oa]|perigos[oa]|violent[oa]|fam[íi]lia|fam[íi]lias)\b", re.I)


# "o Brooklin é seguro?" não diz a palavra bairro — diz o nome de um. Quem sabe quais nomes são
# lugares é o catálogo `geo`, o mesmo que já resolve apelido e erro de digitação na busca.
# A cópula é o que separa a pergunta sobre o LUGAR da busca por imóvel: "o Brooklin é bom?" é
# juízo sobre a região; "tem apartamento bom no Brooklin?" é o catálogo, e o adjetivo é do imóvel.
COPULA_QUALIDADE = re.compile(
    r"\b([ée]|eh)\s+(muito\s+|bem\s+|meio\s+)?(bom|boa|segur[oa]|tranquil[oa]|perigos[oa]|"
    r"violent[oa]|calm[oa]|barulhent[oa]|caro|cara|barat[oa])\b", re.I)


def pergunta_consultiva(txt: str) -> bool:
    """Juízo ou dado de mercado — e, no caso de qualidade de lugar, só quando é pergunta mesmo."""
    if CONSULTIVA.search(txt):
        return True
    if not ("?" in txt or re.search(PERGUNTA, txt, re.I)):
        return False
    if LUGAR_QUALIDADE.search(txt):
        return True
    if COPULA_QUALIDADE.search(txt):
        from sdr_shared.geo import resolver
        return resolver(txt).tipo in ("bairro", "regiao", "cidade", "fora")
    return False


def pergunta_institucional(txt: str) -> bool:
    return bool(INSTITUCIONAL_FORTE.search(txt) or INSTITUCIONAL_FRACO.search(txt)
                or pergunta_consultiva(txt))


def run(state: AgentState) -> dict:
    saltos = state.get("saltos", 0) + 1
    if state.get("resposta") or saltos > 1:          # já respondeu neste turno → encerra
        return {"saltos": saltos}

    lead, entrada = state["lead"], state["entrada"]
    txt = entrada.conteudo or ""

    if entrada.canal == Canal.SISTEMA:                # pedido interno (briefing/análise): não passa pelas regras de conversa
        return {"proximo": "resumidor", "saltos": saltos}
    if entrada.tipo == TipoMensagem.FOLLOWUP:
        return {"proximo": "followup", "saltos": saltos}
    if entrada.tipo == TipoMensagem.REATIVACAO:
        return {"proximo": "reativador", "saltos": saltos}

    # Pedir para não receber avisos tem precedência sobre tudo — inclusive sobre o porteiro de
    # escopo, que leria "não quero mais nada" como assunto fora do escopo e responderia recusa.
    # Quem pede para sair de uma lista sai na primeira vez que pede.
    if reativador.PEDE_SAIR.search(txt):
        return {"proximo": "reativador", "saltos": saltos}

    # Porteiro: fora do assunto ou tentando reprogramar o agente não entra no fluxo de atendimento.
    # Pedir um humano é exceção — isso é legítimo em qualquer contexto e tem precedência.
    veredito = escopo.avaliar(txt)
    if not veredito and not PEDE_HUMANO.search(txt):
        return {"proximo": "recusa", "veredito": veredito, "saltos": saltos}
    if txt == "Falar com corretor" or PEDE_HUMANO.search(txt) or lead.estagio == Estagio.HANDOFF:
        return {"proximo": "handoff", "saltos": saltos}
    # Antes do agendador de propósito: "vocês cobram taxa de visita?" contém "visita" e cairia lá,
    # oferecendo horário para quem pediu uma informação. A escolha de horário (slot:/data) tem
    # precedência sobre isto, porque aí o cliente já está no meio do agendamento.
    if not txt.startswith("slot:") and not state.get("horarios_oferecidos") and pergunta_institucional(txt):
        return {"proximo": "informacoes", "saltos": saltos}
    if txt.startswith("slot:") or (state.get("horarios_oferecidos") and ESCOLHE_HORARIO.search(txt)):
        return {"proximo": "agendador", "saltos": saltos}       # escolha de horário (botão ou texto)
    # `pediu_visita` fica ligado para sempre depois do primeiro pedido — é assim que o agendador
    # sabe retomar de onde parou. Mas, DEPOIS que a visita foi reservada, ele deixa de ser sinal de
    # intenção e vira uma rota grudada: o cliente manda o telefone que a Mora acabou de pedir, cai
    # no agendador de novo, e recebe a grade de horários outra vez — sobre uma visita que já está
    # reservada. Quem quiser remarcar diz isso, e aí cai nas duas condições explícitas acima.
    if txt == "Agendar visita" or PEDE_VISITA.search(txt) or (
            lead.cartao.pediu_visita and lead.estagio != Estagio.AGENDADO):
        return {"proximo": "agendador", "saltos": saltos}
    if txt == "Ver outros" or PEDE_OPCOES.search(txt):
        return {"proximo": "consultor", "saltos": saltos}
    if lead.cartao.completo() and not state.get("imoveis_sugeridos"):
        return {"proximo": "consultor", "saltos": saltos}
    if not lead.cartao.completo():
        return {"proximo": "qualificador", "saltos": saltos}

    # Ambíguo: cartão completo, imóveis já sugeridos, mensagem livre → Haiku decide
    bruto = llm_roteamento().invoke(texto("supervisor", estagio=lead.estagio, intencao=lead.cartao.intencao,
                                          completo=lead.cartao.completo(), faltantes=[], mensagem=txt)).content
    decisao = bruto if isinstance(bruto, str) else str(bruto)      # `content` pode vir em blocos
    decisao = decisao.strip().lower().split()[0] if decisao.strip() else "qualificador"
    if decisao not in ("qualificador", "consultor", "agendador", "handoff", "informacoes"):
        decisao = "qualificador"
    # As regras determinísticas acima já decidiram que esta mensagem NÃO pede visita (nem botão de
    # horário, nem palavra de agendamento) e que a visita deste lead já está reservada. O modelo não
    # pode desfazer isso: mandado ao agendador, ele reoferece a grade de horários — e o cliente, que
    # só quis mudar de bairro, recebe dias de visita que não pediu.
    if decisao == "agendador" and lead.estagio == Estagio.AGENDADO:
        decisao = "consultor" if lead.cartao.completo() else "qualificador"
    # Passar para um humano é caro e, para o cliente, sem volta: a Mora silencia e quem responde
    # passa a ser uma pessoa que pode demorar. O modelo mandava para lá qualquer coisa que não
    # reconhecesse como assunto de imóvel — e um cliente digitou "dim" (provavelmente "sim") logo
    # depois de reservar a visita, virou handoff, perguntou "não entendi, pode falar mais sobre o
    # imóvel?" e não recebeu resposta de ninguém.
    #
    # Mensagem de até três palavras que não pede pessoa nenhuma é erro de digitação, resposta curta
    # ou ruído — não é reclamação nem pedido de atendente. Pedido explícito continua passando:
    # `PEDE_HUMANO` e o botão "Falar com corretor" são tratados lá em cima, antes do modelo.
    if decisao == "handoff" and len(txt.split()) <= 3 and not PEDE_HUMANO.search(txt):
        decisao = "consultor" if lead.cartao.completo() else "qualificador"
    return {"proximo": decisao, "saltos": saltos}
