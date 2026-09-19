"""Entrada do Telegram, por long polling (`getUpdates`).

Havia aqui também um `handler()` de webhook, para a Bot API chamar uma URL pública. Saiu com a AWS:
sem função hospedada não há URL pública, e o long polling não precisa de uma — basta um
`SDR_TELEGRAM_BOT_TOKEN` no `.env` (ver ADR-0007), o que é justamente o que torna a entrega
reproduzível na máquina de quem avalia.

A tradução do update é do `adapter.parse_inbound`, compartilhada com o resto do canal."""
import logging
import time

import httpx
from sdr_shared.config import get_settings
from sdr_shared.db import LeadRepository, CanalRepository
from sdr_shared.models import Lead
from sdr_shared.ports import get_broker
from .adapter import parse_inbound

log = logging.getLogger("canal_telegram")


def _resolver_lead(chat_id: str, nome: str | None) -> str:
    """chat_id → lead existente ou novo (o mesmo lead pode ter vindo do site antes, por telefone)."""
    repo = LeadRepository()
    if lead := repo.get_por_canal("telegram", chat_id):
        return lead.id
    lead = repo.upsert(Lead(id=f"tg_{chat_id}", nome=nome))
    CanalRepository().vincular(lead.id, "telegram", chat_id)
    return lead.id


def _publicar(update: dict) -> None:
    for msg in parse_inbound(update, resolver_lead=_resolver_lead):
        get_broker().publish("inbound", msg.model_dump_json(), key=msg.lead_id)   # ordem por lead garantida


def local_worker():
    """Um processo dedicado (ver `telegram-in` no compose). Sem fila própria — cada
    update processado avança o `offset`, então nada é entregue duas vezes mesmo se o processo cair
    e reiniciar (o Telegram guarda os updates não confirmados por até 24h)."""
    s = get_settings()
    if not s.telegram_bot_token:
        log.warning("SDR_TELEGRAM_BOT_TOKEN não configurado — worker do Telegram não vai subir")
        return
    from sdr_shared.db import iniciar_batimento
    iniciar_batimento("telegram-in")
    base = f"https://api.telegram.org/bot{s.telegram_bot_token}"
    offset = None
    with httpx.Client(timeout=35) as http:
        while True:
            try:
                params = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
                if offset is not None:
                    params["offset"] = offset
                r = http.get(f"{base}/getUpdates", params=params)
                r.raise_for_status()
                for u in r.json().get("result", []):
                    offset = u["update_id"] + 1
                    try:
                        _publicar(u)
                    except Exception:
                        log.exception("falha processando update %s do Telegram", u.get("update_id"))
            except Exception:
                log.exception("getUpdates falhou — tentando de novo em 5s")
                time.sleep(5)
