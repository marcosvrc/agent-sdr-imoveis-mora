"""Consome outbound-telegram e envia pela Bot API. Sem janela de 24h nem template aprovado — a
única regra do Telegram é o cliente ter dado /start no bot antes (senão a API recusa o envio)."""
import json
import httpx
from sdr_shared.config import get_settings
from sdr_shared.messaging import RespostaAgente
from .adapter import render


def enviar(body_json: str) -> None:
    s = get_settings()
    base = f"https://api.telegram.org/bot{s.telegram_bot_token}"
    body = json.loads(body_json)
    r = RespostaAgente.model_validate(body["resposta"])
    with httpx.Client(timeout=10) as http:
        for p in render(body["identificador"], r):
            metodo = p.pop("_method")
            http.post(f"{base}/{metodo}", json=p).raise_for_status()


def local_worker():
    from sdr_shared.db import iniciar_batimento
    from sdr_shared.ports import get_broker
    iniciar_batimento("telegram-out")
    get_broker().consume("outbound-telegram", enviar)
