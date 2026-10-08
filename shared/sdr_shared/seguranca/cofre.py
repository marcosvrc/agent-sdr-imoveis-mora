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

O formato tem prefixo para o leitor distinguir valor cifrado de valor legado: o que já estava no
banco continua legível, e vira cifrado na próxima gravação.

- `enc:v1:` — chave = SHA-256("cofre:" + segredo). Só leitura: é o que já está gravado.
- `enc:v2:` — chave = HMAC(segredo, "mora/cofre") (`chaves.py`), uma por finalidade. É o que se
  grava agora. Ler v1 com a derivação antiga é o que evita pedir a todo corretor que reconecte a
  agenda; `CorretorRepository.credencial_calendario` regrava o v1 como v2 na primeira leitura.
"""
import base64
import hashlib
import logging

from .chaves import EXEMPLOS_PUBLICOS, derivar, segredo_configurado

log = logging.getLogger("seguranca")
PREFIXO_V1 = "enc:v1:"
PREFIXO = "enc:v2:"                 # o que se grava hoje
_AVISOU = False


def _fernet(chave_bruta: bytes):
    from cryptography.fernet import Fernet
    return Fernet(base64.urlsafe_b64encode(chave_bruta))


def _chave_v1(segredo: str) -> bytes:
    return hashlib.sha256(f"cofre:{segredo}".encode()).digest()


def cifrar(texto: str | None) -> str | None:
    global _AVISOU
    if texto is None:
        return None
    segredo = segredo_configurado()
    if not segredo:
        if not _AVISOU:
            log.warning("SDR_SESSAO_SECRET ausente: credencial guardada sem cifra")
            _AVISOU = True
        return texto
    return PREFIXO + _fernet(derivar(segredo, "cofre")).encrypt(texto.encode()).decode()


def precisa_recifrar(valor: str | None) -> bool:
    """Cifrado no formato antigo — vale regravar como v2 assim que for lido com sucesso."""
    return bool(valor) and valor.startswith(PREFIXO_V1)


def decifrar(valor: str | None) -> str | None:
    """Valor legado (sem prefixo) volta como está. Cifrado com outra chave levanta — trocar o
    segredo invalida as credenciais guardadas, e isso precisa aparecer, não virar token vazio."""
    if valor is None or not valor.startswith((PREFIXO, PREFIXO_V1)):
        return valor
    segredo = segredo_configurado()
    if not segredo:
        raise RuntimeError("credencial cifrada no banco e SDR_SESSAO_SECRET ausente: não dá para ler")
    from cryptography.fernet import InvalidToken
    if valor.startswith(PREFIXO):
        return _fernet(derivar(segredo, "cofre")).decrypt(valor[len(PREFIXO):].encode()).decode()
    corpo = valor[len(PREFIXO_V1):].encode()
    try:
        return _fernet(_chave_v1(segredo)).decrypt(corpo).decode()
    except InvalidToken:
        # Quem rodou com o valor de exemplo do repositório e agora gerou um segredo de verdade tem
        # v1 cifrado com uma chave pública. Ler com ela não expõe nada além do que já estava
        # exposto (qualquer um decifra), e evita obrigar o corretor a reconectar a agenda: a
        # leitura seguinte regrava como v2, com a chave nova. Fora disso, o erro sobe.
        for exemplo in EXEMPLOS_PUBLICOS:
            try:
                texto = _fernet(_chave_v1(exemplo)).decrypt(corpo).decode()
            except InvalidToken:
                continue
            log.warning("credencial da agenda estava cifrada com o SDR_SESSAO_SECRET de exemplo; "
                        "regravando com o segredo atual")
            return texto
        raise
