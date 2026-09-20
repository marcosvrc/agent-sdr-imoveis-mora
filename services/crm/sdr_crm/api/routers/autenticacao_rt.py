"""Sessão humana: login, logout e quem sou eu."""
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, Response

from ...config import get_settings
from ...db.connection import leitura, transacao
from ...erros import NaoAutenticado
from .. import auth as autenticacao
from ..contexto import Contexto, Ctx, conferir_limite_de_login, envelope
from ..esquemas import Login

router = APIRouter(tags=["auth"])

COOKIE = "crm_session"
DURACAO = timedelta(hours=12)


@router.post("/auth/login")
def entrar(corpo: Login, request: Request, resposta: Response):
    """Mensagem única para usuário inexistente, senha errada e conta inativa.

    Distinguir os três diria a um estranho quais e-mails existem na base — e, num CRM, a lista de
    quem trabalha na imobiliária já é informação. A `conferir_senha` roda mesmo sem usuário para o
    tempo de resposta não entregar a mesma coisa.
    """
    conferir_limite_de_login(request, corpo.email)      # antes de tocar no banco ou no argon2
    with leitura() as conn:
        usuario = conn.execute("SELECT * FROM users WHERE lower(btrim(email)) = %s",
                               (corpo.email.strip().lower(),)).fetchone()
    senha_ok = autenticacao.conferir_senha(
        usuario["password_hash"] if usuario else None, corpo.password)
    if not usuario or not senha_ok or not usuario["active"]:
        raise NaoAutenticado("E-mail ou senha inválidos.")

    token = secrets.token_urlsafe(32)
    expira = datetime.now(UTC) + DURACAO
    with transacao() as conn:
        conn.execute("INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                     (usuario["id"], autenticacao.hash_token(token), expira))

    cfg = get_settings()
    resposta.set_cookie(
        COOKIE, token, httponly=True, samesite="lax",
        # `Secure` fora de desenvolvimento: com HTTP em localhost, um cookie Secure simplesmente não
        # é enviado e o login "não funciona" sem nenhuma mensagem de erro.
        secure=not cfg.sintetico, max_age=int(DURACAO.total_seconds()), path="/")
    return {"data": {"id": str(usuario["id"]), "name": usuario["name"], "role": usuario["role"]},
            "request_id": ""}


@router.post("/auth/logout", status_code=204)
def sair(request: Request, resposta: Response):
    """Revoga a sessão NO BANCO, não só apaga o cookie. Apagar o cookie deixa o token válido na
    mão de quem o tivesse copiado — que é justamente de quem se está tentando fugir ao sair."""
    cookie = request.cookies.get(COOKIE)
    if cookie:
        with transacao() as conn:
            conn.execute("UPDATE sessions SET revoked_at = now() "
                         "WHERE token_hash = %s AND revoked_at IS NULL",
                         (autenticacao.hash_token(cookie),))
    resposta.delete_cookie(COOKIE, path="/")
    return Response(status_code=204)


@router.get("/auth/me")
def eu(ctx: Contexto = Ctx):
    return envelope({"actor_type": ctx.ator.tipo, "id": ctx.ator.id, "name": ctx.ator.nome,
                     "role": ctx.ator.papel, "scopes": sorted(ctx.ator.scopes)}, ctx.request_id)
