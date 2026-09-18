"""Erros de negócio do CRM, com o formato único da seção 7.

A regra que separa 422 de 409, e que vale para o arquivo inteiro: **422 é sintaxe, 409 é mundo**.
"orçamento máximo é uma letra" é 422; "não dá para qualificar porque o orçamento nunca foi dito" é
409 — a requisição está perfeitamente bem formada, o que falta é um fato. Misturar os dois tira do
cliente (e do agente) a informação mais útil que existe: dá para tentar de novo com outro corpo, ou
é preciso ir buscar o dado antes?
"""
from typing import Any


class ErroDeNegocio(Exception):
    """Vira a resposta `{"error": {...}, "request_id": ...}` no handler da aplicação."""

    status = 409
    code = "BUSINESS_RULE"
    retryable = False

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def corpo(self, request_id: str) -> dict:
        return {"error": {"code": self.code, "message": self.message,
                          "details": self.details, "retryable": self.retryable},
                "request_id": request_id}


class NaoEncontrado(ErroDeNegocio):
    status, code = 404, "NOT_FOUND"


class SemPermissao(ErroDeNegocio):
    status, code = 403, "FORBIDDEN"


class NaoAutenticado(ErroDeNegocio):
    status, code = 401, "UNAUTHENTICATED"


class ConflitoDeVersao(ErroDeNegocio):
    """If-Match veio com uma versão que já não é a atual: alguém editou no meio do caminho."""

    status, code = 412, "VERSION_CONFLICT"


class PrecondicaoAusente(ErroDeNegocio):
    """428, e não 412: faltou a precondição em vez de ela ter falhado. O cliente precisa saber que
    o caminho é ler o recurso e mandar o If-Match, não repetir a mesma chamada."""

    status, code = 428, "PRECONDITION_REQUIRED"


class ConflitoDeIdempotencia(ErroDeNegocio):
    code = "IDEMPOTENCY_CONFLICT"


class LeadDuplicado(ErroDeNegocio):
    """Identificadores apontando para leads diferentes. Nunca fazemos merge automático: unir dois
    históricos comerciais é irreversível, e desfazer no banco é bem pior do que uma revisão humana."""

    code = "LEAD_CONFLICT"


class QualificacaoIncompleta(ErroDeNegocio):
    code = "QUALIFICATION_INCOMPLETE"


class TransicaoInvalida(ErroDeNegocio):
    code = "INVALID_TRANSITION"


class ContatoBloqueado(ErroDeNegocio):
    code = "CONTACT_BLOCKED"


class SlotIndisponivel(ErroDeNegocio):
    code = "SLOT_UNAVAILABLE"


class AtendimentoHumano(ErroDeNegocio):
    """Encaminhamento aberto ou aceito: o agente registra mensagem recebida e nada mais."""

    code = "HUMAN_IN_CONTROL"


class LimiteExcedido(ErroDeNegocio):
    status, code, retryable = 429, "RATE_LIMITED", True


class DependenciaIndisponivel(ErroDeNegocio):
    status, code, retryable = 503, "DEPENDENCY_UNAVAILABLE", True
