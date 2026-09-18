"""Ambiente das suítes de integração do CRM.

O banco é recriado do schema uma vez e LIMPO entre os testes. Limpar, e não recriar, porque
`TRUNCATE` de quinze tabelas leva milissegundos e recriar o schema leva segundos — e uma suíte lenta
é uma suíte que se deixa de rodar.

A trava de segurança: o DSN precisa ter "test" no nome do banco. Uma suíte que apaga tabelas
apontada por engano para o banco de desenvolvimento é um acidente que só acontece uma vez.
"""
import os
import uuid
from pathlib import Path

import pytest

DSN = os.environ.get("CRM_TEST_DSN", "postgresql://sdr:sdr@127.0.0.1:5432/crm_test")
if "test" not in DSN.rsplit("/", 1)[-1]:
    raise RuntimeError(f"Recuso rodar: {DSN!r} não parece um banco de teste.")
os.environ["CRM_DATABASE_DSN"] = DSN
os.environ["CRM_APP_ENV"] = "test"

from fastapi.testclient import TestClient  # noqa: E402  (precisa do env acima já configurado)

from sdr_crm.api import auth as autenticacao  # noqa: E402
from sdr_crm.api.contexto import limpar_limites  # noqa: E402
from sdr_crm.api.main import app  # noqa: E402
from sdr_crm.db.connection import get_pool, transacao  # noqa: E402

SCHEMA = Path(__file__).resolve().parents[1] / "sdr_crm" / "db" / "schema.sql"
TABELAS = ("idempotency_records", "audit_events", "handoffs", "tasks", "visits",
           "availability_slots", "property_interests", "interactions", "preferences",
           "opportunities", "leads", "properties", "sessions", "service_credentials", "users")


@pytest.fixture(scope="session", autouse=True)
def schema():
    with get_pool().connection() as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
        conn.commit()


@pytest.fixture(autouse=True)
def limpo(schema):
    with transacao() as conn:
        conn.execute(f"TRUNCATE {', '.join(TABELAS)} RESTART IDENTITY CASCADE")
    limpar_limites()          # senão um teste de limite envenena os seguintes
    yield


@pytest.fixture
def cliente():
    # raise_server_exceptions=False para que um 500 inesperado apareça como 500 no teste, com o
    # corpo que o cliente real veria, em vez de estourar a exceção dentro do próprio pytest.
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _usuario(nome: str, papel: str, senha: str = "Senha-de-teste-123") -> str:
    with transacao() as conn:
        linha = conn.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s) RETURNING id",
            (nome, f"{uuid.uuid4().hex[:8]}@example.com", autenticacao.hash_senha(senha),
             papel)).fetchone()
    return str(linha["id"])


@pytest.fixture
def admin_id():
    return _usuario("Admin de Teste", "admin")


@pytest.fixture
def corretor_id():
    return _usuario("Corretor de Teste", "broker")


def _credencial(scopes: list[str]) -> str:
    token, hash_ = autenticacao.novo_token("crmtest")
    with transacao() as conn:
        conn.execute("INSERT INTO service_credentials (name, token_hash, scopes) VALUES (%s,%s,%s)",
                     ("agente-de-teste", hash_, scopes))
    return token


@pytest.fixture
def token_agente():
    """Os scopes que o agente SDR recebe na especificação — nem um a mais."""
    return _credencial(["crm:read", "leads:write", "opportunities:write", "interactions:write",
                        "visits:request", "tasks:write", "handoffs:write"])


@pytest.fixture
def agente(cliente, token_agente):
    """Cliente HTTP já autenticado como o agente, com Idempotency-Key automática.

    A chave é gerada por chamada aqui porque o objetivo destes testes é a regra de negócio; os
    testes de idempotência mandam a chave explicitamente, que é onde ela é o assunto.
    """
    class Agente:
        def __init__(self):
            self.token = token_agente

        def _cabecalhos(self, extra: dict | None) -> dict:
            base = {"Authorization": f"Bearer {token_agente}",
                    "Idempotency-Key": f"auto-{uuid.uuid4()}"}
            base.update(extra or {})
            return base

        def get(self, url, **kw):
            return cliente.get(url, headers=self._cabecalhos(kw.pop("headers", None)), **kw)

        def post(self, url, json=None, headers=None, **kw):
            return cliente.post(url, json=json, headers=self._cabecalhos(headers), **kw)

        def put(self, url, json=None, headers=None, **kw):
            return cliente.put(url, json=json, headers=self._cabecalhos(headers), **kw)

        def patch(self, url, json=None, headers=None, **kw):
            return cliente.patch(url, json=json, headers=self._cabecalhos(headers), **kw)

    return Agente()


@pytest.fixture
def humano(cliente, admin_id):
    """Cliente autenticado como administrador, via sessão — o caminho do painel."""
    token, hash_ = autenticacao.novo_token("sess")
    with transacao() as conn:
        conn.execute("INSERT INTO sessions (user_id, token_hash, expires_at) "
                     "VALUES (%s, %s, now() + interval '1 hour')", (admin_id, hash_))
    cliente.cookies.set("crm_session", token)

    class Humano:
        id = admin_id

        def _h(self, extra):
            base = {"Idempotency-Key": f"auto-{uuid.uuid4()}"}
            base.update(extra or {})
            return base

        def get(self, url, **kw):
            return cliente.get(url, **kw)

        def post(self, url, json=None, headers=None, **kw):
            return cliente.post(url, json=json, headers=self._h(headers), **kw)

        def patch(self, url, json=None, headers=None, **kw):
            return cliente.patch(url, json=json, headers=self._h(headers), **kw)

        def put(self, url, json=None, headers=None, **kw):
            return cliente.put(url, json=json, headers=self._h(headers), **kw)

    return Humano()
