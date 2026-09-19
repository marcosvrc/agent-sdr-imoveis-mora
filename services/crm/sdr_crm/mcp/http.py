"""Transporte HTTP do servidor MCP — como a Mora consome o CRM.

O stdio serve o cliente que sobe o servidor como subprocesso. Este aqui serve o cliente que fala
pela rede, que é a forma que um CRM de verdade exporia: a imobiliária publica um serviço, e o
agente é um sistema separado que se conecta nele. Rodar o CRM como processo filho do agente
funcionaria na demo e mentiria sobre a topologia.

Três decisões:

1. **Sem sessão (`stateless`).** Cada chamada de ferramenta é independente e já carrega a própria
   `operation_id` para idempotência. Guardar sessão daria ao servidor um estado que ele não usa e
   uma forma nova de quebrar quando o agente reinicia no meio de uma conversa.

2. **Resposta JSON, sem SSE.** Nenhuma ferramenta aqui transmite progresso nem faz streaming — são
   todas pergunta e resposta. SSE acrescentaria reconexão e replay de evento para nada.

3. **Token obrigatório, sem exceção configurável.** Este processo carrega a credencial da Mora no
   CRM: quem alcança a porta age como ela sobre dado de cliente. Um "modo aberto para
   desenvolvimento" seria justamente o que sobra ligado quando a demo vira outra coisa, então o
   servidor recusa subir sem `CRM_MCP_TOKEN` e diz como gerar um. Local não é o mesmo que sem
   ninguém escutando: a porta publicada pelo compose alcança a máquina inteira.
"""
import contextlib
import logging
import os
import secrets
import sys

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .servidor import criar_servidor

log = logging.getLogger("crm.mcp.http")

NAO_AUTORIZADO = {"ok": False, "error": {"code": "NAO_AUTORIZADO",
                                         "message": "Credencial ausente ou inválida.",
                                         "retryable": False}}


def _token_esperado() -> str:
    token = os.environ.get("CRM_MCP_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "✗ CRM_MCP_TOKEN não definido.\n"
            "  O servidor MCP carrega a credencial da Mora no CRM; publicá-lo sem autenticação\n"
            "  entrega leitura e escrita de dado de cliente a qualquer processo da máquina.\n"
            "  Gere um valor e coloque em local/.env (o mesmo valor vai para o agente):\n"
            "      python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
    return token


def criar_app(token: str | None = None) -> Starlette:
    esperado = token if token is not None else _token_esperado()
    servidor = criar_servidor()
    gerente = StreamableHTTPSessionManager(app=servidor, stateless=True, json_response=True)

    async def mcp(scope, receive, send):
        # Comparação em tempo constante: o token é um segredo, e `==` em string vaza o prefixo
        # correto pelo tempo de resposta.
        cabecalhos = dict(scope.get("headers") or [])
        recebido = cabecalhos.get(b"authorization", b"").decode()
        apresentado = recebido[7:] if recebido.lower().startswith("bearer ") else ""
        if not secrets.compare_digest(apresentado, esperado):
            log.warning("chamada MCP sem credencial válida de %s", scope.get("client"))
            await JSONResponse(NAO_AUTORIZADO, status_code=401)(scope, receive, send)
            return
        await gerente.handle_request(scope, receive, send)

    async def saude(_):
        return JSONResponse({"ok": True, "servidor": "crm-imobiliario"})

    @contextlib.asynccontextmanager
    async def ciclo(_):
        async with gerente.run():
            yield

    # /saude fica fora do token de propósito: é o healthcheck do compose e não revela nada além de
    # que o processo está de pé.
    return Starlette(routes=[Route("/saude", saude), Mount("/mcp", app=mcp)], lifespan=ciclo)


def servir(porta: int = 8200) -> None:
    import uvicorn
    app = criar_app()
    log.info("MCP do CRM em http://0.0.0.0:%s/mcp", porta)
    uvicorn.run(app, host="0.0.0.0", port=porta, log_config=None)  # noqa: S104 (dentro do compose)


if __name__ == "__main__":
    servir(int(sys.argv[1]) if len(sys.argv) > 1 else 8200)
