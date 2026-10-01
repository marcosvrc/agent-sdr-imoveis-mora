"""Modelos do agente, um acessor por papel (ver `sdr_shared.papeis`).

A escolha é reavaliada a cada chamada porque a governança pode degradar para o modelo barato quando o
orçamento estoura (shared/sdr_shared/db/governanca.py) E porque o painel pode trocar o modelo — ou o
reserva — em tempo de execução (shared/sdr_shared/db/modelos.py, ADR-0010).

Quem usa o quê:
- `llm_conversa`     — qualificador (resposta), consultor, agendador, followup, reativador
- `llm_roteamento`   — supervisor, só quando as regras determinísticas não decidem
- `llm_extracao`     — `qualificador._extrair` (e o consultor, que a reaproveita)
- `llm_informacoes`  — nó informacoes (RAG institucional)
- `llm_analise`      — resumidor (briefing e análise, fora do turno)
"""
from functools import lru_cache

from sdr_shared.db import escolha_de_modelo, reserva_do_painel
from sdr_shared.papeis import BARATO
from sdr_shared.ports import get_chat_model, modo_do_agente

# Nomes dos acessores — o dublê dos testes e o modo falso do harness trocam TODOS por esta lista.
# Um papel novo com acessor fora dela chamaria o modelo de verdade no meio da suíte.
ACESSORES = ("llm_conversa", "llm_roteamento", "llm_extracao", "llm_informacoes", "llm_analise")


@lru_cache(maxsize=32)
def _modelo(papel: str, degradado: bool, escolha: tuple):
    """`escolha` entra na chave do cache de propósito: sem ela, um worker de vida longa continuaria
    usando o modelo antigo para sempre depois de uma troca no painel. O reserva também está nela —
    antes não estava, e trocar o reserva pela tela só valia depois de reiniciar o worker.

    `degradado` também é só chave de cache: quem troca o modelo é `get_chat_model`, que precisa do
    papel ORIGINAL para manter temperatura e teto de tokens da conversa quando cai para o barato."""
    return get_chat_model(papel)


def _chave(papel: str) -> tuple:
    try:
        return (*escolha_de_modelo(papel), reserva_do_painel())
    except Exception:
        return (None, None, None)


def _para(papel: str):
    return _modelo(papel, papel != BARATO and modo_do_agente() == "degradado", _chave(papel))


def llm_conversa():
    return _para("conversa")


def llm_roteamento():
    return _para("roteamento")


def llm_extracao():
    """Cartão do lead em JSON. Vazio no painel e no ambiente = o mesmo modelo do roteamento."""
    return _para("extracao")


def llm_informacoes():
    """Resposta presa ao trecho recuperado. Vazio = o mesmo modelo da conversa."""
    return _para("informacoes")


def llm_analise():
    """Briefing/análise do lead: roda fora do turno, então pode usar modelo diferente do da conversa."""
    return _para("analise")
