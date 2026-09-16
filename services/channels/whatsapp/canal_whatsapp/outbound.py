"""Consome SQS sdr-outbound-whatsapp e envia pela Cloud API. Fora da janela de 24h usa template."""
import json
import httpx
from datetime import datetime, timedelta, timezone
from sdr_shared.config import get_settings
from sdr_shared.db import LeadRepository
from sdr_shared.messaging import RespostaAgente
from .adapter import render
from .templates import template_followup


def _fora_da_janela(lead_id: str) -> bool:
    lead = LeadRepository().get(lead_id)
    return bool(lead and lead.ultima_mensagem_em and
                datetime.now(timezone.utc) - lead.ultima_mensagem_em > timedelta(hours=24))


def enviar(body_json: str) -> None:
    s = get_settings()
    url = f"https://graph.facebook.com/v21.0/{s.whatsapp_phone_number_id}/messages"
    body = json.loads(body_json)
    r = RespostaAgente.model_validate(body["resposta"])
    payloads = [template_followup(body["identificador"], r)] if _fora_da_janela(r.lead_id) \
        else render(body["identificador"], r)
    with httpx.Client(headers={"Authorization": f"Bearer {s.whatsapp_token}"}, timeout=10) as http:
        for p in payloads:
            http.post(url, json=p).raise_for_status()


def handler(event, _ctx):                       # perfil aws
    for rec in event["Records"]:
        enviar(rec["body"])


def local_worker():                             # perfil local
    from sdr_shared.ports import get_broker
    get_broker().consume("outbound-whatsapp", enviar)
