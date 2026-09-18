"""Emite credenciais de serviço do CRM — só por linha de comando.

Não existe rota REST nem ferramenta MCP para isto, de propósito (seção 8): um sistema onde o agente
consegue emitir a própria credencial não tem credencial, tem decoração.

O token em claro aparece **uma única vez**, nesta saída. O banco guarda só o hash — se perder,
emita outro e revogue o antigo; não há como recuperá-lo.

    python -m sdr_crm.credenciais emitir --nome mora
    python -m sdr_crm.credenciais listar
    python -m sdr_crm.credenciais revogar --id <uuid>
"""
import argparse
import sys

from .api.auth import SCOPES, novo_token
from .db.connection import leitura, transacao

# O que o agente SDR recebe por padrão: tudo que a seção 4 lista para o perfil dele, e nada além.
# `admin` não está aqui e não pode ser concedido por esta CLI — auditoria e gestão de credencial
# são do administrador humano.
PADRAO = ["crm:read", "leads:write", "opportunities:write", "interactions:write",
          "visits:request", "tasks:write", "handoffs:write"]


def emitir(nome: str, scopes: list[str], dias: int | None) -> int:
    invalidos = sorted(set(scopes) - SCOPES)
    if invalidos:
        print(f"✗ scope inexistente: {', '.join(invalidos)}", file=sys.stderr)
        return 1
    token, hash_ = novo_token("crm")
    with transacao() as conn:
        linha = conn.execute(
            """INSERT INTO service_credentials (name, token_hash, scopes, expires_at)
               VALUES (%s, %s, %s, CASE WHEN %s::int IS NULL THEN NULL
                                        ELSE now() + (%s || ' days')::interval END)
               RETURNING id""", (nome, hash_, scopes, dias, dias)).fetchone()
    print(f"id:     {linha['id']}")
    print(f"scopes: {' '.join(scopes)}")
    print(f"token:  {token}")
    print("\nGuarde agora — o banco só tem o hash e este valor não é recuperável.")
    return 0


def listar() -> int:
    with leitura() as conn:
        linhas = conn.execute(
            "SELECT id, name, scopes, expires_at, revoked_at, created_at "
            "FROM service_credentials ORDER BY created_at DESC").fetchall()
    if not linhas:
        print("(nenhuma credencial emitida)")
    for x in linhas:
        estado = "revogada" if x["revoked_at"] else "ativa"
        print(f"{x['id']}  {estado:9} {x['name']:20} {' '.join(x['scopes'])}")
    return 0


def revogar(ident: str) -> int:
    with transacao() as conn:
        linha = conn.execute(
            "UPDATE service_credentials SET revoked_at = now() "
            "WHERE id = %s AND revoked_at IS NULL RETURNING name", (ident,)).fetchone()
    if linha is None:
        print("✗ credencial não encontrada ou já revogada", file=sys.stderr)
        return 1
    print(f"✓ credencial de {linha['name']} revogada — a próxima chamada dela é recusada.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sdr_crm.credenciais")
    sub = p.add_subparsers(dest="comando", required=True)

    e = sub.add_parser("emitir")
    e.add_argument("--nome", required=True)
    e.add_argument("--scopes", nargs="*", default=PADRAO)
    e.add_argument("--dias", type=int, default=None, help="validade; sem isto, não expira")

    sub.add_parser("listar")
    r = sub.add_parser("revogar")
    r.add_argument("--id", required=True)

    a = p.parse_args(argv)
    if a.comando == "emitir":
        return emitir(a.nome, list(a.scopes), a.dias)
    if a.comando == "listar":
        return listar()
    return revogar(a.id)


if __name__ == "__main__":
    sys.exit(main())
