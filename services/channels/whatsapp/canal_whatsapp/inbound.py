"""Lambda do webhook da Meta Cloud API. Valida HMAC, normaliza, enfileira. Responde em < 100 ms."""
import hashlib
import hmac
import json
from sdr_shared.ports import get_broker
from sdr_shared.config import get_settings
from sdr_shared.db import LeadRepository, CanalRepository
from sdr_shared.models import Lead
from .adapter import parse_inbound


def _assinatura_valida(headers: dict, body: str) -> bool:
    secret = get_settings().whatsapp_app_secret or ""
    esperado = "sha256=" + hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, headers.get("x-hub-signature-256", ""))


def _resolver_lead(telefone: str, nome_perfil: str | None) -> str:
    """Telefone → lead existente ou novo (o mesmo lead pode ter vindo da web antes)."""
    repo = LeadRepository()
    if lead := repo.get_por_canal("whatsapp", telefone):
        return lead.id
    lead = repo.upsert(Lead(id=f"lead_{telefone[-8:]}", nome=nome_perfil, telefone=telefone))
    CanalRepository().vincular(lead.id, "whatsapp", telefone)
    return lead.id


def handler(event, _ctx):
    s = get_settings()
    qs = event.get("queryStringParameters") or {}
    if event["requestContext"]["http"]["method"] == "GET":            # verificação do webhook
        ok = qs.get("hub.verify_token") == s.whatsapp_verify_token
        return {"statusCode": 200 if ok else 403, "body": qs.get("hub.challenge", "")}

    body = event["body"]
    if not _assinatura_valida({k.lower(): v for k, v in event["headers"].items()}, body):
        return {"statusCode": 401}

    for msg in parse_inbound(json.loads(body), resolver_lead=_resolver_lead):
        get_broker().publish("inbound", msg.model_dump_json(), key=msg.lead_id)   # ordem por lead garantida
    return {"statusCode": 200}
