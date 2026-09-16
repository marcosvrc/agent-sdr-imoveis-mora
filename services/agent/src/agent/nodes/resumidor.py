"""Roda fora do turno do lead (mensagem tipo sistema `resumir`). Gera para o corretor:
  1. briefing em texto (o que apareceu na conversa);
  2. análise estruturada — sentimento, engajamento, perfil de comunicação/decisão e como abordar.
A análise é inferência sobre o texto da conversa, não avaliação clínica; o prompt exige ancorar cada leitura no que foi dito."""
import logging
from datetime import datetime, timezone

from sdr_shared.db import notificar
from sdr_shared.models import AnaliseLead
from ..guardrails.saida import sanear
from ..llm import llm_analise
from ..prompts import carregar
from ..state import AgentState

log = logging.getLogger(__name__)


def run(state: AgentState) -> dict:
    lead = state["lead"]
    historico = state["messages"]
    resumo = llm_analise().invoke([carregar("resumidor", cartao=lead.cartao.model_dump(exclude_defaults=True)), *historico])
    # o briefing vai para a tela do corretor: passa pelo mesmo filtro da fala com o cliente
    lead.resumo = sanear(resumo.content, lead.id)
    lead.analisado_em = datetime.now(timezone.utc)      # carimba já: o briefing saiu, mesmo se a análise falhar
    try:
        analise = llm_analise().with_structured_output(AnaliseLead).invoke(
            [carregar("analise", nome=lead.nome or "cliente", estagio=lead.estagio, cartao=lead.cartao.model_dump(exclude_defaults=True)), *historico])
        if isinstance(analise, AnaliseLead):
            analise.confianca = max(0.0, min(1.0, float(analise.confianca)))
            lead.analise = analise
    except Exception:                                   # análise é complementar: nunca derruba o briefing
        log.exception("análise do lead %s falhou", lead.id)

    if lead.corretor_id:                                # só avisa quem já tem o lead na mão
        quem = lead.nome or lead.telefone or lead.id
        notificar(tipo="briefing.pronto", corretor_id=lead.corretor_id, lead_id=lead.id,
                  titulo=f"Briefing de {quem} pronto",
                  detalhe=(lead.analise.resumo_perfil if lead.analise else None) or "Leia antes de ligar.",
                  dados={"tem_analise": bool(lead.analise)},
                  chave=lead.analisado_em.isoformat())
    return {"lead": lead}
