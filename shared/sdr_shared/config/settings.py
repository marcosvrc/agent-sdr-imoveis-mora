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
    llm_provider: str = "anthropic"         # anthropic | openai | ollama | openrouter
    # Provedor de reserva: assumido quando o primário falha (indisponibilidade, timeout, cota).
    # Vazio = sem fallback. O ID do modelo é traduzido sozinho entre provedores (normalizar_modelo).
    llm_provider_fallback: str | None = None
    # OpenRouter (ADR-0016): um intermediário que dá acesso a centenas de modelos com uma chave só.
    # É um operador a mais no caminho do texto do cliente, e por isso a retenção zero é LIGADA por
    # padrão: com ela o OpenRouter só roteia para endpoints que não guardam o dado. Desligar é para
    # a bancada de avaliação, com dataset sintético — nunca com conversa de cliente de verdade.
    # Exige `langchain-openai` (o extra `openai` do sdr-shared).
    openrouter_api_key: str | None = None
    openrouter_zdr: bool = True
    openrouter_url: str = "https://openrouter.ai/api/v1"
    # ollama | openai | openrouter. O padrão fica no ollama porque é o único que roda sem chave nenhuma —
    # importa para os testes e para quem clona o projeto sem conta em lugar algum. O `.env.example`
    # sugere `openai`, que é mais leve (tira um container do compose). Os dois entregam as 1024
    # dimensões que o schema exige; trocar exige reindexar tudo (ver adapters/hospedados).
    embeddings_provider: str = "ollama"
    # Usado quando o provedor é `openai` ou `openrouter`. Pelo OpenRouter, sem fornecedor no ID vira
    # `openai/<modelo>` — o MESMO modelo, então os vetores já indexados continuam valendo.
    embeddings_model: str = "text-embedding-3-small"
    embeddings_dimensoes: int = 1024                   # tem de casar com o vector(N) do schema.sql
    # Chave de organização (não escopada a um workspace) exige este header em toda requisição.
    anthropic_workspace_id: str | None = None
    ollama_url: str = "http://localhost:11434"
    # Marca pontos de cache no prefixo do prompt (só Anthropic; ver ports/factory.py).
    # Ligado é seguro: abaixo do mínimo do provedor a marcação é ignorada, sem erro.
    prompt_cache: bool = True
    llm_timeout_s: float = 45.0             # acima disso o turno falha e o cliente recebe o fallback
    # Fotos enviadas pelo painel: gravadas em disco.
    fotos_dir: str = str(Path(__file__).resolve().parents[3] / "data" / "fotos")
    # Fotos do acervo de demonstração, servidas em /acervo/ — prefixo separado de propósito, porque
    # `/fotos/%` é o que marca "foto do painel" na precedência do upsert (ADR-0015).
    fotos_acervo_dir: str = str(Path(__file__).resolve().parents[3] / "data" / "fotos-acervo")
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
    db_pool_max: int = 4                    # por processo; a API sobe para 12 no compose

    # Modelos. IDs da API direta da Anthropic; `normalizar_modelo` ainda limpa prefixos de
    # provedores hospedados que possam vir de um .env antigo.
    model_conversa: str = "claude-sonnet-4-5"
    model_roteamento: str = "claude-haiku-4-5"
    # Papéis que herdam (ver sdr_shared.papeis): vazio = usa o do papel pai. Existem no ambiente
    # para a bancada poder fixar um modelo por papel sem banco; em operação, o painel é o caminho.
    model_extracao: str | None = None       # vazio → model_roteamento
    model_informacoes: str | None = None    # vazio → model_conversa
    model_analise: str | None = None        # vazio → model_conversa

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
