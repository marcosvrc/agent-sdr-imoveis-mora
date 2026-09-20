"""Cifra em repouso para o pouco que o banco guarda de segredo de terceiros — hoje, o refresh
token do Google Calendar do corretor.

Por que existe: o refresh token dá acesso à agenda da pessoa enquanto ela não revogar, e estava em
texto puro numa coluna. Um dump do banco (backup, `pg_dump` num ticket de suporte, o próprio
`make reset` de alguém curioso) carregava a agenda de todos os corretores junto.

Fernet (AES-128-CBC + HMAC-SHA256, da `cryptography`), com chave derivada de `SDR_SESSAO_SECRET`:
é o segredo que já precisa existir e ser igual entre os processos. Sem ele, cada processo teria
uma chave própria e a API cifraria o que o worker não consegue ler — por isso, sem segredo
configurado, o valor é guardado como sempre foi (texto puro), com aviso no log. Silêncio não; mas
quebrar a agenda de quem está em desenvolvimento sem o `.env` completo também não.

O formato tem prefixo (`enc:v1:`) para o leitor distinguir valor cifrado de valor legado: o que
já estava no banco continua legível, e vira cifrado na próxima gravação.
"""
import base64
import hashlib
import logging

from ..config import get_settings

log = logging.getLogger("seguranca")
PREFIXO = "enc:v1:"
_AVISOU = False


def _chave() -> bytes | None:
    segredo = getattr(get_settings(), "sessao_secret", None)
    if not segredo:
        return None
    return base64.urlsafe_b64encode(hashlib.sha256(f"cofre:{segredo}".encode()).digest())


def cifrar(texto: str | None) -> str | None:
    global _AVISOU
    if texto is None:
        return None
    chave = _chave()
    if chave is None:
        if not _AVISOU:
            log.warning("SDR_SESSAO_SECRET ausente: credencial guardada sem cifra")
            _AVISOU = True
        return texto
    from cryptography.fernet import Fernet
    return PREFIXO + Fernet(chave).encrypt(texto.encode()).decode()


def decifrar(valor: str | None) -> str | None:
    """Valor legado (sem prefixo) volta como está. Cifrado com outra chave levanta — trocar o
    segredo invalida as credenciais guardadas, e isso precisa aparecer, não virar token vazio."""
    if valor is None or not valor.startswith(PREFIXO):
        return valor
    chave = _chave()
    if chave is None:
        raise RuntimeError("credencial cifrada no banco e SDR_SESSAO_SECRET ausente: não dá para ler")
    from cryptography.fernet import Fernet
    return Fernet(chave).decrypt(valor[len(PREFIXO):].encode()).decode()
