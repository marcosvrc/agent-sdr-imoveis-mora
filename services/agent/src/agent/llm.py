"""Modelos do agente. A escolha é reavaliada a cada chamada porque a governança pode degradar
Sonnet → Haiku quando o orçamento estoura (shared/sdr_shared/db/governanca.py) E porque o painel
pode trocar o modelo em tempo de execução (shared/sdr_shared/db/modelos.py, ADR-0010)."""
from functools import lru_cache

from sdr_shared.db import escolha_de_modelo
from sdr_shared.ports import get_chat_model, modo_do_agente


@lru_cache(maxsize=32)
def _modelo(papel: str, degradado: bool, escolha: tuple):
    """`escolha` entra na chave do cache de propósito: sem ela, um worker de vida longa continuaria
    usando o modelo antigo para sempre depois de uma troca no painel."""
    return get_chat_model("roteamento" if degradado and papel != "roteamento" else papel)


def _chave(papel: str) -> tuple:
    try:
        return escolha_de_modelo(papel)
    except Exception:
        return (None, None)


def llm_conversa():
    return _modelo("conversa", modo_do_agente() == "degradado", _chave("conversa"))


def llm_roteamento():
    return _modelo("roteamento", False, _chave("roteamento"))


def llm_analise():
    """Briefing/análise do lead: roda fora do turno, então pode usar modelo diferente do da conversa."""
    return _modelo("analise", modo_do_agente() == "degradado", _chave("analise"))
