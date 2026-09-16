"""Acionado pelo scheduler. Retoma a conversa com contexto; o canal cuida da janela de 24h."""
from sdr_shared import followup as politica_followup
from sdr_shared.db import auditar
from sdr_shared.messaging import RespostaAgente
from sdr_shared.models import Estagio
from ..llm import llm_conversa
from ..prompts import carregar
from ..state import AgentState
from ..guardrails.saida import sanear


def run(state: AgentState) -> dict:
    lead = state["lead"]
    tentativa = lead.followups_enviados + 1
    total = len(politica_followup.politica_cacheada()["tempos_min"])
    msg = llm_conversa().invoke([carregar("followup", nome=lead.nome or "cliente", tentativa=tentativa,
                                          total=total, ultima="sim" if tentativa >= total else "não",
                                          cartao=lead.cartao.model_dump(exclude_defaults=True)), *state["messages"]])
    lead.followups_enviados = tentativa
    # esgotou as tentativas → frio (sai do fluxo); ainda há o que tentar → inativo
    lead.estagio = Estagio.FRIO if tentativa >= total else Estagio.INATIVO
    auditar(acao="lead.followup_enviado", entidade="lead", entidade_id=lead.id, ator_tipo="agente",
            ator_nome="Mora", dados={"tentativa": tentativa, "de": total, "estagio": str(lead.estagio.value)})
    return {"lead": lead, "messages": [msg], "resposta": RespostaAgente(lead_id=lead.id, texto=sanear(msg.content, lead.id))}
