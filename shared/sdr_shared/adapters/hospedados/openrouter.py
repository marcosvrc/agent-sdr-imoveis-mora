"""Catálogo do OpenRouter: parâmetros que cada modelo aceita e preço de cada um (ADR-0016).

Duas perguntas que só o catálogo responde, e as duas decidem se uma chamada funciona:

1. **O modelo aceita `temperature`? E `reasoning`?** Mandar parâmetro que o modelo não declara, com
   `require_parameters` ligado (o cliente da extração liga), deixa o OpenRouter sem endpoint nenhum
   para rotear — erro em toda chamada. Sem ele ligado, o parâmetro é ignorado em silêncio.
2. **Quanto custa?** Modelo sem preço é gravado com custo zero, e custo zero desliga o teto mensal
   do painel de Governança. O OpenRouter publica o preço de cada modelo; sincronizar é mais honesto
   que digitar à mão.

A lista é pública (sem chave) e muda devagar: uma leitura a cada seis horas por processo basta. Falha
de rede devolve "não sei" (`None`), nunca lista vazia: "não sei" deixa o factory decidir pelo nome do
modelo; "vazio" o faria concluir que o modelo não aceita parâmetro nenhum.
"""
import logging
import threading
import time

import httpx

from ...config import get_settings

log = logging.getLogger(__name__)

VALIDADE_S = 6 * 3600
_cache: dict = {"em": 0.0, "modelos": None}
_trava = threading.Lock()


def catalogo(forcar: bool = False) -> dict[str, dict] | None:
    """`{id: entrada do /models}` ou None se o OpenRouter não respondeu."""
    with _trava:
        fresco = _cache["modelos"] is not None and time.time() - _cache["em"] < VALIDADE_S
        if fresco and not forcar:
            return _cache["modelos"]
        try:
            r = httpx.get(f"{get_settings().openrouter_url.rstrip('/')}/models", timeout=5)
            r.raise_for_status()
            modelos = {m["id"]: m for m in r.json().get("data", []) if m.get("id")}
        except Exception as e:
            log.warning("catálogo do OpenRouter indisponível (%s): decidindo pelo nome do modelo",
                        type(e).__name__)
            return _cache["modelos"]              # o velho, se houver, é melhor que nenhum
        _cache.update(em=time.time(), modelos=modelos)
        return modelos


def parametros_suportados(modelo: str) -> set[str] | None:
    """Parâmetros que o modelo declara, ou None quando não dá para saber."""
    tudo = catalogo()
    if tudo is None or modelo not in tudo:
        return None
    return set(tudo[modelo].get("supported_parameters") or [])


def config_raciocinio(modelo: str) -> dict | None:
    """O bloco `reasoning` do catálogo: `mandatory`, `supported_efforts`, `default_effort`.
    None quando o catálogo não respondeu ou não descreve o modelo."""
    tudo = catalogo()
    if tudo is None or modelo not in tudo:
        return None
    r = tudo[modelo].get("reasoning")
    return r if isinstance(r, dict) else None


def _por_milhao(v) -> float:
    try:
        return round(float(v or 0) * 1_000_000, 6)
    except (TypeError, ValueError):
        return 0.0


def preco(entrada: dict) -> tuple[float, float, float, float] | None:
    """Converte o preço do OpenRouter (USD por TOKEN, em string) para a tupla da governança (USD por
    MILHÃO: entrada, saída, escrita de cache, leitura de cache). Sem preço de entrada e saída, None:
    um modelo "de graça" por falta de dado é exatamente o zero que desliga o teto."""
    p = entrada.get("pricing") or {}
    if p.get("prompt") in (None, "") or p.get("completion") in (None, ""):
        return None
    return (_por_milhao(p.get("prompt")), _por_milhao(p.get("completion")),
            _por_milhao(p.get("input_cache_write")), _por_milhao(p.get("input_cache_read")))


def precos_de(modelos: list[str]) -> tuple[dict[str, list[float]], list[str]]:
    """Preços dos modelos pedidos e a lista dos que o OpenRouter não conhece."""
    tudo = catalogo(forcar=True)
    if tudo is None:
        raise RuntimeError("o catálogo do OpenRouter não respondeu; tente de novo em instantes")
    achados, faltando = {}, []
    for m in modelos:
        p = preco(tudo[m]) if m in tudo else None
        if p is None:
            faltando.append(m)
        else:
            achados[m] = list(p)
    return achados, faltando
