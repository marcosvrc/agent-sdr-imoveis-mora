"""Consome sdr-outbound-web: entrega ao widget (session) e espelha para o dashboard (tempo real)."""
import json
import os
from functools import lru_cache
from . import connections


@lru_cache
def _api():
    import boto3
    return boto3.client("apigatewaymanagementapi", endpoint_url=os.environ["WS_ENDPOINT"])


def _push(cids: list[str], data: dict) -> None:
    api = _api()
    for cid in cids:
        try:
            api.post_to_connection(ConnectionId=cid, Data=json.dumps(data).encode())
        except api.exceptions.GoneException:
            connections.remover(cid)          # conexão fechada pelo cliente: limpa o registro


def entregar(body: dict) -> None:
    _push(connections.conexoes("lead", body["identificador"]), body["resposta"])   # widget renderiza texto/opcoes/imoveis
    _push(connections.conexoes("dashboard"), {"evento": "mensagem", **body})       # painel do corretor ao vivo


def handler(event, _ctx):
    for rec in event["Records"]:
        entregar(json.loads(rec["body"]))
