"""Uma chave por finalidade, todas derivadas de `SDR_SESSAO_SECRET`.

Por que derivar em vez de usar o segredo direto: o mesmo segredo assinava a sessão do chat
(`sessao.py`), o `state` do OAuth do Google (`oauth.py`) e cifrava o refresh token da agenda
(`cofre.py`). Com a MESMA chave HMAC e o mesmo formato `<id>.<expira>.<assinatura>`, um `state`
emitido para `cor_ana-souza` era também um token de chat válido para a sessão `cor_ana-souza` — e
vice-versa. Com HMAC(segredo, rótulo) cada finalidade tem a sua chave: uma assinatura emitida para
uma nunca confere na outra, e vazar uma chave derivada não entrega as demais.

E por que recusar o valor de exemplo: `local/.env.example` (público, no repositório) trazia
`dev-local-troque-antes-de-expor-publicamente`. Quem copiou o arquivo e subiu o ambiente para fora
da máquina estava assinando sessões e cifrando a agenda dos corretores com uma chave que qualquer
um lê no GitHub — dava para forjar o token de chat de qualquer visitante e decifrar um dump do banco.
"""
import hashlib
import hmac

from ..config import get_settings

# Valores que já estiveram nos `.env.example` versionados. Não são segredo de ninguém.
EXEMPLOS_PUBLICOS = frozenset({
    "dev-local-troque-antes-de-expor-publicamente",     # local/.env.example
    "troque-por-uma-string-aleatoria-longa",            # .env.example da raiz
})
COMO_GERAR = 'python3 -c "import secrets; print(secrets.token_urlsafe(48))"'


class SegredoDeExemplo(RuntimeError):
    """SDR_SESSAO_SECRET está com um valor público. Não é para seguir com ele."""


def mensagem_segredo_de_exemplo() -> str:
    return ("SDR_SESSAO_SECRET está com o valor de exemplo do repositório — qualquer um que leia o "
            "código forja sessões de chat e decifra os tokens de agenda. Gere um segredo com "
            f"`{COMO_GERAR}` e coloque em local/.env (ou deixe vazio só para desenvolvimento: "
            "chave aleatória por processo).")


def segredo_configurado() -> str | None:
    """O segredo do ambiente, ou None se vazio. Levanta se for um valor público de exemplo."""
    segredo = getattr(get_settings(), "sessao_secret", None) or None
    if segredo is not None and segredo.strip() in EXEMPLOS_PUBLICOS:
        raise SegredoDeExemplo(mensagem_segredo_de_exemplo())
    return segredo


def derivar(segredo: str, finalidade: str) -> bytes:
    """HMAC-SHA256 com o segredo como chave e o rótulo da finalidade como mensagem (32 bytes)."""
    return hmac.new(segredo.encode(), f"mora/{finalidade}".encode(), hashlib.sha256).digest()
