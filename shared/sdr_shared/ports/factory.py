"""Único lugar que conhece o perfil. `SDR_PROFILE=aws` (padrão) ou `local`."""
import logging
from functools import lru_cache
from ..config import get_settings

log = logging.getLogger("ports")


@lru_cache
def get_broker():
    if get_settings().profile == "local":
        from ..adapters.local.broker import RedisBroker
        return RedisBroker()
    from ..adapters.aws.broker import SqsBroker
    return SqsBroker()


@lru_cache
def get_scheduler():
    if get_settings().profile == "local":
        from ..adapters.local.scheduler import PostgresScheduler
        return PostgresScheduler()
    from ..adapters.aws.scheduler import EventBridgeScheduler
    return EventBridgeScheduler()


@lru_cache
def get_calendario():
    """Google quando há credencial de aplicativo configurada; senão, a agenda do próprio banco.
    A escolha é por aplicativo; se um corretor não conectou a agenda dele, o adaptador do Google
    devolve a ocupação interna do mesmo jeito."""
    s = get_settings()
    if s.google_client_id and s.google_client_secret:
        from ..adapters.google.calendario import CalendarioGoogle
        return CalendarioGoogle()
    from ..adapters.local.calendario import CalendarioLocal
    return CalendarioLocal()


@lru_cache
def get_crm():
    """O CRM entra quando está configurado, e o padrão é não ter.

    A escolha não é por `SDR_PROFILE`, como as outras portas, e sim por configuração presente: o
    perfil diz onde a Mora roda, não se a imobiliária tem CRM. Rodar local com CRM e rodar local
    sem CRM são os dois casos normais.
    """
    from ..adapters.crm.via_mcp import CRMviaMCP
    adaptador = CRMviaMCP()
    if adaptador.habilitado():
        return adaptador
    from ..adapters.crm.ausente import CRMAusente
    return CRMAusente()


@lru_cache
def get_embedder():
    s = get_settings()
    if s.embeddings_provider == "ollama":
        from ..adapters.local.embeddings import OllamaEmbedder
        return OllamaEmbedder(s.ollama_url, s.ollama_embedding_model)
    from ..adapters.aws.embeddings import BedrockEmbedder
    return BedrockEmbedder()


_PREFIXOS_BEDROCK = ("anthropic.", "us.", "eu.", "apac.")

# Famílias de modelo por provedor. Anthropic e Bedrock servem o MESMO modelo com prefixo diferente —
# `normalizar_modelo` dá conta. OpenAI é outra família: não existe `claude-sonnet-4-5` lá.
_FAMILIA = {
    "openai": ("gpt-", "o1", "o3", "o4"),
    "anthropic": ("claude",),
    "bedrock": ("claude", "anthropic.", "us.", "eu.", "apac.", "amazon.", "meta.", "mistral."),
}

# Equivalente por PAPEL quando o modelo configurado não existe no provedor — o caso do fallback
# entre famílias. Sem esta tabela, cair da Anthropic para a OpenAI mandaria "claude-sonnet-4-5" para
# a OpenAI e voltaria 404: o reserva falharia exatamente no momento em que ele existe para servir.
# Pareado por posição na escala, não por nome: conversa ↔ modelo bom, roteamento ↔ modelo barato.
_EQUIVALENTE = {
    "openai":    {"conversa": "gpt-5.6-terra", "analise": "gpt-5.6-terra", "roteamento": "gpt-5.6-luna"},
    "anthropic": {"conversa": "claude-sonnet-4-5", "analise": "claude-sonnet-4-5", "roteamento": "claude-haiku-4-5"},
    "bedrock":   {"conversa": "anthropic.claude-sonnet-4-5", "analise": "anthropic.claude-sonnet-4-5",
                  "roteamento": "anthropic.claude-haiku-4-5"},
}


def modelo_do_provedor(model: str, provider: str, papel: str = "conversa") -> str:
    """Devolve um ID que EXISTE no provedor pedido.

    Mesma família (Anthropic ↔ Bedrock): só ajusta o prefixo. Família diferente (qualquer coisa ↔
    OpenAI): troca pelo equivalente do papel, porque traduzir o nome não faria o modelo existir lá.
    """
    familia = _FAMILIA.get(provider)
    if familia and model and model.lower().startswith(familia):
        return normalizar_modelo(model, provider)
    equivalente = _EQUIVALENTE.get(provider, {}).get(papel)
    return equivalente or normalizar_modelo(model, provider)


def normalizar_modelo(model: str, provider: str) -> str:
    """O MESMO modelo tem IDs diferentes por provedor: no Bedrock é `anthropic.claude-sonnet-4-5`,
    na API da Anthropic é `claude-sonnet-4-5`. Trocar de provedor no .env não deve exigir trocar o ID."""
    if provider == "anthropic":
        mudou = True
        while mudou:                      # `us.anthropic.claude-…` tem dois prefixos empilhados
            mudou = False
            for p in _PREFIXOS_BEDROCK:
                if model.startswith(p):
                    model, mudou = model[len(p):], True
        return model
    # Só modelo da Anthropic leva o prefixo `anthropic.`. O Bedrock serve outras famílias com
    # namespace próprio (`amazon.nova-…`, `meta.llama…`) e prefixar aquilo geraria um ID inexistente.
    if provider == "bedrock" and model.startswith("claude") and not model.startswith(_PREFIXOS_BEDROCK):
        return f"anthropic.{model}"
    return model


def modo_do_agente() -> str:
    """normal | degradado | bloqueado, conforme o orçamento de LLM (painel de Governança)."""
    try:
        from ..db.governanca import estado_do_orcamento
        return estado_do_orcamento()["modo"]
    except Exception:                       # sem banco/tabela (testes, boot): não atrapalha
        return "normal"


def _construir(provider: str, model: str, temp: float, papel: str):
    """Monta UM provedor. Separado de `get_chat_model` para o fallback montar o segundo pelo mesmo
    caminho — inclusive a tradução do ID do modelo, que é o pedaço chato de trocar de provedor e já
    estava resolvido aqui (ver `normalizar_modelo` e ADR-0009)."""
    s = get_settings()
    from ..governanca import callbacks_para
    cb = callbacks_para(papel, provider)
    if provider != "ollama":
        model = modelo_do_provedor(model, provider, papel)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        # Chave de organização precisa dizer em qual workspace cobrar; chave já escopada dispensa.
        headers = {"anthropic-workspace-id": s.anthropic_workspace_id} if s.anthropic_workspace_id else None
        # timeout/retries curtos: melhor falhar rápido e acionar o fallback do que pendurar o cliente
        return ChatAnthropic(model=model, temperature=temp, max_tokens=600, default_headers=headers, callbacks=cb,
                             timeout=s.llm_timeout_s, max_retries=2)
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model, base_url=s.ollama_url, temperature=temp, callbacks=cb, client_kwargs={"timeout": s.llm_timeout_s})
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        # Reserva de produção (ADR-0009): ao contrário do OpenRouter, é o próprio fornecedor do
        # modelo, sem intermediário no caminho do dado do cliente. Mesmos timeout e retries curtos
        # da Anthropic — a régua é a espera do cliente, não o provedor.
        # A chave sai de OPENAI_API_KEY no ambiente, como a da Anthropic sai de ANTHROPIC_API_KEY:
        # é o nome que a própria biblioteca procura. Passar `api_key=` explícito anularia esse
        # caminho para quem exporta a variável convencional.
        return ChatOpenAI(model=model, temperature=temp, max_tokens=600, callbacks=cb,
                          timeout=s.llm_timeout_s, max_retries=2)
    if provider == "openrouter":
        # Porta aberta para BANCADA, não para produção: o OpenRouter põe um terceiro no caminho de
        # dados de cliente (ver ADR-0009). Serve para o harness comparar modelos alternativos sobre
        # os datasets sintéticos de evals/. Dependência opcional, de propósito.
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, temperature=temp, max_tokens=600, callbacks=cb,
                          base_url="https://openrouter.ai/api/v1", api_key=s.openrouter_api_key,
                          timeout=s.llm_timeout_s, max_retries=2)
    from langchain_aws import ChatBedrockConverse
    gr = {"guardrailIdentifier": s.guardrail_id, "guardrailVersion": "DRAFT"} if s.guardrail_id else None
    from botocore.config import Config
    cfg = Config(read_timeout=s.llm_timeout_s, connect_timeout=10, retries={"max_attempts": 2})
    return ChatBedrockConverse(model=model, region_name=s.aws_region, temperature=temp, max_tokens=600,
                               guardrail_config=gr, callbacks=cb, config=cfg)


class ModeloComFallback:
    """Tenta o provedor primário; se ele falhar, repete no reserva.

    Só entra em ação quando o primário já esgotou os retries internos dele — ou seja, quando o
    provedor está de fato indisponível, não numa oscilação. Nesse ponto tentar o outro provedor é
    melhor que devolver a mensagem de desculpa ao cliente, que é o que acontecia antes.

    Não usamos `Runnable.with_fallbacks` porque ele devolve um Runnable sem `with_structured_output`,
    e a extração do cartão depende justamente disso (`qualificador._extrair`).
    """

    def __init__(self, primario, reserva, nome_reserva: str):
        self._primario, self._reserva, self._nome = primario, reserva, nome_reserva

    def invoke(self, *a, **kw):
        try:
            return self._primario.invoke(*a, **kw)
        except Exception as e:
            log.warning("provedor primário falhou (%s); assumindo o reserva (%s)", type(e).__name__, self._nome)
            return self._reserva.invoke(*a, **kw)

    def with_structured_output(self, schema, **kw):
        return ModeloComFallback(self._primario.with_structured_output(schema, **kw),
                                 self._reserva.with_structured_output(schema, **kw), self._nome)

    def __getattr__(self, nome):            # o que não for invoke/structured segue para o primário
        return getattr(self._primario, nome)


def _escolha_do_painel(papel: str) -> tuple[str | None, str | None]:
    """O painel manda; o .env é o piso. Vazio no painel = usa o ambiente (ver db/modelos.py)."""
    try:
        from ..db import escolha_de_modelo
        return escolha_de_modelo(papel)
    except Exception:                       # sem banco (testes, boot): o ambiente decide sozinho
        return None, None


def get_chat_model(papel: str = "conversa"):
    """papel: conversa | roteamento | analise. Provedor: bedrock | anthropic | openai | ollama.
    Modelo e provedor saem do painel quando configurados lá, senão do .env (ADR-0010).
    Toda chamada é registrada para governança; se o orçamento estourou, `conversa` cai para o barato.
    Com fallback definido, a queda de um provedor não vira turno perdido."""
    s = get_settings()
    if papel in ("conversa", "analise") and modo_do_agente() == "degradado":
        papel = "roteamento"                # degradação: Sonnet → Haiku até o orçamento virar o mês
    model_painel, provider_painel = _escolha_do_painel(papel)
    padrao_env = s.model_roteamento if papel == "roteamento" else s.model_conversa
    model = model_painel or padrao_env
    provider = provider_painel or s.llm_provider
    temp = 0.0 if papel == "roteamento" else 0.6
    primario = _construir(provider, model, temp, papel)
    reserva = (s.llm_provider_fallback or "").strip()
    if not reserva or reserva == provider:
        return primario
    return ModeloComFallback(primario, _construir(reserva, model, temp, papel), reserva)
