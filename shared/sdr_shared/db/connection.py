from functools import lru_cache
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from ..config import get_settings


@lru_cache
def get_pool() -> ConnectionPool:
    # `max_size` por processo e configurável: 4 servia ao worker (um turno por vez), mas a API
    # atende painel, site e canal ao mesmo tempo — com 4, a quinta requisição esperava conexão.
    # Cada processo tem o seu pool; a soma é o que conta contra o `max_connections` do Postgres.
    return ConnectionPool(get_settings().database_dsn, min_size=1, max_size=get_settings().db_pool_max, open=True,
                          kwargs={"row_factory": dict_row, "autocommit": True})
