from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    env: str = "dev"
    # `local` (padrão) | `producao`. Não decide adaptador — cada porta tem uma implementação só.
    # Decide UMA coisa, e é de segurança: se o token estático de desenvolvimento vale. Ver
    # `seguranca/painel.py` e `services/api/src/api/auth.py`.
    profile: str = "local"

    # Provedores de LLM
    llm_provider: str = "anthropic"         # anthropic | openai | ollama
    # Provedor de reserva: assumido quando o primário falha (indisponibilidade, timeout, cota).
    # Vazio = sem fallback. O ID do modelo é traduzido sozinho entre provedores (normalizar_modelo).
    llm_provider_fallback: str | None = None
    # Só para a bancada do harness comparar modelos (ADR-0009). NÃO usar no caminho de produção:
    # põe um terceiro no meio das conversas com PII de cliente. Exige `pip install langchain-openai`.
    openrouter_api_key: str | None = None
    embeddings_provider: str = "ollama"     # ollama (único; o bge-m3 dá as 1024 dimensões do schema)
    # Chave de organização (não escopada a um workspace) exige este header em toda requisição.
    anthropic_workspace_id: str | None = None
    ollama_url: str = "http://localhost:11434"
    llm_timeout_s: float = 45.0             # acima disso o turno falha e o cliente recebe o fallback
    # Fotos enviadas pelo painel: gravadas em disco.
    fotos_dir: str = str(Path(__file__).resolve().parents[3] / "data" / "fotos")
    public_api_url: str = "http://localhost:8000"     # base para montar URLs absolutas de fotos fora da API (cards do agente)
    ollama_embedding_model: str = "bge-m3"
    redis_url: str = "redis://localhost:6379/0"

    # Transcrição de áudio (mensagens de voz do Telegram → texto).
    # auto: usa o whisper local. `off` não transcreve (o cliente recebe o pedido para escrever).
    transcricao_provider: str = "auto"      # auto | whisper_local | off
    # Tamanho do modelo faster-whisper (tiny|base|small|medium|large-v3).
    # small equilibra qualidade e custo de CPU/RAM para pt-BR; ajuste conforme a máquina.
    whisper_model: str = "small"

    # Dados
    database_dsn: str = "postgresql://sdr:sdr@localhost:5432/sdr"

    # Modelos. IDs da API direta da Anthropic; `normalizar_modelo` ainda limpa prefixos de
    # provedores hospedados que possam vir de um .env antigo.
    model_conversa: str = "claude-sonnet-4-5"
    model_roteamento: str = "claude-haiku-4-5"

    # Telegram — o canal externo ativo.
    # Token vem do @BotFather; não precisa de app review nem verificação de negócio.
    telegram_bot_token: str | None = None
    telegram_bot_username: str | None = None   # só para montar o link t.me/<usuario> no site
    # Assina a sessão do chat do site. Sem valor definido, cada processo gera o seu no boot
    # (sessões caem a cada reinício — visível — em vez de aceitar qualquer assinatura).
    sessao_secret: str | None = None
    # Credencial do painel para portas sem o authorizer do API Gateway na frente (hoje o WebSocket
    # do perfil local). Vazio + perfil local = "dev-token"; vazio fora dele = ninguém entra.
    painel_token: str | None = None
    # Google Calendar do corretor: sem estas duas, o sistema usa a agenda do próprio banco
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8000/calendario/callback"
    cors_origins: str | None = None      # lista separada por vírgula; vazio = '*' (só para dev)

    model_config = {"env_prefix": "SDR_", "env_file": ".env"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
