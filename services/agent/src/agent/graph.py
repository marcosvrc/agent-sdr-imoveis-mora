"""Supervisor + especialistas sobre um estado único. Só Qualificador, Consultor e Agendador falam com o lead."""
import logging
import time

from langgraph.graph import StateGraph, END
from contextvars import ContextVar

from sdr_shared.governanca import ctx_lead, ctx_no
from .state import AgentState
from .nodes import (supervisor, qualificador, consultor, agendador, followup, resumidor, handoff,
                    informacoes,
                    recusa, reativador)

log = logging.getLogger("agent.graph")

# Caminho percorrido no turno, para o registro em `turnos` (ADR-0011). ContextVar (não global)
# porque o worker pode processar turnos de leads diferentes em threads distintas — e é o handler
# quem zera e lê, no início e no fim. Guarda a MESMA lista e só faz append: o LangGraph roda cada
# nó num contexto copiado, então um `caminho.set(...)` lá dentro se perderia na volta; a cópia
# compartilha o objeto, não a atribuição.
caminho: ContextVar[list | None] = ContextVar("caminho", default=None)


def novo_caminho() -> list:
    lista: list = []
    caminho.set(lista)
    return lista


def caminho_atual() -> list:
    return caminho.get() or []


def _cronometrado(nome: str, fn):
    """Loga a duração de cada nó — é o que permite ver onde o tempo do turno vai (LLM, embedding, DB)."""
    def run(state: AgentState) -> dict:
        t0 = time.perf_counter()
        ctx_no.set(nome); ctx_lead.set(state["lead"].id)      # atribui o consumo de tokens ao nó e ao lead
        if (trilha := caminho.get()) is not None:
            trilha.append(nome)                               # registra por onde o turno passou
        out = fn(state)
        log.info("nó %-12s %6.2fs lead=%s → proximo=%s resposta=%s", nome, time.perf_counter() - t0,
                 state["lead"].id, out.get("proximo", "-"), "sim" if out.get("resposta") else "não")
        return out
    return run

MAX_SALTOS = 4
ESPECIALISTAS = ("qualificador", "consultor", "agendador", "followup", "resumidor", "handoff",
                 "recusa", "reativador", "informacoes")


def _rotear(state: AgentState) -> str:
    if state.get("resposta") or state.get("saltos", 0) >= MAX_SALTOS:
        return END
    return state.get("proximo") or "qualificador"


def build_graph(checkpointer=None):
    g = StateGraph(AgentState)
    g.add_node("supervisor", _cronometrado("supervisor", supervisor.run))
    # strict: acrescentar um nó a só uma das duas listas passaria despercebido — o zip truncaria
    # em silêncio e o especialista simplesmente não existiria no grafo.
    for nome, mod in zip(ESPECIALISTAS, (qualificador, consultor, agendador, followup, resumidor,
                                         handoff, recusa, reativador, informacoes), strict=True):
        g.add_node(nome, _cronometrado(nome, mod.run))

    g.set_entry_point("supervisor")
    g.add_conditional_edges("supervisor", _rotear, {**{n: n for n in ESPECIALISTAS}, END: END})
    for n in ("qualificador", "consultor", "agendador", "followup", "handoff", "recusa",
              "reativador", "informacoes"):
        g.add_edge(n, "supervisor")        # volta ao supervisor; ele encerra ao ver `resposta`
    g.add_edge("resumidor", END)
    return g.compile(checkpointer=checkpointer)


def build_checkpointer():
    """Checkpointer Postgres (thread_id = lead_id)."""
    from psycopg import Connection
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from sdr_shared.config import get_settings
    conn = Connection.connect(get_settings().database_dsn, autocommit=True, prepare_threshold=0)
    # Registra os tipos nossos que vão ao checkpoint (silencia "Deserializing unregistered type" e evita o bloqueio futuro)
    try:
        serde = JsonPlusSerializer(allowed_msgpack_modules=[("sdr_shared.models.lead", "Lead"), ("sdr_shared.models.lead", "Estagio"),
                                                            ("sdr_shared.models.lead", "Intencao"), ("sdr_shared.models.lead", "Temperatura"),
                                                            ("sdr_shared.models.lead", "CartaoQualificacao"), ("sdr_shared.models.imovel", "ImovelCard"),
                                                            ("sdr_shared.messaging.contracts", "MensagemNormalizada"), ("sdr_shared.messaging.contracts", "RespostaAgente"),
                                                            ("sdr_shared.messaging.contracts", "Canal"), ("sdr_shared.messaging.contracts", "TipoMensagem"),
                                                            ("sdr_shared.messaging.contracts", "Acao")])
    except TypeError:                                   # versão antiga do langgraph sem o parâmetro
        serde = JsonPlusSerializer()
    saver = PostgresSaver(conn, serde=serde)
    saver.setup()
    return saver
