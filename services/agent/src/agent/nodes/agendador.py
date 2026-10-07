"""Turno 1: oferece horários (lista). Turno 2 (botão `slot:<iso>`): confirma, grava visita, publica evento."""
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from langchain_core.messages import AIMessage

from sdr_shared.messaging import RespostaAgente, Acao
from sdr_shared.models import Estagio
from ..llm import llm_conversa
from ..prompts import carregar
from ..state import AgentState
from ..guardrails.saida import sanear
from sdr_shared.crm import horarios_do_imovel, pedir_visita
from sdr_shared.geo import link_do_mapa

from ..tools.agenda import HorarioOcupado, listar_horarios, agendar, formatar

DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
_SEMANA = {"segunda": 0, "seg": 0, "terca": 1, "ter": 1, "quarta": 2, "qua": 2, "quinta": 3, "qui": 3, "sexta": 4, "sex": 4,
           "sabado": 5, "sab": 5, "domingo": 6, "dom": 6}
_BR = timezone(timedelta(hours=-3))


def _onde_fica(imovel_id: str | None, card) -> tuple[str | None, str]:
    """Bairro e cidade do imóvel — do CADASTRO, não do título do card.

    O `local` da visita saía de `card.titulo.split("·")[-1]`, que é o bairro só enquanto o título
    tiver exatamente esse formato: "Sala comercial 45 m² · Pinheiros". Mudou o título — e ele mudou
    quando o comercial entrou, com a medida em metros — e o "bairro" vira outra coisa, que ia parar
    no evento de calendário do cliente. O cadastro tem os dois campos; é de lá que eles saem.
    """
    from sdr_shared.geo import CIDADE_PADRAO
    if imovel_id:
        try:
            from sdr_shared.db import ImovelRepository
            if im := ImovelRepository().get(imovel_id):
                return im.bairro, im.cidade or CIDADE_PADRAO
        except Exception:
            pass
    if card and "·" in card.titulo:                    # reserva sem o imóvel no banco: melhor que nada
        return card.titulo.split("·")[-1].strip(), CIDADE_PADRAO
    return None, CIDADE_PADRAO


def descrever_imovel(imovel_id: str | None, sugeridos: list) -> str:
    """Como o imóvel deve ser CHAMADO na conversa.

    O prompt recebia o código do cadastro (`SP-0282`) no lugar do imóvel, e o modelo fazia o óbvio:
    repetia o código para o cliente. Para quem está do outro lado, isso não significa nada — e faz
    a conversa soar como um sistema respondendo em vez de alguém atendendo.

    Ordem de preferência: o título do card que a Mora acabou de mostrar (é o texto que o cliente viu
    na tela), depois o cadastro no banco, e só então um genérico. Nunca o código.
    """
    if card := next((c for c in sugeridos if c.id == imovel_id), None):
        return card.titulo
    if imovel_id:
        try:
            from sdr_shared.db import ImovelRepository
            if im := ImovelRepository().get(imovel_id):
                return f"{im.tipo.capitalize()} de {im.quartos} quarto(s) no {im.bairro}"
        except Exception:
            pass
    return "o imóvel"


ESCOLHA = "imovel:"
_TEM_TELEFONE = re.compile(r"\d{4}[\s.-]?\d{4}|[\w.+-]+@[\w-]+\.")


def so_contato_na_mensagem(txt: str) -> bool:
    return bool(_TEM_TELEFONE.search(txt))          # botão "quero visitar este": imovel:<id>|<título>


def texto_para_historico(conteudo: str) -> str:
    """O que o modelo deve ler como fala do cliente.

    `slot:2026-09-21T17:00:00+00:00` é o identificador do botão, não uma frase. Entrando cru no
    histórico, o modelo lê "17:00" — a hora em UTC do que o cliente viu escrito como 14h — e passa a
    responder sobre um horário que ninguém pediu. Trocar pelo rótulo do botão devolve ao histórico o
    que de fato aconteceu na tela.
    """
    if conteudo.startswith(ESCOLHA):
        return f"Quero visitar: {descrever_imovel(conteudo[len(ESCOLHA):], [])}"
    if conteudo.startswith("ajuste:"):
        from .consultor import AJUSTES
        return AJUSTES.get(conteudo[7:].split("|")[0], conteudo)
    if not conteudo.startswith("slot:"):
        return conteudo
    try:
        return formatar(datetime.fromisoformat(conteudo[5:]))
    except ValueError:
        return conteudo


def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def _horario_do_botao(texto: str, state: AgentState) -> datetime | None:
    """O horário de um `slot:<iso>` — só se for um dos que a Mora ofereceu (ou o que ela está
    segurando) e ainda não tiver passado.

    O prefixo chega como texto comum: o cliente pode digitá-lo, e um botão antigo do Telegram pode
    ser clicado dias depois. Aceitar qualquer data reservava visita de madrugada, no passado ou
    num horário que nunca esteve na grade; `slot:abc` derrubava o turno. Fora da oferta, devolve
    None e o agendador oferece a grade de novo.
    """
    try:
        inicio = datetime.fromisoformat(texto[5:].split("|")[0].strip())
    except ValueError:
        return None
    if inicio.tzinfo is None:
        return None
    validos = list(state.get("horarios_oferecidos") or [])
    if state.get("horario_pendente"):
        validos.append(state["horario_pendente"])
    try:
        ofertados = {datetime.fromisoformat(h) for h in validos}
    except ValueError:
        ofertados = set()
    if inicio not in ofertados or inicio <= datetime.now(timezone.utc):
        return None
    return inicio


def _resolver_horario(texto: str, oferecidos: list[str]) -> datetime | None:
    """Casa texto livre ("terça às 14h", "o das 10", "amanhã 16h", "o primeiro") com um dos horários oferecidos."""
    if not oferecidos:
        return None
    slots = [datetime.fromisoformat(h) for h in oferecidos]
    t = _sem_acento(texto)
    ordinal = {"primeiro": 0, "primeira": 0, "segundo": 1, "segunda opcao": 1, "terceiro": 2, "ultimo": len(slots) - 1}
    for k, i in ordinal.items():
        if k in t and 0 <= i < len(slots):
            return slots[i]
    m = re.search(r"\b(\d{1,2})\s*(?:h|hs|hrs|horas|:\d{2})\b", t) or re.search(r"\b(?:as|das)\s+(\d{1,2})\b", t)
    hora = int(m.group(1)) if m else None
    if hora is None and "manha" in t:
        hora = 10
    if hora is not None and hora <= 8 and ("tarde" in t or ("manha" not in t and hora < 8)):
        hora += 12
    dia = next((v for k, v in _SEMANA.items() if re.search(rf"\b{k}\b", t)), None)
    hoje = datetime.now(_BR).date()
    data = re.search(r"\b(\d{1,2})/(\d{1,2})\b", t)
    alvo = None
    if data:
        try:
            alvo = hoje.replace(month=int(data.group(2)), day=int(data.group(1)))
        except ValueError:
            # "31/09", "50/50": data que não existe não casa com horário nenhum. Antes o
            # `ValueError` derrubava o turno, e o cliente ia parar no corretor por ter digitado errado.
            return None
    elif "amanha" in t:
        alvo = hoje + timedelta(days=1)
    candidatos = slots
    if alvo:
        candidatos = [s for s in candidatos if s.astimezone(_BR).date() == alvo]
    elif dia is not None:
        candidatos = [s for s in candidatos if s.astimezone(_BR).weekday() == dia]
    if hora is not None:
        candidatos = [s for s in candidatos if s.astimezone(_BR).hour == hora]
    # Só confirma quando a escolha é inequívoca: um único candidato, e o cliente disse pelo menos dia ou hora
    if len(candidatos) == 1 and (hora is not None or dia is not None or alvo is not None):
        return candidatos[0]
    return None


_ORDINAIS = {"primeiro": 0, "primeira": 0, "1o": 0, "segundo": 1, "segunda": 1, "2o": 1,
             "terceiro": 2, "terceira": 2, "3o": 2}


def _candidatos(state: AgentState, lead) -> list:
    """Os imóveis entre os quais o cliente está escolhendo: o ÚLTIMO lote mostrado, na ordem da tela."""
    sugeridos = state.get("imoveis_sugeridos") or []
    ultimos = state.get("ultimos_sugeridos") or []
    por_id = {c.id: c for c in sugeridos}            # o mesmo imóvel pode ter sido mostrado duas vezes
    lote = [por_id[i] for i in dict.fromkeys(ultimos) if i in por_id]
    return lote or list({c.id: c for c in sugeridos[-3:]}.values())


def _escolher_pelo_texto(txt: str, candidatos: list) -> str | None:
    """"o segundo", "o studio", "o de 33 m²", "o com 2 vagas" → o id, só quando for inequívoco."""
    t = _sem_acento(txt)
    for palavra, i in _ORDINAIS.items():
        if re.search(rf"\b{palavra}\b", t) and i < len(candidatos):
            return candidatos[i].id
    if re.search(r"\bultimo\b", t) and candidatos:
        return candidatos[-1].id
    palavras = set(re.findall(r"[a-z]{4,}|\d+", t))
    termos = [set(re.findall(r"[a-z]{4,}|\d+", _sem_acento(c.titulo))) for c in candidatos]
    # só conta o que distingue: palavra presente no título de TODOS ("mooca", "apartamento") não escolhe nada
    comuns = set.intersection(*termos) if termos else set()
    pontos = [len((palavras & tt) - comuns) for tt in termos]
    melhor = max(pontos, default=0)
    if melhor and pontos.count(melhor) == 1:
        return candidatos[pontos.index(melhor)].id
    return None


def _imovel_da_visita(state: AgentState, lead, txt: str) -> tuple[str | None, list]:
    """Qual imóvel o cliente quer visitar — ou None quando ele ainda não disse.

    Antes era sempre o primeiro da lista. Com três imóveis na tela, "Agendar visita" levava à
    grade de horários do primeiro, o modelo improvisava "qual desses você quer visitar?" em cima
    dos botões de HORÁRIO, o cliente clicava num horário e a visita era reservada no primeiro
    imóvel — que ele nunca escolheu.
    """
    candidatos = _candidatos(state, lead)
    if txt.startswith(ESCOLHA):
        return txt[len(ESCOLHA):].split("|")[0].strip() or None, candidatos
    if state.get("imovel_escolhido"):
        return state["imovel_escolhido"], candidatos
    if len(candidatos) == 1:
        return candidatos[0].id, candidatos
    if not candidatos:
        return (lead.cartao.imoveis_visualizados or [None])[0], candidatos     # veio da ficha do imóvel
    return _escolher_pelo_texto(txt, candidatos), candidatos


def _perguntar_imovel(state: AgentState, lead, candidatos: list) -> dict:
    """Pergunta qual imóvel antes de mostrar horário. Texto fixo: os botões dizem o resto."""
    lead.cartao.pediu_visita = True
    texto = "Claro! Qual deles você quer visitar? Escolha abaixo que eu te mostro os horários livres."
    return {"lead": lead, "horarios_oferecidos": [], "slots_crm": {}, "imovel_escolhido": None,
            "messages": [AIMessage(content=texto)],
            "resposta": RespostaAgente(lead_id=lead.id, texto=texto,
                                       opcoes=[f"{ESCOLHA}{c.id}|{c.titulo}" for c in candidatos])}


def _tem_contato(lead, canal) -> bool:
    """No site, a conversa some quando o cliente fecha a aba: sem telefone ou e-mail não há volta.
    No Telegram o chat continua aberto, e o corretor fala com ele por ali."""
    from sdr_shared.messaging import Canal
    return canal != Canal.WEB or bool(lead.telefone or lead.email or lead.cartao.tem_contato())


def _absorver_contato_da_mensagem(state: AgentState, lead, txt: str) -> None:
    """Enquanto o horário espera, a mensagem do cliente é (quase sempre) o contato pedido."""
    from .qualificador import _absorver_contato, _extrair, ultima_pergunta
    lead.cartao = _extrair(lead.cartao, txt, ultima_pergunta(state.get("messages")))
    _absorver_contato(lead)


def _pedir_contato(state: AgentState, lead, inicio: datetime, insistindo: bool = False) -> dict:
    """Segura o horário e pede o contato ANTES de reservar.

    Reservar primeiro e pedir depois deixava o corretor com uma visita marcada e ninguém para ligar
    quando o cliente fechava o chat logo após o clique — e o horário bloqueado para os outros.
    Texto fixo: é uma frase de processo, e o modelo tendia a confirmar a visita junto.
    """
    # Telefone, não "WhatsApp": o canal de mensagem da Vértice é o Telegram (ADR-0007), e o número
    # serve ao corretor para ligar ou mandar mensagem, seja qual for o aplicativo do cliente.
    o_que = "seu nome e telefone" if not lead.nome else "seu telefone"
    if insistindo:
        texto = (f"Pra reservar {formatar(inicio)} eu preciso de um contato: me passa {o_que}? "
                 "Se preferir, um corretor pode te atender direto.")
    else:
        texto = (f"Ótimo, {formatar(inicio)}! Pra eu reservar, me passa {o_que}? "
                 "O corretor usa esse contato para confirmar a visita e mandar a localização.")
    lead.cartao.pediu_visita = True
    return {"lead": lead, "horario_pendente": inicio.isoformat(), "messages": [AIMessage(content=texto)],
            "resposta": RespostaAgente(lead_id=lead.id, texto=texto,
                                       opcoes=["Falar com corretor"] if insistindo else [])}


def run(state: AgentState) -> dict:
    lead, entrada = state["lead"], state["entrada"]
    sugeridos = state.get("imoveis_sugeridos") or []
    txt = entrada.conteudo or ""
    imovel_id, candidatos = _imovel_da_visita(state, lead, txt)
    if imovel_id is None and candidatos:
        return _perguntar_imovel(state, lead, candidatos)

    inicio = None
    if txt.startswith("slot:"):                                   # botão (web ou Telegram) — independe do tipo
        inicio = _horario_do_botao(txt, state)
    elif state.get("horarios_oferecidos"):                        # texto livre depois de uma oferta
        inicio = _resolver_horario(txt, state["horarios_oferecidos"])
    pendente = state.get("horario_pendente")
    if inicio is None and pendente:                               # a resposta ao pedido de contato
        inicio = datetime.fromisoformat(pendente)
        _absorver_contato_da_mensagem(state, lead, txt)
        if not _tem_contato(lead, entrada.canal):
            return _pedir_contato(state, lead, inicio, insistindo=True)
    elif inicio is not None and not _tem_contato(lead, entrada.canal):
        if so_contato_na_mensagem(txt):                           # "sexta às 10h, 11 98765-4321"
            _absorver_contato_da_mensagem(state, lead, txt)
        if not _tem_contato(lead, entrada.canal):
            return _pedir_contato(state, lead, inicio)

    if inicio is not None:
        if not lead.corretor_id:                                  # visita ganha um corretor pela região (mesma regra do handoff)
            from sdr_shared.db import CorretorRepository
            if co := CorretorRepository().escolher(lead.cartao.regiao):
                lead.corretor_id = co.id
        card = next((c for c in sugeridos if c.id == imovel_id), None)
        bairro, cidade = _onde_fica(imovel_id, card)
        local = f"{bairro}, {cidade}" if bairro else cidade
        mapa = link_do_mapa(bairro, cidade)
        try:
            agendar(lead.id, imovel_id, inicio, corretor_id=lead.corretor_id,
                    titulo=f"Visita: {card.titulo}" if card else "Visita ao imóvel — Vértice Imóveis",
                    local=local, email_cliente=lead.email)
        except HorarioOcupado:
            # Alguém pegou o horário entre a oferta e o clique: reoferece em vez de confirmar em falso.
            return _oferecer(state, lead, imovel_id, txt, ocupado_agora=True)
        lead.estagio, lead.cartao.pediu_visita = Estagio.AGENDADO, True
        # A Mora reservou o horário; quem confirma a visita é o corretor. O pedido no CRM é o que
        # faz o painel dele mostrar a mesma coisa que o cliente ouviu. Falhar aqui não desfaz a
        # reserva: o cliente tem o horário e o corretor recebe a notificação de qualquer jeito.
        pedir_visita(lead, imovel_id, (state.get("slots_crm") or {}).get(inicio.isoformat()),
                     observacao=f"Pedido pela Mora no canal {entrada.canal.value}.")
        # Visita marcada sem telefone é visita perdida: é o momento natural de pedir o contato.
        pedir = ("" if lead.telefone or lead.cartao.tem_contato() else
                 "IMPORTANTE: ainda não temos o contato deste cliente. Ao confirmar, peça o telefone dele numa "
                 "frase, explicando o motivo (o corretor confirma a visita e manda a localização por lá).")
        msg = llm_conversa().invoke([carregar("agendador_reserva", nome=lead.nome or "cliente",
                                              imovel=descrever_imovel(imovel_id, sugeridos),
                                              escolhido=formatar(inicio),
                                              contexto_contato=pedir), *state["messages"]])
        visita = {"inicio": inicio.isoformat(), "duracao_min": 60, "imovel_id": imovel_id,
                  "titulo": f"Visita: {card.titulo}" if card else "Visita ao imóvel — Vértice Imóveis",
                  "local": local, "rotulo": formatar(inicio), "mapa": mapa}
        # O mapa vai em `dados.visita.mapa`, nunca no texto, e nunca escrito pelo modelo: URL que o
        # modelo escreve é URL que ele pode inventar, e esta leva alguém a um endereço físico. Cada
        # canal o mostra como BOTÃO — o card da visita no site, um botão de link no Telegram.
        # Colado no fim do texto, o link cru (uma linha de %2C e %C3%A3) ficava depois da pergunta
        # do telefone e a enterrava: a última coisa que o cliente lia era o mapa, não o pedido.
        texto = sanear(msg.content, lead.id)
        return {"lead": lead, "messages": [msg], "horarios_oferecidos": [], "slots_crm": {},
                "imovel_escolhido": None, "horario_pendente": None,
                "resposta": RespostaAgente(lead_id=lead.id, texto=texto, acao=Acao.AGENDAR,
                                           dados={"visita": visita})}

    return _oferecer(state, lead, imovel_id, txt)


def _oferecer(state: AgentState, lead, imovel_id, txt: str, ocupado_agora: bool = False) -> dict:
    """Monta a oferta de horários.

    Com imóvel definido, a disponibilidade vem do CRM: horário de visita a um imóvel é dado
    comercial da imobiliária, e é lá que o corretor o mantém. Sem imóvel escolhido ainda, ou sem
    CRM, vale a agenda do corretor — que é o que a Mora sempre soube fazer e continua funcionando
    sozinha. Lista vazia do CRM significa "não sei", nunca "não há": recusar uma visita por causa
    de uma falha de integração seria inventar indisponibilidade.
    """
    do_crm = horarios_do_imovel(imovel_id)
    slots_crm = {h.inicio.isoformat(): h.slot_id for h in do_crm if h.slot_id}
    horarios = [h.inicio for h in do_crm][:8] or listar_horarios(corretor_id=lead.corretor_id)[:8]
    lead.cartao.pediu_visita = True
    # Nota em TEXTO, e não um booleano no template: `Se {pedido_invalido} for verdadeiro…` obriga o
    # modelo a interpretar uma condição, e é o tipo de ambiguidade que ele resolve para o lado
    # errado justamente quando o cliente está esperando uma confirmação.
    pediu_hora = bool(state.get("horarios_oferecidos")) and bool(re.search(r"\d{1,2}\s*h|\d{1,2}:\d{2}", txt))
    nota = ("O cliente pediu um horário que não existe nesta agenda: diga isso em meia frase, sem pedir desculpas "
            "em excesso, e ofereça os disponíveis do mesmo dia ou o mais próximo." if pediu_hora else "")
    contexto = ("O horário que ele escolheu acabou de ser ocupado por outra pessoa. Diga isso em meia frase, "
                "sem culpar ninguém, e ofereça os que restam." if ocupado_agora else "")
    msg = llm_conversa().invoke([carregar("agendador", nome=lead.nome or "cliente",
                                          imovel=descrever_imovel(imovel_id, state.get("imoveis_sugeridos") or []),
                                          horarios=[formatar(h) for h in horarios], nota=nota,
                                          contexto_contato=contexto), *state["messages"]])
    # opcoes carregam o id `slot:<iso>` e o rótulo legível — o canal renderiza como lista
    return {"lead": lead, "messages": [msg], "horarios_oferecidos": [h.isoformat() for h in horarios],
            "slots_crm": slots_crm, "imovel_escolhido": imovel_id,
            "resposta": RespostaAgente(lead_id=lead.id, texto=sanear(msg.content, lead.id),
                                       opcoes=[f"slot:{h.isoformat()}|{formatar(h)}" for h in horarios])}
