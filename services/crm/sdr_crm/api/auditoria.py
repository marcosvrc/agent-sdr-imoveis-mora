"""Registro de auditoria (seções 5 e 11).

Duas propriedades, e as duas são o ponto:

* **mesma transação da mutação** — auditoria gravada depois é auditoria que falta justamente quando
  o processo morre no meio, que é quando ela mais importa;
* **somente append** — não há UPDATE nem DELETE em `audit_events` em lugar nenhum do código.
  Auditoria corrigível não responde "quem mudou isto".

O diff é filtrado: token, hash de senha e o corpo inteiro de texto livre ficam de fora. Auditoria
existe para reconstruir *o que mudou*, não para virar uma segunda cópia do banco — e uma cópia que
ninguém lembra de proteger.
"""
import json
from typing import Any

OCULTOS = frozenset({"password", "password_hash", "token", "token_hash", "authorization",
                     "session", "secret"})
LIMITE_TEXTO = 500


def _limpar(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {k: ("[omitido]" if k.lower() in OCULTOS else _limpar(v)) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_limpar(v) for v in valor[:50]]
    if isinstance(valor, str) and len(valor) > LIMITE_TEXTO:
        return valor[:LIMITE_TEXTO] + "…[truncado]"
    return valor


def diferenca(antes: dict | None, depois: dict | None) -> dict:
    """Só os campos que mudaram. Guardar o registro inteiro a cada alteração faz a auditoria crescer
    sem limite e esconde a mudança no meio de trinta colunas iguais."""
    antes, depois = antes or {}, depois or {}
    mudou = {}
    for chave in set(antes) | set(depois):
        a, d = antes.get(chave), depois.get(chave)
        if a != d:
            mudou[chave] = {"de": _limpar(a), "para": _limpar(d)}
    return mudou


def registrar(conn, *, ator, action: str, entity_type: str, entity_id: str | None,
              request_id: str, changes: dict | None = None) -> None:
    conn.execute(
        """INSERT INTO audit_events
             (actor_type, actor_id, actor_name, action, entity_type, entity_id, request_id, changes_json)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (ator.tipo, ator.id, ator.nome, action, entity_type, entity_id, request_id,
         json.dumps(_limpar(changes or {}), default=str)))
