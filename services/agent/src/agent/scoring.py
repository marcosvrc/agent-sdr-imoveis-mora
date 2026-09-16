"""Score e temperatura do lead: cartão + sinais de comportamento. Determinístico, sem LLM."""
from datetime import datetime, timedelta, timezone

from sdr_shared.models import Lead, Temperatura, Intencao

RESPOSTA_RAPIDA = timedelta(minutes=5)     # quem responde nesse intervalo está com o assunto na mão


def respondeu_rapido(ultima_interacao: datetime | None, agora: datetime | None = None) -> bool:
    """Intervalo entre o último turno e a mensagem que acabou de chegar.

    Não é o tempo do agente responder — é o tempo do CLIENTE voltar, que é o sinal de interesse.
    Primeira mensagem da conversa não conta: não há intervalo anterior para medir.
    """
    if ultima_interacao is None:
        return False
    agora = agora or datetime.now(timezone.utc)
    if ultima_interacao.tzinfo is None:
        ultima_interacao = ultima_interacao.replace(tzinfo=timezone.utc)
    return timedelta(0) <= agora - ultima_interacao <= RESPOSTA_RAPIDA


def calcular(lead: Lead, respondeu_rapido: bool = False) -> tuple[int, Temperatura]:
    c, s = lead.cartao, 0
    s += 15 if c.intencao != Intencao.INDEFINIDA else 0
    s += 10 if c.regiao else 0
    s += 15 if (c.preco_max or c.ticket) else 0
    s += 10 if (c.quartos or c.perfil_investidor) else 0
    s += {"imediata": 25, "3_meses": 15, "6_meses": 8}.get(c.urgencia or "", 0)
    s += 15 if c.pediu_visita else 0
    s += min(len(c.imoveis_visualizados), 3) * 3
    s += 5 if respondeu_rapido else 0
    s -= lead.followups_enviados * 10
    s = max(0, min(100, s))
    temp = Temperatura.QUENTE if s >= 60 else Temperatura.MORNO if s >= 30 else Temperatura.FRIO
    return s, temp
