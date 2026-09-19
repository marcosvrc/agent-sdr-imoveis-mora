"""Responde "como a imobiliária trabalha" com base nos documentos dela (RAG institucional).

O catálogo responde *qual imóvel*; este nó responde *taxa, documentação, prazo, política de visita,
financiamento, garantia*. Antes dele, essas perguntas caíam no qualificador ou no consultor, que
não têm fonte para elas — e um modelo sem fonte sobre política de empresa não fica em silêncio:
ele responde com a média do mercado, que é plausível, específica e frequentemente falsa.

Três decisões que tornam este nó confiável:

1. **Nada sai sem trecho.** Sem recuperação acima do piso, o caminho é outro prompt, que diz "vou
   confirmar" e não deixa espaço para o modelo preencher a lacuna.
2. **O texto recuperado é neutralizado.** É conteúdo externo entrando no prompt — o mesmo vetor de
   injeção de segunda ordem que o card de imóvel tem, e o mesmo tratamento.
3. **A fonte é citada.** Resposta sobre política sem origem é indistinguível de invenção, tanto
   para o cliente quanto para o corretor que vai ter que honrá-la depois.
"""
import logging

from sdr_shared.db import auditar
from sdr_shared.messaging import RespostaAgente

from ..guardrails.saida import sanear
from ..llm import llm_conversa
from ..prompts import carregar
from ..state import AgentState
from ..tools.conhecimento import consultar
from ..util import neutralizar_texto_externo

log = logging.getLogger("agent.informacoes")

LIMITE_TRECHO = 1200


def _formatar(trechos) -> str:
    return "\n\n".join(
        f"### {t.fonte}\n{neutralizar_texto_externo(t.texto, limite=LIMITE_TRECHO)}"
        for t in trechos)


def run(state: AgentState) -> dict:
    lead, entrada = state["lead"], state["entrada"]
    pergunta = entrada.conteudo or ""

    try:
        trechos = consultar(pergunta)
    except Exception:
        # Falha da busca não pode virar invenção: segue pelo caminho do "vou confirmar".
        log.warning("busca institucional falhou para o lead %s", lead.id, exc_info=True)
        trechos = []

    if trechos:
        prompt = carregar("informacoes", mensagem=pergunta, trechos=_formatar(trechos),
                          exemplo_fonte=trechos[0].fonte)
    else:
        prompt = carregar("informacoes_sem_base", mensagem=pergunta)

    msg = llm_conversa().invoke([prompt, *state["messages"]])

    auditar(acao="agente.consulta_institucional", entidade="lead", entidade_id=lead.id,
            ator_tipo="agente", ator_nome="Mora", origem=str(entrada.canal.value),
            resultado="ok" if trechos else "vazio",
            detalhe=None if trechos else "nenhum trecho acima do piso de similaridade",
            dados={"fontes": [t.id for t in trechos],
                   "scores": [round(t.score, 3) for t in trechos]})

    return {"lead": lead, "messages": [msg],
            "resposta": RespostaAgente(lead_id=lead.id, texto=sanear(msg.content, lead.id),
                                       opcoes=["Falar com corretor"] if not trechos else [])}
