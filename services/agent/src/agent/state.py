"""Estado único compartilhado por todos os nós do grafo."""
from typing import Annotated, TypedDict
from langchain_core.messages import RemoveMessage
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
    slots_crm: dict[str, str]                 # ISO → slot_id do CRM, quando a grade veio de lá
    resposta: RespostaAgente
    # Texto da mensagem cuja extração de cartão JÁ rodou neste turno. O handler zera a cada turno;
    # o qualificador preenche; o consultor, quando recebe o turno logo em seguida, não extrai de
    # novo a mesma frase — era uma chamada de modelo a mais em todo turno que completava o cartão.
    cartao_extraido_de: str | None


# Poda do histórico. `add_messages` só acrescenta, e o checkpointer guarda tudo: sem isto, um lead
# que conversa há três meses manda a conversa inteira ao modelo em cada turno — custo e latência
# crescendo com a idade do lead, e o limite de contexto lá na frente. O que é durável (nome,
# contato, intenção, orçamento, imóveis vistos) já vive no cartão e no banco, não no histórico.
MAX_HISTORICO = 40          # a partir daqui, poda
HISTORICO_APOS_PODA = 24    # o que fica: as últimas ~12 trocas


def podar_historico(messages: list) -> dict:
    """Devolve o delta de estado que remove as mensagens mais antigas, ou `{}` se não há o que podar.
    Poda em bloco (40 → 24) em vez de uma por turno para não reescrever o checkpoint a cada mensagem."""
    if len(messages) <= MAX_HISTORICO:
        return {}
    excedente = messages[:-HISTORICO_APOS_PODA]
    return {"messages": [RemoveMessage(id=m.id) for m in excedente if getattr(m, "id", None)]}
