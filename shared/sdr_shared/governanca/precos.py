"""Tabela de preços dos modelos (USD por 1 milhão de tokens) e cálculo de custo.

Fonte: documentação de preços da Anthropic (platform.claude.com/docs/en/about-claude/pricing).
Preços mudam: a tabela é o padrão do código e pode ser sobrescrita pelo painel (configuração `precos`).
O Bedrock cobra valores próprios por região — ajuste pelo painel se usar `SDR_LLM_PROVIDER=bedrock`.
"""
import re

# modelo -> (entrada, saída, escrita de cache 5min, leitura de cache) em USD por 1M tokens
# Escrita de cache = 1,25x a entrada; leitura de cache = 0,1x a entrada (multiplicadores da Anthropic).
PRECOS_PADRAO: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-5":     (5.0, 25.0, 6.25, 0.50),
    "claude-opus-4-1":   (15.0, 75.0, 18.75, 1.50),
    "claude-opus-4":     (15.0, 75.0, 18.75, 1.50),
    "claude-sonnet-5":   (2.0, 10.0, 2.50, 0.20),
    "claude-sonnet-4-6": (3.0, 15.0, 3.75, 0.30),
    "claude-sonnet-4-5": (3.0, 15.0, 3.75, 0.30),
    "claude-sonnet-4":   (3.0, 15.0, 3.75, 0.30),
    "claude-haiku-4-5":  (1.0, 5.0, 1.25, 0.10),
    "claude-haiku-3-5":  (0.80, 4.0, 1.0, 0.08),
    # Amazon Nova (Bedrock): alternativa barata para roteamento/extração sem sair da AWS (ADR-0010).
    # Valores de cache aproximados — o Bedrock cobra por região; confirme e ajuste pelo painel.
    "amazon.nova-premier-v1:0": (2.50, 12.50, 3.125, 0.25),
    "amazon.nova-pro-v1:0":     (0.80, 3.20, 1.0, 0.08),
    "amazon.nova-lite-v1:0":    (0.06, 0.24, 0.075, 0.006),
    "amazon.nova-micro-v1:0":   (0.035, 0.14, 0.044, 0.0035),
    # OpenAI (provedor de reserva — ADR-0009). A OpenAI não cobra ESCRITA de cache, só desconta a
    # leitura: por isso o terceiro valor é zero e o quarto é o preço de "cached input".
    # Fonte: developers.openai.com/api/docs/pricing (consultado em 2026-09). Confira antes de confiar
    # no número do painel — preço de modelo muda mais rápido que código.
    "gpt-6-astra":   (10.0, 50.0, 0.0, 1.00),
    "gpt-5.6-sol":   (4.0, 20.0, 0.0, 0.40),
    "gpt-5.6-terra": (2.0, 12.0, 0.0, 0.20),
    "gpt-5.6-luna":  (0.20, 1.20, 0.0, 0.02),
    "gpt-5-mini":    (0.25, 2.0, 0.0, 0.025),
    "gpt-5-nano":    (0.05, 0.40, 0.0, 0.005),
    # Embeddings (Bedrock Titan v2: só entrada). Ollama roda local: custo zero.
    "amazon.titan-embed-text-v2:0": (0.02, 0.0, 0.0, 0.0),
    "bge-m3": (0.0, 0.0, 0.0, 0.0),
    "llama3.1:8b": (0.0, 0.0, 0.0, 0.0),
}

_PREFIXOS = ("us.", "eu.", "apac.", "anthropic.")
_SUFIXO_DATA = re.compile(r"-\d{8}$|-v\d+:\d+$")


def normalizar(modelo: str) -> str:
    """`us.anthropic.claude-sonnet-4-5-20250929-v1:0` e `claude-sonnet-4-5` viram a mesma chave."""
    m = (modelo or "").strip()
    if m.startswith("amazon.") or (":" in m and m.startswith("bge")):
        return m
    mudou = True
    while mudou:
        mudou = False
        for p in _PREFIXOS:
            if m.startswith(p):
                m, mudou = m[len(p):], True
    m = _SUFIXO_DATA.sub("", m)
    return m


def preco_do_modelo(modelo: str, tabela: dict | None = None) -> tuple[float, float, float, float] | None:
    t = {**PRECOS_PADRAO, **(tabela or {})}
    chave = normalizar(modelo)
    if chave in t:
        v = t[chave]
        return tuple(v) if isinstance(v, (list, tuple)) else v          # JSON do painel vira lista
    return next((tuple(v) for k, v in t.items() if chave.startswith(k)), None)


def custo_usd(modelo: str, entrada: int = 0, saida: int = 0, cache_escrita: int = 0, cache_leitura: int = 0,
              tabela: dict | None = None) -> float:
    """Custo da chamada em dólares. Modelo desconhecido → 0.0 (aparece como 'sem preço' no painel)."""
    p = preco_do_modelo(modelo, tabela)
    if not p:
        return 0.0
    pe, ps, pce, pcl = p
    return round((entrada * pe + saida * ps + cache_escrita * pce + cache_leitura * pcl) / 1_000_000, 6)
