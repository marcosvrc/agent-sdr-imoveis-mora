"""Roteador. Regras determinísticas primeiro (baratas, previsíveis); LLM (Haiku) só na ambiguidade."""
import logging
import re
import unicodedata

from sdr_shared.messaging import TipoMensagem, Canal
from sdr_shared.models import Estagio, Intencao
from ..guardrails import escopo
from ..llm import llm_roteamento
from ..prompts import texto
from ..state import AgentState
from . import reativador
from .agendador import ESCOLHA
from . import followup
from .qualificador import so_contato

log = logging.getLogger(__name__)

DECISOES = ("qualificador", "consultor", "agendador", "informacoes", "handoff")
_DECISAO = re.compile(r"\b(" + "|".join(DECISOES) + r")\b")


def _conteudo(bruto) -> str:
    """`content` vem como texto ou, em alguns modelos que raciocinam, como lista de blocos."""
    if isinstance(bruto, str):
        return bruto
    if isinstance(bruto, list):
        return " ".join(b if isinstance(b, str) else str(b.get("text") or "")
                        for b in bruto if isinstance(b, (str, dict)))
    return str(bruto or "")


def interpretar_decisao(bruto) -> str | None:
    """A primeira decisão válida que aparece na resposta, ou None.

    Pegava-se a primeira palavra e exigia-se o rótulo exato. "Consultor.", "**consultor**",
    "informações" (com acento) ou blocos de conteúdo viravam, em silêncio, `qualificador` — e a
    matriz mediu um modelo que roteou TUDO para o qualificador com 59% de "acerto" (os casos cuja
    resposta certa era justamente o valor padrão).
    """
    t = unicodedata.normalize("NFKD", _conteudo(bruto)).encode("ascii", "ignore").decode().lower()
    achado = _DECISAO.search(t)
    return achado.group(1) if achado else None


_FALA_ALUGUEL = re.compile(r"\balug(ar|uel|ueis|o)\b|\bloca[cç][aã]o\b", re.I)
_FALA_COMPRA = re.compile(r"\bcompr(ar|a|o)\b|\badquirir\b", re.I)
# Citar o outro uso não é trocar de intenção. "não quero comprar agora", de quem aluga, é o
# contrário de uma troca; "quanto rende o aluguel desse?", de quem compra, é pergunta sobre o
# imóvel que ele já quer. As duas iam para o qualificador como troca, e a de cima abria uma
# oportunidade de compra para quem tinha acabado de dizer que não ia comprar.
_NEGA_INTENCAO = re.compile(r"\bn[ãa]o\s+(quero|vou|pretendo|penso em|estou pensando em|tenho interesse em|"
                            r"preciso|busco|procuro)\s+(mais\s+)?(em\s+)?(compr|alug|adquir|loca)", re.I)
_DESEJO = re.compile(r"\b(quero|queria|prefiro|gostaria|pretendo|penso em|pensando em|procur\w*|busc\w*|"
                     r"na verdade|mudei|mudar para)\b", re.I)
# A coisa (o aluguel, a compra) ou a possibilidade ("dá pra alugar depois?") — não o pedido.
_OUTRO_USO = re.compile(r"\b(aluguel|loca[cç][aã]o|compra)\b|\b(d[áa]|daria|posso|pode|consigo)\s+(pra|para\s+)?"
                        r"\s*(alugar|comprar)\b", re.I)


def intencao_citada(txt: str) -> Intencao | None:
    """Compra ou aluguel dito com todas as letras. "comprar para alugar" cita os dois: não decide."""
    aluguel, compra = bool(_FALA_ALUGUEL.search(txt)), bool(_FALA_COMPRA.search(txt))
    if aluguel == compra:
        return None
    if _NEGA_INTENCAO.search(txt):
        return None
    if "?" in txt and not _DESEJO.search(txt) and _OUTRO_USO.search(txt):
        return None
    return Intencao.ALUGUEL if aluguel else Intencao.COMPRA


# Pedido EXPLÍCITO de uma pessoa. "corretor" sozinho casava qualquer menção: "quando o corretor vai
# me ligar?", logo depois de reservar a visita, virava handoff — a Mora calava e a pergunta ficava
# sem resposta até alguém abrir o painel; "vocês cobram comissão do corretor?" também. Atendente,
# humano e pessoa de verdade continuam valendo sozinhos: ninguém cita essas palavras à toa aqui.
PEDE_HUMANO = re.compile(
    r"\b(atendente|humano|pessoa de verdade|falar com algu[ée]m)\b"
    r"|\b(falar|conversar|fala|ser atendid[oa])\s+com\s+(o\s+|a\s+|um\s+|uma\s+)?(corretor|corretora|pessoa)\b"
    # O verbo de pedido pode vir com preposição ("preciso DE um corretor", "me passa PRO corretor")
    # e no infinitivo ("pode chamar o corretor?"): a primeira versão só casava "quero um corretor",
    # e "preciso de um corretor" ia ao qualificador, que respondia com pergunta de qualificação.
    r"|\b(quero|queria|preciso|prefiro|gostaria|me\s+(passa|passe|transfere|transfira|coloca|encaminha)|"
    r"chamar|passar|transferir|encaminhar|chama|chame|cad[êe]|tem)\s+"
    r"(de\s+|d[eo]\s+|pr[oa]\s+|para\s+|ao\s+|com\s+)?"
    r"(o\s+|a\s+|um\s+|uma\s+|algum\s+|alguma\s+)?(corretor|corretora)\b", re.I)
_NEGA_HUMANO = re.compile(r"\bn[ãa]o\s+(quero|preciso)\b[^.!?]{0,24}\b(corretor|corretora|atendente|humano|pessoa)\b", re.I)


def pede_humano(txt: str) -> bool:
    """"não quero falar com corretor" cita o pedido para recusá-lo."""
    return bool(PEDE_HUMANO.search(txt)) and not _NEGA_HUMANO.search(txt)


# "horário" sozinho não é pedido de visita: "qual o horário de atendimento de vocês?" ia para o
# agendador e recebia a grade. E "remarcar", "desmarcar", "reagendar" não casavam `\bmarcar\b` —
# quem já tinha visita e queria mudá-la caía no modelo de rota, que não pode mandá-la ao agendador.
PEDE_VISITA = re.compile(r"\b(visitar|visita|(re)?agendar|(re|des)?marcar|conhecer o im[oó]vel|"
                         r"outro hor[aá]rio|hor[aá]rios|tem hor[aá]rio)\b", re.I)
ESCOLHE_HORARIO = re.compile(r"(\b\d{1,2}\s*(h|hs|hrs|horas|:\d{2})\b|\b(seg|ter|qua|qui|sex|segunda|ter[çc]a|quarta|quinta|sexta|amanh[ãa]|primeir[oa]|segund[oa]|terceir[oa]|[úu]ltim[oa])\b|\b\d{1,2}/\d{1,2}\b)", re.I)
PEDE_OPCOES = re.compile(r"\b(op[çc][õo]es|me mostra|mostrar|o que (voc[eê]s? )?tem|outros? im[oó]ve(l|is)|ver outros)\b", re.I)
# Pergunta sobre um imóvel que já está na tela ("mais detalhes da segunda opção", "tem mais
# fotos dele?"). Não é pedido de visita, mesmo quando cita a visita ("antes de agendar…"): ia para o
# agendador, que respondia a pergunta no texto e ainda assim mandava a grade de horários embaixo.
PEDE_DETALHES = re.compile(
    r"\b(mais\s+)?detalhes?\b|\bmais\s+(fotos?|informa[çc][õo]es|infos?)\b"
    r"|\b(me\s+)?(fala|conta|diz|explica)\s+mais\b|\bfotos?\s+d[oaei]s?\b"
    r"|\b(como|qual)\s+[ée]\s+(o|a)\s+(primeir|segund|terceir|[úu]ltim)[oa]\b", re.I)
# Quem adia a visita não está pedindo visita: "antes de agendar", "ainda não quero marcar".
ADIA_VISITA = re.compile(
    r"\bantes\s+de\s+(agendar|marcar|visitar)\b"
    r"|\b(ainda\s+)?n[ãa]o\s+(quero|vou|preciso|pretendo)\s+(agendar|marcar|visitar)\b"
    r"|\bdepois\s+(eu\s+)?(agendo|marco)\b|\bsem\s+(agendar|marcar)\b", re.I)

# Pergunta sobre COMO A IMOBILIÁRIA TRABALHA — vai para o RAG institucional.
#
# Dois grupos, e a separação não é preciosismo. Termos FORTES (fiador, IPTU, vistoria, ITBI) só
# aparecem em pergunta institucional; termos FRACOS (taxa, prazo, entrada, contrato, comissão)
# aparecem também em conversa de imóvel — "quero um apê de entrada até 300 mil" não é pergunta
# sobre política. Por isso o fraco exige uma marca de pergunta ao lado.
INSTITUCIONAL_FORTE = re.compile(
    r"\b(fiador|avalista|cau[çc][ãa]o|seguro.fian[çc]a|vistoria|iptu|itbi|escritura|financiamento|"
    r"documenta[çc][ãa]o|documentos? (necess[áa]rios?|preciso|exigidos?)|reajuste|rescis[ãa]o|"
    r"pet|cachorro|gato|animal de estima[çc][ãa]o|hor[aá]rios? de (atendimento|funcionamento))\b", re.I)
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
    # "Já encontrei" / "Agora não" do follow-up: quem encerra a cadência é o próprio nó de follow-up,
    # que sabe o que cancelar. Antes do porteiro: "followup:encontrei" não é assunto fora do escopo.
    if txt.startswith(followup.SAIDA):
        return {"proximo": "followup", "saltos": saltos}

    # Pedir para não receber avisos tem precedência sobre tudo — inclusive sobre o porteiro de
    # escopo, que leria "não quero mais nada" como assunto fora do escopo e responderia recusa.
    # Quem pede para sair de uma lista sai na primeira vez que pede.
    if reativador.PEDE_SAIR.search(txt):
        return {"proximo": "reativador", "saltos": saltos}

    # Porteiro: fora do assunto ou tentando reprogramar o agente não entra no fluxo de atendimento.
    # Pedir um humano é exceção — isso é legítimo em qualquer contexto e tem precedência.
    veredito = escopo.avaliar(txt)
    if not veredito and not pede_humano(txt):
        return {"proximo": "recusa", "veredito": veredito, "saltos": saltos}
    if txt == "Falar com corretor" or pede_humano(txt) or lead.estagio == Estagio.HANDOFF:
        return {"proximo": "handoff", "saltos": saltos}

    # Horário segurado esperando o contato. Ele prendia a conversa: toda mensagem de até quatro
    # palavras ia ao agendador, que repetia "pra reservar eu preciso de um contato" sem limite — o
    # cliente perguntava de pet, pedia outros imóveis, e recebia o mesmo pedido de telefone.
    # Agora a Mora insiste UMA vez (`contato_insistido`, gravado pelo agendador); na mensagem
    # seguinte sem contato, ou quando o cliente pede claramente outra coisa (outros imóveis),
    # o horário é solto aqui e a mensagem segue o fluxo normal, como se não houvesse pendente.
    #
    # Quem solta depende do que a mensagem é. Pedido de outros imóveis, ou pergunta institucional
    # depois da insistência: solta aqui e a mensagem segue o fluxo normal. Qualquer outra coisa
    # depois da insistência ("ok", "agora não", "depois eu mando"): vai ao agendador, que solta e
    # DIZ que soltou ("Sem problema, deixei o horário livre…") — soltar aqui e seguir o fluxo
    # mandava a mensagem de volta ao agendador pela rota de `pediu_visita`, e ele oferecia a grade
    # de novo para quem tinha acabado de recusar.
    soltar = {}
    if state.get("horario_pendente") and not (so_contato(txt) or txt.startswith("slot:")):
        pede_opcoes = txt == "Ver outros" or bool(PEDE_OPCOES.search(txt))
        if pede_opcoes or (state.get("contato_insistido") and pergunta_institucional(txt)):
            lead.cartao.pediu_visita = False
            soltar = {"lead": lead, "horario_pendente": None, "contato_insistido": False,
                      "horarios_oferecidos": [], "slots_crm": {}}
            state = {**state, **soltar}
        elif state.get("contato_insistido"):
            return {"proximo": "agendador", "saltos": saltos}
    return {**soltar, **_decidir(state, lead, txt, saltos)}


def _decidir(state: AgentState, lead, txt: str, saltos: int) -> dict:
    """O resto das regras, depois do porteiro e do handoff."""
    # Antes do agendador de propósito: "vocês cobram taxa de visita?" contém "visita" e cairia lá,
    # oferecendo horário para quem pediu uma informação. A escolha de horário (slot:/data) tem
    # precedência sobre isto, porque aí o cliente já está no meio do agendamento.
    if txt.startswith(ESCOLHA):                       # botão "visitar este imóvel": só o agendador sabe o que fazer
        return {"proximo": "agendador", "saltos": saltos}
    if txt.startswith("ajuste:"):                     # como ampliar a busca sem imóvel exato: o consultor busca de novo
        return {"proximo": "consultor", "saltos": saltos}
    # Horário escolhido esperando o contato: o nome e o telefone que chegam agora fecham a reserva.
    # Pergunta institucional não é resposta ao pedido de contato, mesmo curta ("aceita pet?"): vai
    # para informações e o horário continua segurado. (Pedido de opções já soltou o horário em `run`.)
    if state.get("horario_pendente") and (so_contato(txt) or txt.startswith("slot:") or (
            len(txt.split()) <= 4 and not pergunta_institucional(txt))):
        return {"proximo": "agendador", "saltos": saltos}
    # A grade de horários na tela não tranca mais a rota de informações: `horarios_oferecidos` só é
    # zerado quando a visita é reservada, e "precisa de fiador?" dias depois de ver a grade caía no
    # agendador. O que a grade protege é a ESCOLHA do horário ("pode ser terça?"), e só ela.
    if (not txt.startswith("slot:") and pergunta_institucional(txt)
            and not (state.get("horarios_oferecidos") and ESCOLHE_HORARIO.search(txt))):
        return {"proximo": "informacoes", "saltos": saltos}
    # Troca de compra para aluguel (ou o contrário) depois de qualificado. Quem trata é o
    # qualificador: ele abre a oportunidade nova e refaz o cartão. O consultor mantém a intenção de
    # propósito — e recebia a conversa pelo modelo de rota, buscava "compra em Moema até R$ 5 mil"
    # para quem tinha acabado de pedir aluguel, e a resposta saía contraditória.
    if (lead.cartao.intencao not in (Intencao.INDEFINIDA, Intencao.INVESTIMENTO)
            and (citada := intencao_citada(txt)) and citada != lead.cartao.intencao):
        return {"proximo": "qualificador", "saltos": saltos}
    # Detalhe de um imóvel já mostrado vai ao consultor, que responde sobre ele sem buscar de novo
    # e sem grade. Antes da escolha de horário porque "segunda opção" casa ESCOLHE_HORARIO
    # ("segunda" = dia da semana) quando a grade está na tela.
    if (state.get("imoveis_sugeridos") and not txt.startswith("slot:") and txt != "Agendar visita"
            and PEDE_DETALHES.search(txt)):
        return {"proximo": "consultor", "saltos": saltos}
    if txt.startswith("slot:") or (state.get("horarios_oferecidos") and ESCOLHE_HORARIO.search(txt)):
        return {"proximo": "agendador", "saltos": saltos}       # escolha de horário (botão ou texto)
    # `pediu_visita` fica ligado para sempre depois do primeiro pedido — é assim que o agendador
    # sabe retomar de onde parou. Mas, DEPOIS que a visita foi reservada, ele deixa de ser sinal de
    # intenção e vira uma rota grudada: o cliente manda o telefone que a Mora acabou de pedir, cai
    # no agendador de novo, e recebe a grade de horários outra vez — sobre uma visita que já está
    # reservada. Quem quiser remarcar diz isso, e aí cai nas duas condições explícitas acima.
    adia = bool(ADIA_VISITA.search(txt))
    if txt == "Agendar visita" or (PEDE_VISITA.search(txt) and not adia):
        return {"proximo": "agendador", "saltos": saltos}
    # Pedir outros imóveis vem ANTES da rota grudada: com `pediu_visita` ligado, o botão "Ver
    # outros" ia para o agendador e o cliente recebia a grade de horários no lugar dos imóveis.
    if txt == "Ver outros" or PEDE_OPCOES.search(txt):
        return {"proximo": "consultor", "saltos": saltos}
    if lead.cartao.pediu_visita and lead.estagio != Estagio.AGENDADO and not adia:
        return {"proximo": "agendador", "saltos": saltos}
    # Resposta ao pedido de contato. A Mora pede o telefone ao reservar a visita (ou ao mostrar as
    # opções); o número chegava ao modelo de rota, que via cartão completo e mandava para o
    # consultor — e o cliente que só passou o telefone recebia mais imóveis. Quem recebe contato é
    # o qualificador: ele grava o número e agradece.
    if lead.cartao.completo() and so_contato(txt):
        return {"proximo": "qualificador", "saltos": saltos}
    if state.get("ajuste_pendente") and lead.cartao.completo():      # resposta escrita à pergunta "como prefere?"
        return {"proximo": "consultor", "saltos": saltos}
    if lead.cartao.completo() and not state.get("imoveis_sugeridos"):
        return {"proximo": "consultor", "saltos": saltos}
    if not lead.cartao.completo():
        return {"proximo": "qualificador", "saltos": saltos}

    # Ambíguo: cartão completo, imóveis já sugeridos, mensagem livre → Haiku decide
    bruto = llm_roteamento().invoke(texto("supervisor", estagio=lead.estagio, intencao=lead.cartao.intencao,
                                          completo=lead.cartao.completo(), faltantes=[],
                                          sugeridos="sim" if state.get("imoveis_sugeridos") else "não",
                                          mensagem=txt)).content
    decisao = interpretar_decisao(bruto)
    if decisao is None:
        # Não loga a mensagem do cliente, só o que o modelo devolveu — e cortado.
        log.warning("roteador devolveu resposta ilegível (%r): seguindo para o qualificador",
                    _conteudo(bruto)[:80])
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
    if decisao == "handoff" and len(txt.split()) <= 3 and not pede_humano(txt):
        decisao = "consultor" if lead.cartao.completo() else "qualificador"
    return {"proximo": decisao, "saltos": saltos}
