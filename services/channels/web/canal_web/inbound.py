"""API Gateway WebSocket: $connect / $disconnect / message. Widget do site e dashboard usam a mesma API."""
import json
from sdr_shared.ports import get_broker
from sdr_shared.messaging import MensagemNormalizada, Canal
from . import connections


def handler(event, _ctx):
    rc = event["requestContext"]
    cid, route = rc["connectionId"], rc["routeKey"]
    if route == "$connect":
        qs = event.get("queryStringParameters") or {}
        connections.registrar(cid, qs.get("papel", "lead"), qs.get("id", cid))   # papel=dashboard exige JWT Cognito (authorizer)
        return {"statusCode": 200}
    if route == "$disconnect":
        connections.remover(cid)
        return {"statusCode": 200}

    body = json.loads(event["body"])
    session_id = body["session_id"]
    msg = MensagemNormalizada(lead_id=f"web_{session_id}", canal=Canal.WEB, identificador_canal=session_id,
                              conteudo=body["texto"], meta=body.get("meta", {}))
    get_broker().publish("inbound", msg.model_dump_json(), key=msg.lead_id)
    return {"statusCode": 200}
