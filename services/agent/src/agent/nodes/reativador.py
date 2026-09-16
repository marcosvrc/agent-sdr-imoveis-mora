"""Aviso de imóvel novo para quem já tinha sumido. A única mensagem que a Mora manda sem ser chamada.

Duas metades da mesma responsabilidade:

- **avisar** — o critério de quem recebe já foi decidido antes (`sdr_shared.reativacao`, rodado pelo
  worker); aqui o trabalho é escrever bem: dizer POR QUE este imóvel e não outro, com os motivos que
  a pontuação produziu. Eles entram no prompt como fato dado — saíram da comparação entre o cartão e
  a ficha — e é isso que impede o texto de virar "apareceu algo que talvez te interesse", que é como
  todo mundo escreve e ninguém responde.
- **sair** — quem responde "não quero mais avisos" desliga o aviso na hora, pela conversa, sem
  depender de alguém abrir o painel. Um contato não pedido sem saída é spam, por melhor que seja o
  texto; e a saída tem de estar onde a mensagem chegou.
"""
import logging
import re
from datetime import datetime, timezone

from sdr_shared.db import InteresseRepository, LeadRepository, auditar
from sdr_shared.messaging import RespostaAgente, TipoMensagem
from ..llm import llm_conversa
from ..prompts import carregar
from ..state import AgentState
from ..tools.buscar_imoveis import montar_card
from ..guardrails.saida import sanear

log = logging.getLogger("agent.reativador")

# Saída explícita, na própria mensagem — e o botão é o que alimenta o opt-out sem ninguém precisar
# abrir o painel.
OPCOES = ["Quero ver", "Agendar visita", "Não quero mais avisos"]

PEDE_SAIR = re.compile(
    r"n[ãa]o (quero|queria|desejo)( mais)?( receber)?\s*(avisos?|novidades|mensagens|nada)"
    r"|parar de (receber|me avisar)|me tir[ae] da lista|sair da lista|descadastr|me remova|pare de me avisar",
    re.I)

CONFIRMACAO_SAIDA = ("Pronto, não te aviso mais quando entrar um imóvel novo. "
                     "Se mudar de ideia, é só me chamar aqui.")


def run(state: AgentState) -> dict:
    if state["entrada"].tipo == TipoMensagem.REATIVACAO:
        return _avisar(state)
    return _desligar_avisos(state)


def _avisar(state: AgentState) -> dict:
    from sdr_shared.db import ImovelRepository
    lead, entrada = state["lead"], state["entrada"]
    imovel_id = entrada.meta.get("imovel_id")
    motivos = [m for m in (entrada.meta.get("motivos") or []) if isinstance(m, str)]

    im = ImovelRepository().get(imovel_id) if imovel_id else None
    if not im:
        # O imóvel saiu do ar entre o enfileiramento e o consumo. Melhor não dizer nada do que
        # anunciar o que não existe mais: sem `resposta`, o turno morre aqui sem incomodar ninguém.
        log.warning("reativação abortada: imóvel %s não existe mais (lead %s)", imovel_id, lead.id)
        return {"lead": lead}

    card = montar_card(im, motivo=" · ".join(motivos) or None)
    dias = _dias_de_silencio(lead)
    msg = llm_conversa().invoke([carregar("reativacao", nome=lead.nome or "cliente",
                                          cartao=lead.cartao.model_dump(exclude_defaults=True),
                                          imovel=f"{card.titulo} — R$ {card.preco:,.0f}",
                                          motivos="; ".join(motivos) or "combina com o que ele procurava",
                                          dias=dias)])
    texto = sanear(msg.content, lead.id)

    # Carimbo e interesse são o que impede o segundo aviso: sem eles a cadência não tem em que se
    # apoiar e o mesmo lead receberia o mesmo imóvel toda vez que o worker rodasse.
    lead.reativado_em = datetime.now(timezone.utc)
    LeadRepository().marcar_reativacao(lead.id)
    try:
        InteresseRepository().registrar(lead.id, im.id, situacao="sugerido", origem="agente",
                                        motivo=" · ".join(motivos) or None)
    except Exception:
        log.warning("não consegui registrar o interesse sugerido do lead %s", lead.id, exc_info=True)
    auditar(acao="lead.reativado", entidade="lead", entidade_id=lead.id, ator_tipo="agente",
            ator_nome="Mora", dados={"imovel_id": im.id, "pontos": entrada.meta.get("pontos"),
                                     "motivos": motivos, "dias_em_silencio": dias})

    return {"lead": lead, "messages": [msg], "imoveis_sugeridos": (state.get("imoveis_sugeridos") or []) + [card],
            "resposta": RespostaAgente(lead_id=lead.id, texto=texto, imoveis=[card], opcoes=OPCOES)}


def _desligar_avisos(state: AgentState) -> dict:
    """Resposta fixa, sem modelo: confirmar uma preferência é um recibo, e recibo não se improvisa —
    além de que gerar o texto abriria espaço para a Mora tentar convencer a pessoa a ficar."""
    lead = state["lead"]
    lead.aceita_reativacao = False
    LeadRepository().definir_aceita_reativacao(lead.id, False)
    auditar(acao="lead.optout_reativacao", entidade="lead", entidade_id=lead.id, ator_tipo="cliente",
            ator_nome=lead.nome or lead.id, origem=str(state["entrada"].canal.value),
            detalhe="pediu para não receber avisos de imóvel novo")
    log.info("lead %s pediu para não receber avisos de imóvel novo", lead.id)
    return {"lead": lead,
            "resposta": RespostaAgente(lead_id=lead.id, texto=CONFIRMACAO_SAIDA,
                                       opcoes=["Falar com corretor"])}


def _dias_de_silencio(lead) -> int:
    if not lead.ultima_mensagem_em:
        return 0
    return max(0, (datetime.now(timezone.utc) - lead.ultima_mensagem_em).days)
