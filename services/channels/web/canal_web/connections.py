"""Tabela DynamoDB `sdr-ws-connections`: connection_id ⇄ (session_id | dashboard). Único uso de Dynamo (ADR-0004).
Clientes criados sob demanda: import não deve exigir credencial nem variável de ambiente."""
import os
from functools import lru_cache


@lru_cache
def _tabela():
    import boto3
    return boto3.resource("dynamodb").Table(os.environ.get("WS_TABLE", "sdr-ws-connections"))


def registrar(connection_id: str, papel: str, identificador: str) -> None:
    _tabela().put_item(Item={"connection_id": connection_id, "papel": papel, "identificador": identificador})


def remover(connection_id: str) -> None:
    _tabela().delete_item(Key={"connection_id": connection_id})


def conexoes(papel: str, identificador: str | None = None) -> list[str]:
    from boto3.dynamodb.conditions import Attr
    f = Attr("papel").eq(papel)
    if identificador:
        f = f & Attr("identificador").eq(identificador)
    return [i["connection_id"] for i in _tabela().scan(FilterExpression=f)["Items"]]
