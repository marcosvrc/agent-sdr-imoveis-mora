"""Credencial do painel (corretor) para portas que não têm o authorizer do API Gateway na frente.

Hoje isso é o WebSocket do perfil local (`services/channels/local/app.py`): o canal `papel=dashboard`
recebe o espelho de TODAS as conversas de TODOS os leads, então não pode ser aberto sem prova de que
quem conecta é da equipe. No perfil `aws` o WebSocket é outro serviço (Lambda + API Gateway, ver
infra/stacks/channels_stack.py) e a autorização é feita lá.

Fail-closed de propósito: fora do perfil local, sem `SDR_PAINEL_TOKEN` configurado, nada é aceito.
"""
import hmac

from ..config import get_settings

TOKEN_DEV = "dev-token"          # só vale com SDR_PROFILE=local; ver `esperado()`


def esperado() -> str | None:
    """Token que vale agora, ou None quando nenhuma credencial está configurada (nega tudo)."""
    s = get_settings()
    if s.painel_token:
        return s.painel_token
    return TOKEN_DEV if s.profile == "local" else None


def valido(token: str | None) -> bool:
    """Compara em tempo constante. Sem token configurado ou sem token recebido, é não."""
    alvo = esperado()
    if not alvo or not token:
        return False
    return hmac.compare_digest(token, alvo)
