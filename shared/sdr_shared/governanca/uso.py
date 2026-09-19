"""Registro de uso de LLM: um callback do LangChain grava cada chamada (tokens, custo, latência).

Fica em `shared/` porque vale para todo serviço que chama modelo — o agente é quem mais usa.
O contexto (lead, nó do grafo, papel) vem de contextvars preenchidas pelo grafo, para não
poluir a assinatura dos nós. Falha de gravação nunca derruba a conversa.
"""
import contextvars
import logging
import time
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

from ..config import get_settings
from .precos import custo_usd

log = logging.getLogger(__name__)

ctx_lead: contextvars.ContextVar[str | None] = contextvars.ContextVar("sdr_lead", default=None)
ctx_no: contextvars.ContextVar[str | None] = contextvars.ContextVar("sdr_no", default=None)
ctx_papel: contextvars.ContextVar[str | None] = contextvars.ContextVar("sdr_papel", default=None)


def _tokens(resposta: Any) -> dict:
    """Extrai tokens do retorno, cobrindo os formatos de Anthropic, OpenAI e Ollama."""
    saida = {"entrada": 0, "saida": 0, "cache_escrita": 0, "cache_leitura": 0}
    gen = (resposta.generations or [[]])[0] if getattr(resposta, "generations", None) else []
    msg = getattr(gen[0], "message", None) if gen else None
    um = getattr(msg, "usage_metadata", None) if msg is not None else None
    if um:
        saida["entrada"] = int(um.get("input_tokens") or 0)
        saida["saida"] = int(um.get("output_tokens") or 0)
        det = um.get("input_token_details") or {}
        saida["cache_leitura"] = int(det.get("cache_read") or 0)
        saida["cache_escrita"] = int(det.get("cache_creation") or 0)
        saida["entrada"] = max(0, saida["entrada"] - saida["cache_leitura"] - saida["cache_escrita"])
        return saida
    llm_out = getattr(resposta, "llm_output", None) or {}
    u = llm_out.get("usage") or llm_out.get("token_usage") or {}
    saida["entrada"] = int(u.get("input_tokens") or u.get("prompt_tokens") or 0)
    saida["saida"] = int(u.get("output_tokens") or u.get("completion_tokens") or 0)
    return saida


def _modelo(serialized: dict, kwargs: dict, resposta: Any = None) -> str:
    for fonte in ((getattr(resposta, "llm_output", None) or {}), kwargs, (serialized or {}).get("kwargs", {})):
        for chave in ("model_name", "model", "model_id"):
            if v := fonte.get(chave):
                return str(v)
    return "desconhecido"


class RegistradorUso(BaseCallbackHandler):
    """Grava uma linha por chamada de modelo. Registrado no factory, vale para todos os nós."""

    def __init__(self, papel: str = "conversa", provider: str | None = None):
        self.papel = papel
        # Com fallback ativo quem atende pode não ser o provedor do .env; sem isto a governança
        # registraria a chamada no nome do primário e o painel mostraria um número mentiroso.
        self.provider = provider
        self._inicio: dict[Any, float] = {}

    def on_llm_start(self, serialized, prompts, *, run_id=None, **kwargs):
        self._inicio[run_id] = time.perf_counter()

    on_chat_model_start = on_llm_start

    def on_llm_end(self, response, *, run_id=None, **kwargs):
        self._gravar(response, run_id, None, kwargs)

    def on_llm_error(self, error, *, run_id=None, **kwargs):
        self._gravar(None, run_id, str(error)[:300], kwargs)

    def _gravar(self, resposta, run_id, erro: str | None, kwargs: dict):
        try:
            ms = int((time.perf_counter() - self._inicio.pop(run_id, time.perf_counter())) * 1000)
            s = get_settings()
            t = _tokens(resposta) if resposta is not None else {"entrada": 0, "saida": 0, "cache_escrita": 0, "cache_leitura": 0}
            modelo = _modelo(kwargs.get("serialized", {}), kwargs.get("invocation_params", {}) or {}, resposta) \
                or (s.model_conversa if self.papel == "conversa" else s.model_roteamento)
            if modelo == "desconhecido":
                modelo = s.model_conversa if self.papel == "conversa" else s.model_roteamento
            from ..db.governanca import UsoRepository
            UsoRepository().registrar(
                lead_id=ctx_lead.get(), no=ctx_no.get(), papel=ctx_papel.get() or self.papel,
                provider=self.provider or s.llm_provider, modelo=modelo, latencia_ms=ms, erro=erro,
                custo=custo_usd(modelo, t["entrada"], t["saida"], t["cache_escrita"], t["cache_leitura"], UsoRepository().precos()),
                **t)
        except Exception:                       # observabilidade nunca pode derrubar o atendimento
            log.debug("falha ao registrar uso de LLM", exc_info=True)


def callbacks_para(papel: str, provider: str | None = None) -> list[BaseCallbackHandler]:
    return [RegistradorUso(papel, provider)]
