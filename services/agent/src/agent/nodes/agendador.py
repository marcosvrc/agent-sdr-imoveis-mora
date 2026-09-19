"""Turno 1: oferece horários (lista). Turno 2 (botão `slot:<iso>`): confirma, grava visita, publica evento."""
import re
import unicodedata
from datetime import datetime, timedelta, timezone

from sdr_shared.messaging import RespostaAgente, Acao
from sdr_shared.models import Estagio
from ..llm import llm_conversa
from ..prompts import carregar
from ..state import AgentState
from ..guardrails.saida import sanear
from sdr_shared.crm import horarios_do_imovel, pedir_visita

from ..tools.agenda import HorarioOcupado, listar_horarios, agendar, formatar

DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
_SEMANA = {"segunda": 0, "seg": 0, "terca": 1, "ter": 1, "quarta": 2, "qua": 2, "quinta": 3, "qui": 3, "sexta": 4, "sex": 4,
           "sabado": 5, "sab": 5, "domingo": 6, "dom": 6}
_BR = timezone(timedelta(hours=-3))


def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


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
        alvo = hoje.replace(month=int(data.group(2)), day=int(data.group(1)))
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


def run(state: AgentState) -> dict:
    lead, entrada = state["lead"], state["entrada"]
    sugeridos = state.get("imoveis_sugeridos") or []
    imovel_id = sugeridos[0].id if sugeridos else (lead.cartao.imoveis_visualizados or [None])[0]
    txt = entrada.conteudo or ""

    inicio = None
    if txt.startswith("slot:"):                                   # botão (web ou WhatsApp) — independe do tipo
        inicio = datetime.fromisoformat(txt[5:])
    elif state.get("horarios_oferecidos"):                        # texto livre depois de uma oferta
        inicio = _resolver_horario(txt, state["horarios_oferecidos"])

    if inicio is not None:
        if not lead.corretor_id:                                  # visita ganha um corretor pela região (mesma regra do handoff)
            from sdr_shared.db import CorretorRepository
            if co := CorretorRepository().escolher(lead.cartao.regiao):
                lead.corretor_id = co.id
        card = next((c for c in sugeridos if c.id == imovel_id), None)
        local = (card.titulo.split("·")[-1].strip() + ", São Paulo") if card else "São Paulo"
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
                 "IMPORTANTE: ainda não temos o contato deste cliente. Ao confirmar, peça o WhatsApp dele numa "
                 "frase, explicando o motivo (o corretor confirma a visita e manda a localização por lá).")
        msg = llm_conversa().invoke([carregar("agendador", nome=lead.nome or "cliente", imovel=imovel_id or "a definir",
                                              horarios="", confirmado=True, escolhido=formatar(inicio),
                                              contexto_contato=pedir), *state["messages"]])
        visita = {"inicio": inicio.isoformat(), "duracao_min": 60, "imovel_id": imovel_id,
                  "titulo": f"Visita: {card.titulo}" if card else "Visita ao imóvel — Vértice Imóveis",
                  "local": local, "rotulo": formatar(inicio)}
        return {"lead": lead, "messages": [msg], "horarios_oferecidos": [], "slots_crm": {},
                "resposta": RespostaAgente(lead_id=lead.id, texto=sanear(msg.content, lead.id), acao=Acao.AGENDAR,
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
    # Cliente pediu um horário que não existe na agenda (ex.: 17h): explicar e reoferecer, sem inventar
    pedido_invalido = bool(state.get("horarios_oferecidos")) and bool(re.search(r"\d{1,2}\s*h|\d{1,2}:\d{2}", txt))
    contexto = ("O horário que ele escolheu acabou de ser ocupado por outra pessoa. Diga isso em meia frase, "
                "sem culpar ninguém, e ofereça os que restam." if ocupado_agora else "")
    msg = llm_conversa().invoke([carregar("agendador", nome=lead.nome or "cliente", imovel=imovel_id or "a definir",
                                          horarios=[formatar(h) for h in horarios], confirmado=False, escolhido="",
                                          pedido_invalido=pedido_invalido, contexto_contato=contexto), *state["messages"]])
    # opcoes carregam o id `slot:<iso>` e o rótulo legível — o canal renderiza como lista
    return {"lead": lead, "messages": [msg], "horarios_oferecidos": [h.isoformat() for h in horarios],
            "slots_crm": slots_crm,
            "resposta": RespostaAgente(lead_id=lead.id, texto=sanear(msg.content, lead.id),
                                       opcoes=[f"slot:{h.isoformat()}|{formatar(h)}" for h in horarios])}
