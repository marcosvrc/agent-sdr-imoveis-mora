"""Registro automático de auditoria na API.

Tudo que MUDA o sistema passa por aqui (POST/PUT/PATCH/DELETE), mais as exportações de dados.
Leituras rotineiras ficam de fora de propósito: o painel recarrega sozinho a cada 15s e registrá-las
encheria a auditoria de ruído, escondendo o que importa.
"""
import json
import re
import time

from fastapi import Request
from sdr_shared.db import AuditoriaRepository
from starlette.middleware.base import BaseHTTPMiddleware

# rota → (ação, entidade); o id sai do próprio caminho
ROTAS: list[tuple[re.Pattern, str, str, str]] = [
    (re.compile(r"^/handoff/([^/]+)/assumir$"), "POST", "lead.handoff_assumido", "lead"),
    (re.compile(r"^/handoff/([^/]+)/responder$"), "POST", "lead.corretor_respondeu", "lead"),
    (re.compile(r"^/handoff/([^/]+)/devolver$"), "POST", "lead.devolvido_ao_agente", "lead"),
    (re.compile(r"^/leads/([^/]+)/corretor$"), "PUT", "lead.corretor_atribuido", "lead"),
    (re.compile(r"^/leads/([^/]+)/analisar$"), "POST", "lead.analise_solicitada", "lead"),
    (re.compile(r"^/leads/crm/sync$"), "POST", "lead.exportado_crm", "lead"),
    (re.compile(r"^/corretores$"), "POST", "corretor.criado", "corretor"),
    (re.compile(r"^/corretores/([^/]+)$"), "PUT", "corretor.alterado", "corretor"),
    (re.compile(r"^/corretores/([^/]+)$"), "DELETE", "corretor.removido", "corretor"),
    (re.compile(r"^/imoveis/([^/]+)/fotos$"), "POST", "imovel.foto_enviada", "imovel"),
    (re.compile(r"^/imoveis/([^/]+)/fotos$"), "PUT", "imovel.fotos_reordenadas", "imovel"),
    (re.compile(r"^/imoveis/([^/]+)/fotos/([^/]+)$"), "DELETE", "imovel.foto_removida", "imovel"),
    (re.compile(r"^/config/([^/]+)$"), "PUT", "configuracao.alterada", "configuracao"),
    (re.compile(r"^/config/([^/]+)$"), "DELETE", "configuracao.restaurada", "configuracao"),
    (re.compile(r"^/governanca/limites$"), "PUT", "governanca.limites_alterados", "configuracao"),
    (re.compile(r"^/governanca/precos/([^/]+)$"), "PUT", "governanca.preco_alterado", "configuracao"),
    (re.compile(r"^/governanca/precos/([^/]+)$"), "DELETE", "governanca.preco_restaurado", "configuracao"),
]


# Marcar um aviso como lido muda o sistema, mas registrar isso só afogaria a trilha em ruído.
IGNORADAS = (re.compile(r"^/notificacoes(/.*)?$"),
             re.compile(r"^/calendario(/.*)?$"))   # auditado com detalhe dentro do próprio router


def _classificar(caminho: str, metodo: str) -> tuple[str, str, str | None] | None:
    if any(p.match(caminho) for p in IGNORADAS):
        return None
    for padrao, m, acao, entidade in ROTAS:
        if m == metodo and (mt := padrao.match(caminho)):
            return acao, entidade, (mt.group(1) if mt.groups() else None)
    if metodo in ("POST", "PUT", "PATCH", "DELETE"):                 # rota nova ainda não mapeada
        return f"{metodo.lower()}{caminho.replace('/', '.')}", caminho.strip("/").split("/")[0] or "api", None
    return None


class AuditoriaMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        classificacao = _classificar(request.url.path, request.method)
        if not classificacao:
            return await call_next(request)

        corpo = b""
        if request.method in ("POST", "PUT", "PATCH"):
            corpo = await request.body()                              # lido aqui, reinjetado abaixo
            async def receive():
                return {"type": "http.request", "body": corpo, "more_body": False}
            request = Request(request.scope, receive)

        t0 = time.perf_counter()
        resposta = await call_next(request)
        acao, entidade, entidade_id = classificacao
        ator = getattr(request.state, "corretor", None) or {}
        dados: dict = {"metodo": request.method, "rota": request.url.path,
                       "ms": int((time.perf_counter() - t0) * 1000)}
        if corpo:
            try:
                dados["enviado"] = json.loads(corpo)
            except Exception:
                dados["enviado"] = "(corpo não-JSON)"
        if request.query_params:
            dados["filtros"] = dict(request.query_params)
        ok = resposta.status_code < 400
        AuditoriaRepository().registrar(
            acao=acao, entidade=entidade, entidade_id=entidade_id,
            ator_tipo="corretor" if ator else "sistema", ator_id=ator.get("id"), ator_nome=ator.get("email"),
            dados=dados, origem=request.client.host if request.client else None,
            resultado="ok" if ok else "erro", detalhe=None if ok else f"HTTP {resposta.status_code}")
        return resposta
