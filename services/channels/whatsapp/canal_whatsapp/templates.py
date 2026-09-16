"""Templates aprovados na Meta (obrigatórios fora da janela de 24h)."""
from sdr_shared.messaging import RespostaAgente


def template_followup(telefone: str, r: RespostaAgente) -> dict:
    return {"messaging_product": "whatsapp", "to": telefone, "type": "template", "template": {
        "name": "sdr_followup_v1", "language": {"code": "pt_BR"},
        "components": [{"type": "body", "parameters": [{"type": "text", "text": r.texto[:1000]}]}]}}
