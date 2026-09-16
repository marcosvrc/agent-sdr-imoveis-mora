"""`state` assinado do OAuth do Google Agenda.

O problema que isto resolve: o `state` era o `corretor_id` em texto puro, e o callback só conferia
se aquele corretor existia. Como o id é derivado do nome (`cor_ana-souza`), dava para adivinhar — e
quem adivinhasse podia rodar o consentimento com a PRÓPRIA conta Google e devolver
`/calendario/callback?code=<código dele>&state=cor_ana-souza`, sobrescrevendo a credencial da Ana.
A partir daí as visitas dela seriam criadas na agenda do atacante, e a disponibilidade lida de lá.

Agora o `state` só é aceito se tiver sido emitido por nós, para aquele corretor, há poucos minutos.
"""
import hmac
import time

from .sessao import _assinar        # mesma chave HMAC da sessão do chat (SDR_SESSAO_SECRET)

VALIDADE_S = 600                    # 10 min: tempo de dar o consentimento, não mais que isso
_SEP = "."


def assinar(corretor_id: str) -> str:
    expira = int(time.time()) + VALIDADE_S
    payload = f"{corretor_id}{_SEP}{expira}"
    return f"{payload}{_SEP}{_assinar(payload)}"


def validar(state: str | None) -> str | None:
    """Devolve o corretor_id se o `state` for nosso e estiver no prazo; senão, None."""
    if not state:
        return None
    partes = state.split(_SEP)
    if len(partes) != 3:
        return None
    corretor_id, expira, assinatura = partes
    if not hmac.compare_digest(assinatura, _assinar(f"{corretor_id}{_SEP}{expira}")):
        return None
    try:
        if int(expira) <= time.time():
            return None
    except ValueError:
        return None
    return corretor_id
