"""Recusa educada: mensagem fora do escopo não vira turno de LLM nem queima um corretor humano.

A resposta é texto fixo — não passa pelo modelo, então não há o que vazar nem como a própria
mensagem recusada influenciar o que o agente diz de volta.
"""
from sdr_shared.db import auditar
from sdr_shared.messaging import RespostaAgente

from ..guardrails.escopo import INSISTENCIA, MAX_RECUSAS, RESPOSTAS
from ..state import AgentState


def run(state: AgentState) -> dict:
    lead = state["lead"]
    veredito = state.get("veredito")
    categoria = getattr(veredito, "categoria", "fora_do_dominio")
    recusas = state.get("recusas", 0) + 1

    insistiu = recusas >= MAX_RECUSAS
    texto = INSISTENCIA if insistiu else RESPOSTAS.get(categoria, RESPOSTAS["fora_do_dominio"])
    auditar(acao="agente.mensagem_recusada", entidade="lead", entidade_id=lead.id, ator_tipo="agente",
            ator_nome="Mora", origem=str(state["entrada"].canal.value), resultado="ok",
            detalhe=getattr(veredito, "detalhe", "") or None,
            dados={"categoria": categoria, "recusas_no_lead": recusas, "ofereceu_humano": insistiu})
    resposta = RespostaAgente(lead_id=lead.id, texto=texto,
                              opcoes=["Falar com corretor"] if insistiu else [])
    return {"lead": lead, "recusas": recusas, "resposta": resposta}
