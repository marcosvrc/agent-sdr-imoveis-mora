"""Autenticação do painel.

Perfil AWS: o JWT do Cognito é validado pelo authorizer do API Gateway; aqui só lemos as claims.
Perfil local: token estático (`SDR_PAINEL_TOKEN`), o mesmo que o WebSocket do painel exige.

O `HTTPBearer` existe por um motivo além de ler o cabeçalho: é ele que faz a rota aparecer como
protegida no OpenAPI. Antes, `corretor_atual` lia `request.headers` na mão — funcionava, mas o
Swagger mostrava tudo como público e não tinha botão **Authorize**, então ninguém conseguia testar
uma rota de corretor pela documentação.
"""
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sdr_shared.config import get_settings
from sdr_shared.seguranca import painel

# auto_error=False: quem decide a resposta é o código abaixo, que distingue perfil local de AWS.
# `description` aparece na caixa do Authorize — é onde a pessoa descobre o que digitar.
bearer = HTTPBearer(
    auto_error=False,
    scheme_name="Token do painel",
    description=("Perfil local: o valor de `SDR_PAINEL_TOKEN` (em desenvolvimento, `dev-token`). "
                 "Perfil AWS: o JWT emitido pelo Cognito."),
)

NAO_AUTORIZADO = {401: {"description": "Credencial ausente ou inválida."}}


def corretor_atual(request: Request,
                   credencial: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    if get_settings().profile == "local":                      # sem Cognito: token estático de dev
        if credencial and painel.valido(credencial.credentials.strip()):
            return _registrar_ator(request, {"id": "corretor-dev", "email": "corretor@local"})
        raise HTTPException(401, "credencial do painel ausente ou inválida")
    claims = request.scope.get("aws.event", {}).get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims")
    if not claims:
        raise HTTPException(401, "JWT ausente no contexto do authorizer")
    return _registrar_ator(request, {"id": claims["sub"], "email": claims.get("email")})


def _registrar_ator(request: Request, ator: dict) -> dict:
    """Deixa quem está agindo visível para o middleware de auditoria."""
    request.state.corretor = ator
    return ator
