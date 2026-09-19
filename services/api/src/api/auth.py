"""Autenticação do painel.

Token estático (`SDR_PAINEL_TOKEN`), o mesmo que o WebSocket do painel exige. No perfil local,
sem token configurado, vale o `dev-token`; fora dele, sem segredo configurado nada é aceito.

O `HTTPBearer` existe por um motivo além de ler o cabeçalho: é ele que faz a rota aparecer como
protegida no OpenAPI. Antes, `corretor_atual` lia `request.headers` na mão — funcionava, mas o
Swagger mostrava tudo como público e não tinha botão **Authorize**, então ninguém conseguia testar
uma rota de corretor pela documentação.
"""
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sdr_shared.seguranca import painel

# auto_error=False: quem decide a resposta é o código abaixo.
# `description` aparece na caixa do Authorize — é onde a pessoa descobre o que digitar.
bearer = HTTPBearer(
    auto_error=False,
    scheme_name="Token do painel",
    description="O valor de `SDR_PAINEL_TOKEN` (em desenvolvimento, `dev-token`).",
)

NAO_AUTORIZADO = {401: {"description": "Credencial ausente ou inválida."}}


def corretor_atual(request: Request,
                   credencial: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if credencial and painel.valido(credencial.credentials.strip()):
        return _registrar_ator(request, {"id": "corretor-dev", "email": "corretor@local"})
    raise HTTPException(401, "credencial do painel ausente ou inválida")


def _registrar_ator(request: Request, ator: dict) -> dict:
    """Deixa quem está agindo visível para o middleware de auditoria."""
    request.state.corretor = ator
    return ator
