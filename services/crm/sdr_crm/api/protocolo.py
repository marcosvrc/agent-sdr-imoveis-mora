"""Idempotência, controle de versão e paginação (seção 7).

São as três mecânicas que fazem a API aguentar um cliente automatizado. Um agente repete chamadas
por timeout, edita em paralelo com o corretor e pagina listas grandes — e nenhuma dessas três coisas
é exceção: é o funcionamento normal.
"""
import hashlib
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from typing import Any

from ..erros import ConflitoDeIdempotencia, ConflitoDeVersao, PrecondicaoAusente

# --------------------------------------------------------------------------- versão / ETag


def etag(versao: int) -> str:
    """ETag forte com a versão do agregado. Aspas fazem parte do valor pelo HTTP."""
    return f'"{versao}"'


def versao_do_if_match(cabecalho: str | None, *, obrigatorio: bool = True) -> int | None:
    """Traduz `If-Match` em número de versão.

    `*` é aceito como "qualquer versão serve" — é o que um cliente manda quando quer apenas garantir
    que o recurso existe. Ausente com `obrigatorio` é 428 (falta a precondição), não 412 (a
    precondição falhou): são respostas com ações diferentes do outro lado.
    """
    if cabecalho is None or cabecalho.strip() == "":
        if obrigatorio:
            raise PrecondicaoAusente("Esta operação exige o cabeçalho If-Match com a versão atual "
                                     "(leia o recurso e use o ETag devolvido).")
        return None
    valor = cabecalho.strip()
    if valor == "*":
        return None
    valor = valor.removeprefix("W/").strip('"')
    try:
        return int(valor)
    except ValueError:
        raise ConflitoDeVersao(f"If-Match '{cabecalho}' não é uma versão válida.")


def conferir_versao(atual: int, esperada: int | None) -> None:
    if esperada is not None and atual != esperada:
        raise ConflitoDeVersao("A versão enviada não é mais a atual — alguém alterou este registro.",
                               current_version=atual, expected_version=esperada)


# --------------------------------------------------------------------------- idempotência


def hash_corpo(corpo: Any) -> str:
    """Hash canônico: chaves ordenadas e sem espaço. Sem isso, o mesmo JSON com os campos em outra
    ordem seria lido como corpo diferente e devolveria 409 para um cliente que não errou nada."""
    return hashlib.sha256(
        json.dumps(corpo, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def buscar_replay(conn, credencial_id: str | None, chave: str, corpo_hash: str,
                  method: str, route: str) -> tuple[int, dict] | None:
    """Procura o resultado guardado desta chave. Devolve (status, corpo) quando é repetição.

    O `SELECT ... FOR UPDATE` serializa chamadas simultâneas com a mesma chave (seção 7): a segunda
    espera a primeira terminar em vez de executar a mutação em paralelo. É o que transforma
    "o cliente clicou duas vezes" em uma linha só no banco.
    """
    linha = conn.execute(
        """SELECT * FROM idempotency_records
            WHERE coalesce(credential_id, '00000000-0000-0000-0000-000000000000'::uuid)
                  = coalesce(%s::uuid, '00000000-0000-0000-0000-000000000000'::uuid)
              AND key = %s
            FOR UPDATE""",
        (credencial_id, chave)).fetchone()
    if linha is None:
        return None
    if linha["expires_at"] <= datetime.now(UTC):
        # Expirou: a chave pode ser reusada. As restrições de negócio (e-mail único, slot único)
        # continuam impedindo duplicata de verdade — a janela de idempotência protege o replay
        # rápido, não a integridade.
        conn.execute("DELETE FROM idempotency_records WHERE id = %s", (linha["id"],))
        return None
    if linha["body_hash"] != corpo_hash:
        raise ConflitoDeIdempotencia(
            "Esta Idempotency-Key já foi usada com outro corpo.",
            key=chave, original_route=linha["route"])
    if linha["method"] != method or linha["route"] != route:
        raise ConflitoDeIdempotencia("Esta Idempotency-Key já foi usada em outra rota.",
                                     key=chave, original_route=linha["route"])
    return linha["response_status"], linha["response_body"]


def gravar_replay(conn, credencial_id: str | None, chave: str, corpo_hash: str,
                  method: str, route: str, status: int, corpo: dict, horas: int) -> None:
    """Grava NA MESMA transação da mutação. Gravar depois abriria a janela em que a operação já
    aconteceu e o registro ainda não existe — exatamente quando o cliente repete por timeout."""
    conn.execute(
        """INSERT INTO idempotency_records
             (credential_id, key, method, route, body_hash, response_status, response_body, expires_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (credencial_id, chave, method, route, corpo_hash, status, json.dumps(corpo, default=str),
         datetime.now(UTC) + timedelta(hours=horas)))


# --------------------------------------------------------------------------- paginação


def cifrar_cursor(created_at: datetime, ident: str) -> str:
    """Cursor opaco sobre (created_at, id).

    Opaco porque é contrato interno: publicar o offset convidaria o cliente a fabricar um. E o par
    com o id desempata registros criados no mesmo microssegundo — sem ele, o seed (que insere tudo
    numa transação) faria a paginação pular ou repetir linhas.
    """
    bruto = json.dumps([created_at.isoformat(), str(ident)])
    return urlsafe_b64encode(bruto.encode()).decode().rstrip("=")


def decifrar_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    try:
        preenchido = cursor + "=" * (-len(cursor) % 4)
        quando, ident = json.loads(urlsafe_b64decode(preenchido.encode()).decode())
        return datetime.fromisoformat(quando), ident
    except Exception:
        # Cursor inválido é tratado como "do começo": o cliente que colou algo errado recebe a
        # primeira página em vez de um 500 sem explicação.
        return None


def limite(valor: int | None, padrao: int = 20, maximo: int = 100) -> int:
    return max(1, min(valor or padrao, maximo))
