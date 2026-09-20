"""Ajustes de operação editáveis no painel: timeout do LLM, transcrição e refresh do acervo.

Mesmo contrato do modelo por nível (ADR-0010): **o painel manda, o `.env` é o piso**. Campo vazio
na tela significa "não opinei, usa o do ambiente".

A lição que o provedor de reserva ensinou está aplicada aqui desde o começo: "vazio" e "desligado"
precisam ser valores DIFERENTES. Se zero significasse as duas coisas, apagar o campo no painel
nunca conseguiria desligar algo que veio do ambiente — e o operador ficaria mexendo numa tela que
não obedece. Por isso `0` desliga de verdade e `None`/vazio é que delega ao `.env`.

Cache curto pelo mesmo motivo do orçamento e dos modelos: o timeout é lido a cada construção de
modelo e não pode virar um SELECT por chamada.
"""
import time

CHAVE = "operacao"
_cache: dict = {"em": 0.0, "valor": None}


def _do_banco() -> dict:
    from .painel import ConfigRepository
    try:
        return ConfigRepository().todas().get(CHAVE, {}) or {}
    except Exception:                       # sem banco (testes, boot): o ambiente decide sozinho
        return {}


def _bruto(cache_segundos: float = 30) -> dict:
    if _cache["valor"] is None or time.time() - _cache["em"] > cache_segundos:
        _cache.update(em=time.time(), valor=_do_banco())
    return _cache["valor"] or {}


def numero(campo: str, cache_segundos: float = 30) -> float | None:
    """Valor numérico do painel, ou None quando ele não opinou. `0` é resposta, não ausência."""
    v = _bruto(cache_segundos).get(campo)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def texto(campo: str, cache_segundos: float = 30) -> str | None:
    v = (_bruto(cache_segundos).get(campo) or "")
    return v.strip() or None if isinstance(v, str) else None


def invalidar_cache_operacao() -> None:
    _cache.update(em=0.0, valor=None)
