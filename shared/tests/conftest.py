"""Infraestrutura compartilhada dos testes que falam com o CRM.

Estas fixtures sobem processos de verdade — a API do CRM e o servidor MCP — porque é o que faz
estes testes valerem: erro de nome de argumento, de formato de resposta e de autenticação só
aparece contra o serviço real. Ficam aqui, e não num arquivo de teste, para que cada novo teste da
integração não remonte a mesma cena.
"""
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest

RAIZ = Path(__file__).resolve().parents[2]
CRM = RAIZ / "services" / "crm"

DSN_MORA = os.environ.get("SDR_DATABASE_DSN", "")
DSN_CRM = os.environ.get("CRM_TEST_DSN", "postgresql://sdr:sdr@127.0.0.1:5432/crm_test")

pytestmark = pytest.mark.skipif(
    not DSN_MORA or "test" not in DSN_MORA.rsplit("/", 1)[-1],
    reason="exige SDR_DATABASE_DSN apontando para um banco de teste")


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def crm_api():
    """A API do CRM, de verdade, num processo separado."""
    porta = _porta_livre()
    env = {**os.environ, "CRM_DATABASE_DSN": DSN_CRM, "CRM_APP_ENV": "test",
           "PYTHONPATH": str(CRM)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "sdr_crm.api.main:app", "--port", str(porta),
         "--host", "127.0.0.1", "--log-level", "warning"],
        cwd=CRM, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{porta}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/health/ready", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.15)
    else:
        proc.kill()
        pytest.skip("a API do CRM não subiu")
    yield base
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture
def token_crm():
    sys.path.insert(0, str(CRM))
    import psycopg
    from sdr_crm.api import auth as autenticacao
    bruto, hash_ = autenticacao.novo_token("mora")
    with psycopg.connect(DSN_CRM, autocommit=True) as conn:
        conn.execute("INSERT INTO service_credentials (name, token_hash, scopes) VALUES (%s,%s,%s)",
                     ("mora", hash_,
                      ["crm:read", "leads:write", "opportunities:write", "interactions:write",
                       "visits:request", "tasks:write", "handoffs:write"]))
    return bruto


@pytest.fixture
def porta_livre():
    """Uma porta que ninguém escuta — para provar o caminho de 'CRM fora do ar'."""
    return _porta_livre


@pytest.fixture(autouse=True)
def _porta_limpa():
    """`get_crm` é memoizada, e a configuração vem do ambiente, que estes testes trocam.

    Sem limpar, o primeiro teste a rodar congelaria o adaptador para todos os outros e o resultado
    passaria a depender da ORDEM — o teste de "sem CRM" passando só porque veio antes. Limpar dos
    dois lados de cada teste tira a ordem da equação.
    """
    from sdr_shared.ports import get_crm
    get_crm.cache_clear()
    yield
    get_crm.cache_clear()


@pytest.fixture
def crm_mcp(crm_api, token_crm):
    """O servidor MCP do CRM, de verdade, falando HTTP.

    Com ele no meio, o teste deixa de exercitar "a Mora chama REST" e passa a exercitar a cadeia
    inteira: porta → cliente MCP → HTTP → servidor MCP → REST do CRM → Postgres. É onde erro de
    nome de argumento e de formato de resposta aparece — nenhum dublê pega isso.
    """
    porta = _porta_livre()
    segredo = uuid.uuid4().hex
    env = {**os.environ, "CRM_API_BASE_URL": crm_api, "CRM_API_TOKEN": token_crm,
           "CRM_MCP_TOKEN": segredo, "PYTHONPATH": str(CRM)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "sdr_crm.mcp", "--http", "--porta", str(porta)],
        cwd=CRM, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{porta}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/saude", timeout=0.5).status_code == 200:
                break
        except Exception:
            time.sleep(0.1)
    else:
        proc.terminate()
        pytest.skip("servidor MCP do CRM não subiu")
    yield f"{base}/mcp", segredo
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture
def ligado(crm_mcp, monkeypatch):
    url, segredo = crm_mcp
    monkeypatch.setenv("SDR_CRM_URL", url)
    monkeypatch.setenv("SDR_CRM_TOKEN", segredo)
    return url
