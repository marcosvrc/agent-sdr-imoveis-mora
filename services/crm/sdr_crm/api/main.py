"""Aplicação FastAPI do CRM.

Base `/v1`, JSON em snake_case, erro sempre no mesmo formato. Nenhuma rota devolve detalhe interno:
o cliente recebe um `code` estável para decidir o que fazer e um `request_id` para a gente achar o
resto no log.
"""
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..config import get_settings
from ..db.connection import leitura
from ..erros import ErroDeNegocio
from .routers import (
    autenticacao_rt,
    dashboard_rt,
    handoffs_rt,
    imoveis_rt,
    leads_rt,
    oportunidades_rt,
    tarefas_rt,
    visitas_rt,
)

log = logging.getLogger("crm")

app = FastAPI(
    title="CRM imobiliário (dados sintéticos)",
    version="1.0.0",
    description=("Registro comercial de uma imobiliária, com dados **exclusivamente sintéticos**. "
                 "Usado para exercitar um agente SDR ponta a ponta."),
    openapi_url="/openapi.json",
    docs_url="/docs",
)

_cfg = get_settings()
app.add_middleware(CORSMiddleware, allow_origins=_cfg.allowed_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def limitar_corpo(request: Request, call_next):
    """256 KB (seção 11). O limite é conferido pelo Content-Length porque recusar antes de ler o
    corpo é o ponto — ler 50 MB para depois dizer que é grande demais já gastou a memória."""
    tamanho = request.headers.get("content-length")
    if tamanho and tamanho.isdigit() and int(tamanho) > _cfg.corpo_maximo_bytes:
        return JSONResponse(status_code=413, content={
            "error": {"code": "PAYLOAD_TOO_LARGE",
                      "message": f"Corpo acima de {_cfg.corpo_maximo_bytes} bytes.",
                      "details": {}, "retryable": False},
            "request_id": str(uuid.uuid4())})
    return await call_next(request)


@app.exception_handler(ErroDeNegocio)
async def erro_de_negocio(request: Request, exc: ErroDeNegocio):
    rid = str(uuid.uuid4())
    cabecalhos = {}
    if exc.status == 429 and "retry_after_seconds" in exc.details:
        cabecalhos["Retry-After"] = str(exc.details["retry_after_seconds"])
    if exc.status == 401:
        cabecalhos["WWW-Authenticate"] = "Bearer"
    return JSONResponse(status_code=exc.status, content=exc.corpo(rid), headers=cabecalhos)


@app.exception_handler(RequestValidationError)
@app.exception_handler(ValidationError)
async def erro_de_validacao(request: Request, exc: ValidationError | RequestValidationError):
    """FastAPI embrulha a validação do corpo em RequestValidationError; o formato padrão dele
    ({"detail": [...]}) não é o erro uniforme da seção 7. Os dois caem aqui."""
    return JSONResponse(status_code=422, content={
        "error": {"code": "VALIDATION_ERROR", "message": "Corpo inválido.",
                  # `include_url` só existe no ValidationError do pydantic; o do FastAPI não aceita.
        "details": {"fields": jsonable_encoder(exc.errors())}, "retryable": False},
        "request_id": str(uuid.uuid4())})


@app.exception_handler(Exception)
async def erro_inesperado(request: Request, exc: Exception):
    """O request_id é a ponte: ele vai para o cliente E para o log, e é por ele que se acha o
    traceback — que nunca sai na resposta."""
    rid = str(uuid.uuid4())
    log.exception("erro inesperado", extra={"request_id": rid, "rota": request.url.path})
    return JSONResponse(status_code=500, content={
        "error": {"code": "INTERNAL_ERROR", "message": "Erro interno.", "details": {},
                  "retryable": True},
        "request_id": rid})


@app.get("/health/live", tags=["health"])
def vivo() -> dict:
    """Não toca no banco de propósito: liveness que depende do banco faz o orquestrador matar uma
    API saudável toda vez que o Postgres pisca."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def pronto() -> JSONResponse:
    """Readiness confere banco E schema aplicado. 'Conecta mas não tem tabela' é indisponível: a
    primeira requisição real quebraria com erro de SQL em vez de 503."""
    try:
        with leitura() as conn:
            faltando = conn.execute(
                """SELECT count(*) = 0 AS falta FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'opportunities'""").fetchone()
        if faltando["falta"]:
            raise RuntimeError("schema não aplicado")
    except Exception:
        return JSONResponse(status_code=503, content={
            "error": {"code": "DEPENDENCY_UNAVAILABLE", "message": "Banco indisponível ou sem schema.",
                      "details": {}, "retryable": True},
            "request_id": str(uuid.uuid4())})
    return JSONResponse(status_code=200, content={"status": "ok"})


# `dashboard_rt` também serve /audit-events: os dois são leitura agregada e compartilham a mesma
# paginação por cursor.
for rt in (autenticacao_rt, leads_rt, oportunidades_rt, imoveis_rt, visitas_rt, tarefas_rt,
           handoffs_rt, dashboard_rt):
    app.include_router(rt.router, prefix="/v1")
