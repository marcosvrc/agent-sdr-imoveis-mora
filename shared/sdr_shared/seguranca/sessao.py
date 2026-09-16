"""Sessão assinada do chat do site.

O problema que isto resolve: o `session_id` vinha do navegador e virava o `lead_id`. Quem soubesse
(ou adivinhasse) o id de outro visitante lia a conversa dele e escrevia no lugar dele. Agora o
servidor emite o id junto com uma assinatura HMAC; sem a assinatura, o id não vale nada.

Não é login — o visitante segue anônimo. É só a prova de que aquele id foi emitido por nós.
"""
import base64
import hashlib
import hmac
import secrets
import time

from ..config import get_settings

VALIDADE_S = 12 * 3600          # uma sessão de navegação; depois o widget pede outra
_SEP = "."


def _segredo() -> bytes:
    s = get_settings()
    chave = getattr(s, "sessao_secret", None)
    if not chave:
        # Sem segredo configurado o sistema não fica inseguro em silêncio: cada processo gera o seu,
        # o que invalida sessões entre reinícios (visível) em vez de aceitar qualquer assinatura.
        chave = _efemero()
    return hashlib.sha256(str(chave).encode()).digest()


_EFEMERO: str | None = None


def _efemero() -> str:
    global _EFEMERO
    if _EFEMERO is None:
        _EFEMERO = secrets.token_hex(32)
    return _EFEMERO


def _assinar(payload: str) -> str:
    mac = hmac.new(_segredo(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def emitir() -> dict:
    """Cria uma sessão nova. O id é do servidor — o navegador não escolhe o seu."""
    sid = secrets.token_urlsafe(16)
    expira = int(time.time()) + VALIDADE_S
    payload = f"{sid}{_SEP}{expira}"
    return {"session_id": sid, "token": f"{payload}{_SEP}{_assinar(payload)}", "expira_em": expira}


def validar(session_id: str, token: str | None) -> bool:
    """Confere que o token foi emitido por nós, não expirou e pertence a este session_id."""
    if not token or not session_id:
        return False
    partes = token.split(_SEP)
    if len(partes) != 3:
        return False
    sid, expira, assinatura = partes
    if not hmac.compare_digest(sid, session_id):
        return False
    if not hmac.compare_digest(assinatura, _assinar(f"{sid}{_SEP}{expira}")):
        return False
    try:
        return int(expira) > time.time()
    except ValueError:
        return False
