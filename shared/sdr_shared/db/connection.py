import atexit
from functools import lru_cache
from typing import cast

from psycopg import Connection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool
from ..config import get_settings

# O pool entrega conexões com `dict_row` (ver `kwargs` abaixo), mas o tipo padrão da biblioteca é
# tupla — e todo `linha["coluna"]` do repositório apareceria para o pyright como erro. O alias diz a
# verdade sobre o que sai daqui.
PoolDeDicionarios = ConnectionPool[Connection[DictRow]]


@lru_cache
def get_pool() -> PoolDeDicionarios:
    # `max_size` por processo e configurável: 4 servia ao worker (um turno por vez), mas a API
    # atende painel, site e canal ao mesmo tempo — com 4, a quinta requisição esperava conexão.
    # Cada processo tem o seu pool; a soma é o que conta contra o `max_connections` do Postgres.
    pool = ConnectionPool(get_settings().database_dsn, min_size=1, max_size=get_settings().db_pool_max, open=True,
                          kwargs={"row_factory": dict_row, "autocommit": True})
    # Fechar na saída, com o interpretador ainda inteiro. Sem isto o pool morria no coletor de lixo
    # do encerramento, e o `__del__` dele tenta esperar as threads de manutenção — o que o Python
    # 3.14 passou a recusar ("PythonFinalizationError: cannot join thread at interpreter shutdown").
    # Não quebrava nada, mas sujava o fim de toda suíte e de todo worker com um traceback.
    atexit.register(_fechar, pool)
    return cast(PoolDeDicionarios, pool)


def _fechar(pool: ConnectionPool) -> None:
    try:
        pool.close(timeout=2)
    except Exception:
        pass                    # saindo do processo: nada a fazer com a falha além de não fazer barulho
