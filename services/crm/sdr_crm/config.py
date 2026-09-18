"""Configuração do CRM.

Deliberadamente separada da `sdr_shared.config` da Mora: são dois sistemas, com dois bancos e duas
credenciais. Importar a configuração da Mora aqui seria o primeiro passo para o CRM acabar lendo o
banco dela — exatamente o que a decisão de "fluxo num sentido só" existe para impedir.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CRM_", extra="ignore")

    app_env: str = "development"                 # development | test | production
    database_dsn: str = "postgresql://sdr:sdr@localhost:5432/crm"
    # Assina o cookie de sessão humana. Vazio fora de desenvolvimento é erro, não padrão silencioso:
    # sessão assinada com segredo previsível é sessão de qualquer um.
    session_secret: str = ""
    # Os dois, e não só um: para o navegador, `localhost:3000` e `127.0.0.1:3000` são origens
    # DIFERENTES. Com só um na lista, abrir o painel pelo outro endereço faz toda chamada falhar no
    # CORS — e o erro que chega ao JavaScript não diz "CORS", diz "failed to fetch". Descoberto
    # abrindo o painel de verdade.
    allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    # Limite por credencial, por minuto (seção 11). Contador em memória, de uma instância só — está
    # documentado como tal para ninguém confundir com proteção distribuída.
    rate_limit_por_minuto: int = 120
    rate_limit_burst: int = 20
    corpo_maximo_bytes: int = 256 * 1024
    idempotencia_horas: int = 24

    @property
    def sintetico(self) -> bool:
        """Só ambientes assumidamente de teste podem receber seed e reset."""
        return self.app_env in {"development", "test"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
