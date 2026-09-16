"""Envia um payload da Meta Cloud API para o webhook local/deployado. Uso: python scripts/simular_webhook.py "texto" [url]"""
import hashlib
import hmac
import json
import os
import sys
import httpx

texto = sys.argv[1]; url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8001/webhook"
payload = {"entry": [{"changes": [{"value": {"contacts": [{"wa_id": "5511999990000", "profile": {"name": "Lead Teste"}}],
                                             "messages": [{"from": "5511999990000", "type": "text", "text": {"body": texto}}]}}]}]}
body = json.dumps(payload)
sig = "sha256=" + hmac.new(os.environ.get("SDR_WHATSAPP_APP_SECRET", "").encode(), body.encode(), hashlib.sha256).hexdigest()
print(httpx.post(url, content=body, headers={"x-hub-signature-256": sig, "content-type": "application/json"}).status_code)
