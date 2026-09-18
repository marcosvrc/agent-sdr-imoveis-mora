"""Pool de conexões do CRM.

`autocommit=False` — ao contrário do pool da Mora. Aqui quase toda mutação precisa gravar o registro
de idempotência e o evento de auditoria na MESMA transação do dado (seções 7 e 11), e autocommit
tornaria isso impossível de expressar: cada `execute` fecharia a transação sozinho.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from ..config import get_settings


@lru_cache
def get_pool() -> ConnectionPool:
    return ConnectionPool(get_settings().database_dsn, min_size=1, max_size=8, open=True,
                          kwargs={"row_factory": dict_row, "autocommit": False})


@contextmanager
def transacao() -> Iterator:
    """Uma transação por requisição de mutação: ou o dado, a auditoria e a idempotência entram
    juntos, ou não entra nada. Commit no fim do `with`, rollback em qualquer exceção."""
    with get_pool().connection() as conn:
        with conn.transaction():
            yield conn


@contextmanager
def leitura() -> Iterator:
    """Conexão para consulta. O rollback no fim evita deixar transação ociosa aberta segurando
    snapshot — que é como um pool pequeno trava sob carga."""
    with get_pool().connection() as conn:
        try:
            yield conn
        finally:
            conn.rollback()
