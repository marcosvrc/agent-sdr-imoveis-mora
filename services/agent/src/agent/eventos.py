"""Consumidor do tópico `resumir` (lead agendado/handoff) → nó Resumidor fora da conversa."""
import json
from .handler import resumir


def handler(event, _ctx):                       # perfil aws: SQS sdr-resumir → Lambda
    for rec in event["Records"]:
        resumir(json.loads(rec["body"])["lead_id"])


def local_worker():                             # perfil local
    from sdr_shared.db import iniciar_batimento
    from sdr_shared.ports import get_broker

    iniciar_batimento("resumidor")
    get_broker().consume("resumir", lambda body: resumir(json.loads(body)["lead_id"]))
