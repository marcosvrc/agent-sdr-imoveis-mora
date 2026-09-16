"""Trava contra apagar o banco de desenvolvimento: as suítes de teste limpam tabelas, então só podem
rodar contra um banco cujo nome contenha "test" (ex.: sdr_test). Para forçar, SDR_TEST_ALLOW_WIPE=1."""
import os
from urllib.parse import urlparse


def exigir_banco_de_teste() -> None:
    dsn = os.environ.get("SDR_DATABASE_DSN", "")
    nome = urlparse(dsn).path.lstrip("/") if dsn else ""
    if "test" in nome or os.environ.get("SDR_TEST_ALLOW_WIPE") == "1":
        return
    msg = (f"Os testes APAGAM tabelas, e SDR_DATABASE_DSN aponta para o banco '{nome or '?'}' (não é de teste). "
           "Use `make test` (cria e usa o banco sdr_test no compose) ou aponte SDR_DATABASE_DSN para um banco com 'test' no nome. "
           "Para ignorar a trava de propósito: SDR_TEST_ALLOW_WIPE=1.")
    try:
        import pytest
        pytest.exit(msg, returncode=2)
    except ImportError:
        raise SystemExit("✗ " + msg)
