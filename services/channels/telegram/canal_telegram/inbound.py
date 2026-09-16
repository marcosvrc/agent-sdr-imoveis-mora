"""Entrada do Telegram. Dois modos, mesma tradução (adapter.parse_inbound):

  * `handler()`     — webhook (perfil aws): a Bot API chama esta URL a cada mensagem.
  * `local_worker()`— long polling (perfil local): puxa updates com `getUpdates`, sem precisar de
    URL pública nem de túnel — só um `SDR_TELEGRAM_BOT_TOKEN` no `.env` (ver ADR-0007)."""
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


def handler(event, _ctx):
    """Perfil aws: `setWebhook` aponta para esta função. Telegram não assina o corpo — a segurança
    vem de a própria URL do webhook conter um segredo (`.../webhook/<token-secreto>`), configurado
    no CDK; não reaproveita `whatsapp_app_secret`, que é HMAC de outro provedor."""
    import json
    _publicar(json.loads(event["body"]))
    return {"statusCode": 200}


def local_worker():
    """Perfil local: um processo dedicado (ver `telegram-in` no compose). Sem fila própria — cada
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
