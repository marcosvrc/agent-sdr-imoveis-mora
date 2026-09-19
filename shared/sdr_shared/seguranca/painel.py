"""Credencial do painel (corretor).

Quem precisa dela: o WebSocket de `services/channels/local/app.py` — o canal `papel=dashboard`
recebe o espelho de TODAS as conversas de TODOS os leads, então não pode ser aberto sem prova de
que quem conecta é da equipe — e as rotas de corretor da API (`services/api/src/api/auth.py`).

Fail-closed de propósito: fora do perfil local, sem `SDR_PAINEL_TOKEN` configurado, nada é aceito.
É a única coisa que `SDR_PROFILE` ainda decide, e é por isso que ele continua existindo: rodar a
entrega com `SDR_PROFILE=local` é o que libera o `dev-token`, e qualquer outro valor exige o
segredo de verdade.
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
