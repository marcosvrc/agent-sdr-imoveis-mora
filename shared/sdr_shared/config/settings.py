from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    env: str = "dev"
    profile: str = "aws"                    # aws | local  (decide broker, scheduler e hospedagem)
    aws_region: str = "us-east-1"

    # Provedores (independentes do perfil: dá para rodar local com Bedrock, ou AWS com Anthropic API)
    llm_provider: str = "bedrock"           # bedrock | anthropic | ollama
    # Provedor de reserva: assumido quando o primário falha (indisponibilidade, timeout, cota).
    # Vazio = sem fallback. O ID do modelo é traduzido sozinho entre provedores (normalizar_modelo).
    llm_provider_fallback: str | None = None
    # Só para a bancada do harness comparar modelos (ADR-0009). NÃO usar no caminho de produção:
    # põe um terceiro no meio das conversas com PII de cliente. Exige `pip install langchain-openai`.
    openrouter_api_key: str | None = None
    embeddings_provider: str = "bedrock"    # bedrock | ollama
    # Chave de organização (não escopada a um workspace) exige este header em toda requisição.
    anthropic_workspace_id: str | None = None
    ollama_url: str = "http://localhost:11434"
    llm_timeout_s: float = 45.0             # acima disso o turno falha e o cliente recebe o fallback
    # Fotos enviadas pelo painel (perfil local: disco; na AWS o equivalente é S3 + CloudFront)
    fotos_dir: str = str(Path(__file__).resolve().parents[3] / "data" / "fotos")
    public_api_url: str = "http://localhost:8000"     # base para montar URLs absolutas de fotos fora da API (cards do agente)
    ollama_embedding_model: str = "bge-m3"
    redis_url: str = "redis://localhost:6379/0"

    # Transcrição de áudio (mensagens de voz do Telegram/WhatsApp → texto).
    # auto: whisper_local no perfil local, transcribe no perfil aws. Outras opções forçam o motor.
    # off: não transcreve (o cliente recebe o pedido para escrever).
    transcricao_provider: str = "auto"      # auto | transcribe | whisper_local | off
    # Tamanho do modelo faster-whisper no perfil local (tiny|base|small|medium|large-v3).
    # small equilibra qualidade e custo de CPU/RAM para pt-BR; ajuste conforme a máquina.
    whisper_model: str = "small"

    # Dados
    database_dsn: str = "postgresql://sdr:sdr@localhost:5432/sdr"

    # Bedrock
    model_conversa: str = "anthropic.claude-sonnet-4-5"       # ajustar ao ID disponível na região
    model_roteamento: str = "anthropic.claude-haiku-4-5"
    model_embedding: str = "amazon.titan-embed-text-v2:0"
    knowledge_base_id: str | None = None                    # None => fallback pgvector direto (ADR-0001)
    guardrail_id: str | None = None
    audio_bucket: str | None = None

    # Mensageria (a URL da fila de entrada não aparece aqui: quem publica no inbound usa a porta
    # do broker, e o Lambda recebe por event source — ninguém precisa da URL em configuração)
    eventbus_name: str = "sdr-events"
    scheduler_group: str = "sdr-followup"

    # WhatsApp (Secrets Manager em prod; env em dev) — adapter mantido, não usado no perfil local (ADR-0007)
    whatsapp_phone_number_id: str | None = None
    whatsapp_token: str | None = None
    whatsapp_app_secret: str | None = None
    whatsapp_verify_token: str = "sdr-verify"
    # Telegram (Secrets Manager em prod; env em dev) — canal ativo no perfil local hoje.
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
