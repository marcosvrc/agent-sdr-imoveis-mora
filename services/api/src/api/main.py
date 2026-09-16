import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sdr_shared.config import get_settings
from sdr_shared.db import get_pool, servicos_parados
from sdr_shared.log import configurar as configurar_log
from .auditoria_mw import AuditoriaMiddleware
from .routers import imoveis, leads, dashboard, handoff, eventos, corretores, config, governanca, auditoria, clientes, notificacoes, calendario, interesses, reativacao

configurar_log("api")

DESCRICAO = """
API do **Mora**, o agente SDR imobiliário da Vértice Imóveis.

A etiqueta de cada rota diz quem a usa e o que ela exige:

| Etiqueta | Quem usa | Autenticação |
|---|---|---|
| `público` | site vitrine e chat | nenhuma |
| `corretor` | painel do corretor | `Authorization: Bearer …` |
| `operacao` | rotinas de atendimento no painel | `Authorization: Bearer …` |
| `admin` | configuração, governança de IA e auditoria | `Authorization: Bearer …` |

**Como autenticar no perfil local:** clique em **Authorize** e informe o valor de
`SDR_PAINEL_TOKEN` (no ambiente de desenvolvimento, `dev-token`). No perfil AWS o token é o
JWT do Cognito, validado pelo authorizer do API Gateway antes de chegar aqui.

Toda alteração feita por estas rotas é registrada em auditoria (ver `GET /auditoria`).
"""

ETIQUETAS = [
    {"name": "público", "description":
        "Catálogo de imóveis e eventos de navegação. Sem autenticação — é o que a vitrine consome "
        "e o que o CloudFront pode cachear."},
    {"name": "corretor", "description":
        "Leads, conversas, agenda e KPIs do painel. Exige credencial de corretor."},
    {"name": "operacao", "description":
        "Rotinas do dia a dia do atendimento: clientes e notificações."},
    {"name": "admin", "description":
        "Configuração do sistema, modelos de LLM, orçamento, integração de calendário e auditoria."},
    {"name": "infraestrutura", "description":
        "Sinais operacionais consumidos por health check de container e target group."},
]

app = FastAPI(
    title="Mora — SDR Imobiliário API",
    version="0.1.0",
    description=DESCRICAO,
    openapi_tags=ETIQUETAS,
    contact={"name": "Projeto Mora — Vértice Imóveis (POC acadêmica)"},
    license_info={"name": "Uso acadêmico — licença a confirmar"},
    docs_url="/docs",                  # Swagger UI
    redoc_url="/redoc",                # mesma especificação, leitura contínua
    openapi_url="/openapi.json",
    swagger_ui_parameters={"docExpansion": "none", "defaultModelsExpandDepth": 0,
                           "tryItOutEnabled": True, "persistAuthorization": True},
)
# Em produção, defina SDR_CORS_ORIGINS; "*" só faz sentido no desenvolvimento local.
_origens = [o.strip() for o in (get_settings().cors_origins or "").split(",") if o.strip()] or ["*"]
app.add_middleware(CORSMiddleware, allow_origins=_origens, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(AuditoriaMiddleware)      # registra tudo que muda o sistema

app.include_router(imoveis.router, prefix="/imoveis", tags=["público"])       # sem auth, cache CloudFront
app.include_router(eventos.router, prefix="/eventos", tags=["público"])       # navegação do site → cartão do lead
app.include_router(leads.router, prefix="/leads", tags=["corretor"])          # Cognito JWT (aws) / token dev (local)
app.include_router(dashboard.router, prefix="/dashboard", tags=["corretor"])
app.include_router(handoff.router, prefix="/handoff", tags=["corretor"])
app.include_router(interesses.router, prefix="/interesses", tags=["corretor"])
app.include_router(reativacao.router, prefix="/reativacao", tags=["corretor"])
app.include_router(corretores.router, prefix="/corretores", tags=["admin"])
app.include_router(config.router, prefix="/config", tags=["admin"])
app.include_router(governanca.router, prefix="/governanca", tags=["admin"])
app.include_router(auditoria.router, prefix="/auditoria", tags=["admin"])
app.include_router(clientes.router, prefix="/clientes", tags=["operacao"])
app.include_router(notificacoes.router, prefix="/notificacoes", tags=["operacao"])
app.include_router(calendario.router, prefix="/calendario", tags=["admin"])



@app.get("/fotos/{imovel_id}/{nome}", tags=["público"], include_in_schema=False)
def foto(imovel_id: str, nome: str):
    """Fotos enviadas pelo painel (perfil local: disco). Na AWS: S3 + CloudFront com a mesma URL relativa."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", imovel_id) or not re.fullmatch(r"[a-f0-9]{32}\.(jpg|png|webp)", nome):
        raise HTTPException(404)
    arq = Path(get_settings().fotos_dir) / imovel_id / nome
    if not arq.is_file():
        raise HTTPException(404)
    return FileResponse(arq, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/health", tags=["infraestrutura"], summary="Saúde do sistema")
def health(response: Response):
    """Saúde de verdade: banco alcançável e nenhum worker calado (ADR-0011).

    Devolve 503 quando algo está degradado — é o que o `healthcheck` do compose e o target group
    da AWS leem. Um /health que devolve 200 sempre não é monitoramento, é decoração."""
    problemas: list[str] = []
    try:
        with get_pool().connection() as c:
            c.execute("SELECT 1")
    except Exception as e:
        problemas.append(f"banco: {type(e).__name__}")
    parados = servicos_parados()
    problemas += [f"{p['servico']} sem sinal há {p['ha_segundos']}s" for p in parados]
    if problemas:
        response.status_code = 503
    return {"ok": not problemas, "agente": "Mora", "problemas": problemas}


try:
    from mangum import Mangum
    handler = Mangum(app)          # Lambda (perfil aws)
except ImportError:                # perfil local não precisa do Mangum
    handler = None
