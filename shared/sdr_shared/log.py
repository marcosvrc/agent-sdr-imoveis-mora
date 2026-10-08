"""Log estruturado (ADR-0011). Uma linha JSON por evento quando ligado; texto legível quando não.

Por que JSON: dá para fatiar com `jq` (`docker compose logs agent | jq 'select(.no)'`), e qualquer
coletor de log consulta campo por campo sem regex. É a metade "eventos" da observabilidade — a
outra metade (números agregados) vive nas tabelas `turnos`/`saude`.

Uso:
    from sdr_shared.log import configurar, contexto
    configurar("agent")
    contexto(lead_id=lead.id, canal="telegram")      # entra em toda linha subsequente do turno
    log.info("resposta enviada", extra={"campos": {"duracao_ms": 812}})

`contexto` é por thread/task (ContextVar), então workers concorrentes não misturam lead_id.
"""
import json
import logging
import os
import re
import sys
from contextvars import ContextVar

# default=None e não {}: um dicionário como default é UM objeto só, compartilhado por todos os
# contextos — o mesmo tipo de armadilha que o `caminho` do grafo (ADR-0011). Aqui só se atribui
# dicionário novo, mas o default seguro impede que uma mutação futura vaze entre turnos.
_ctx: ContextVar[dict | None] = ContextVar("log_ctx", default=None)

# Atributos que o LogRecord sempre tem — o resto é campo que alguém colocou de propósito.
_PADRAO = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}


def contexto(**campos) -> None:
    """Acrescenta campos ao contexto do fluxo atual. Chamar no início do turno."""
    _ctx.set({**(_ctx.get() or {}), **{k: v for k, v in campos.items() if v is not None}})


def limpar_contexto() -> None:
    _ctx.set({})


class FormatadorJSON(logging.Formatter):
    def __init__(self, servico: str):
        super().__init__()
        self.servico = servico

    def format(self, r: logging.LogRecord) -> str:
        d = {"em": self.formatTime(r, "%Y-%m-%dT%H:%M:%S%z"), "nivel": r.levelname,
             "servico": self.servico, "origem": r.name, "msg": r.getMessage(), **(_ctx.get() or {})}
        d.update(getattr(r, "campos", {}) or {})
        d.update({k: v for k, v in r.__dict__.items() if k not in _PADRAO and k != "campos"})
        if r.exc_info:
            d["erro"] = self.formatException(r.exc_info)[-2000:]     # cortado: log não é depurador
        return json.dumps(d, ensure_ascii=False, default=str)


def json_ligado() -> bool:
    """Ligado por padrão fora do perfil local — em produção ninguém lê log com o olho."""
    v = os.getenv("SDR_LOG_JSON")
    if v is not None:
        return v.strip().lower() in ("1", "true", "sim")
    return os.getenv("SDR_PROFILE", "producao").strip().lower() != "local"


# Segredos que já apareceram em log por acidente: o token de bot do Telegram vai na URL da Bot API,
# e qualquer traceback de httpx a imprimia inteira. Mascarar na saída é a rede de proteção; o
# código de cada canal continua evitando logar URL.
_SEGREDOS = (re.compile(r"\bbot\d{6,}:[A-Za-z0-9_-]{30,}"), re.compile(r"\b\d{6,}:AA[A-Za-z0-9_-]{30,}"))


class _Mascarar(logging.Formatter):
    def __init__(self, interno: logging.Formatter):
        super().__init__()
        self.interno = interno

    def format(self, record: logging.LogRecord) -> str:
        texto = self.interno.format(record)
        for padrao in _SEGREDOS:
            texto = padrao.sub("<token-do-bot>", texto)
        return texto


def configurar(servico: str, nivel: int = logging.INFO) -> None:
    """Idempotente: substitui os handlers da raiz. Chamar uma vez, no ponto de entrada do processo."""
    raiz = logging.getLogger()
    for h in list(raiz.handlers):
        raiz.removeHandler(h)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(_Mascarar(FormatadorJSON(servico) if json_ligado()
                             else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")))
    raiz.addHandler(h)
    raiz.setLevel(nivel)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # Depois dos handlers, para o aviso/recusa sair no formato do serviço. É aqui porque esta é a
    # única chamada que TODO processo faz ao subir (ver seguranca/subida.py).
    from .seguranca.subida import verificar
    verificar(servico)
