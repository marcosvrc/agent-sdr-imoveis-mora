"""O "digitando…" do Telegram enquanto a Mora pensa.

O turno leva de 3 a 10 s (modelo de extração + modelo de conversa), e no Telegram esse intervalo era
silêncio: o site mostra "digitando", o bot não mostrava nada. Silêncio de 8 s depois de mandar uma
mensagem parece falha. `sendChatAction` mostra o indicador por até 5 s — ou até a próxima mensagem do
bot —, então ele é renovado a cada 4 s até a resposta aparecer no histórico.

Quem sabe quando parar é o banco: o agente registra a mensagem de saída ANTES de despachá-la, então
`houve_saida_desde` vira verdadeiro um instante antes de a resposta chegar ao cliente. O teto cobre o
turno que não responde (handoff, vazão excedida, falha): o indicador não fica aceso para sempre.
"""
import logging
import threading
import time
from datetime import datetime, timezone

import httpx

log = logging.getLogger("canal_telegram.digitando")

INTERVALO_S = 4.0          # o indicador some sozinho em ~5 s
TETO_S = 30.0              # turno mais longo que isso já caiu no fallback; não prometer resposta

_ativos: dict[str, threading.Thread] = {}
_trava = threading.Lock()


def _laco(base: str, chat_id: str, lead_id: str, desde: datetime, respondeu, dormir) -> None:
    fim = time.monotonic() + TETO_S
    try:
        with httpx.Client(timeout=5) as http:
            while time.monotonic() < fim:
                try:
                    if respondeu(lead_id, desde):
                        return
                    http.post(f"{base}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})
                except Exception as e:
                    # Indicador é cortesia: falhar aqui não pode virar log ruidoso nem levar a URL
                    # (com o token) para o log — só o tipo do erro.
                    log.debug("sendChatAction falhou (%s)", type(e).__name__)
                dormir(INTERVALO_S)
    finally:
        with _trava:
            _ativos.pop(chat_id, None)


def iniciar(base: str, chat_id: str, lead_id: str, *, respondeu=None, dormir=time.sleep) -> bool:
    """Liga o indicador para este chat. Devolve False se já havia um aceso (mensagens seguidas do
    mesmo cliente não abrem uma linha de execução por mensagem)."""
    if respondeu is None:
        from sdr_shared.db import MensagemRepository
        respondeu = MensagemRepository().houve_saida_desde
    with _trava:
        if chat_id in _ativos:
            return False
        t = threading.Thread(target=_laco, name=f"digitando-{chat_id}", daemon=True,
                             args=(base, chat_id, lead_id, datetime.now(timezone.utc), respondeu, dormir))
        _ativos[chat_id] = t
    t.start()
    return True
