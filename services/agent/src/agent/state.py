"""Estado único compartilhado por todos os nós do grafo."""
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages
from sdr_shared.models import Lead, ImovelCard
from sdr_shared.messaging import MensagemNormalizada, RespostaAgente


class AgentState(TypedDict, total=False):
    messages: Annotated[list, add_messages]   # histórico (checkpointer em Postgres = memória conversacional)
    lead: Lead
    entrada: MensagemNormalizada
    primeira_interacao: bool
    proximo: str                              # decisão do supervisor
    saltos: int                               # guarda contra pingue-pongue (máx. 4)
    veredito: object                          # resultado do porteiro de escopo (guardrails.escopo)
    recusas: int                              # quantas vezes este lead já foi recusado (persiste no checkpoint)
    imoveis_sugeridos: list[ImovelCard]
    horarios_oferecidos: list[str]            # ISO strings, para o turno de confirmação
    resposta: RespostaAgente
