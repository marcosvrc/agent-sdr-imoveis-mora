"""O que toda requisição carrega: quem chama, qual é o request_id e qual é a chave de idempotência.

Concentrar isso aqui é o que permite escrever cada rota como uma função pequena que recebe uma
conexão e devolve `(status, corpo)` — sem repetir, em vinte lugares, o mesmo bloco de autenticação,
transação, idempotência e auditoria. Repetição nesse bloco é como uma rota acaba sem auditoria e
ninguém percebe.
"""
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..config import get_settings
from ..db.connection import leitura, transacao
from ..erros import ErroDeNegocio, LimiteExcedido, NaoAutenticado
from . import auth as autenticacao
from . import protocolo


@dataclass
class Contexto:
    ator: autenticacao.Ator
    request_id: str
    chave_idempotencia: str | None
    if_match: str | None

    @property
    def credencial_id(self) -> str | None:
        return self.ator.id if self.ator.tipo == "service" else None


# --------------------------------------------------------------------------- limite por credencial

# Contador EM MEMÓRIA, de uma instância só (seção 11 manda documentar isso). Com duas réplicas, o
# limite efetivo dobra. Está aqui como proteção contra laço descontrolado do agente, não como
# defesa contra abuso distribuído.
_balde: dict[str, list[float]] = defaultdict(list)


def conferir_limite(chave: str) -> None:
    cfg = get_settings()
    agora = time.monotonic()
    janela = [t for t in _balde[chave] if agora - t < 60]
    if len(janela) >= cfg.rate_limit_por_minuto:
        janela.sort()
        espera = max(1, int(60 - (agora - janela[0])) + 1)
        _balde[chave] = janela
        raise LimiteExcedido(f"Limite de {cfg.rate_limit_por_minuto} chamadas por minuto atingido.",
                             retry_after_seconds=espera)
    janela.append(agora)
    _balde[chave] = janela


def limpar_limites() -> None:
    """Usado pelos testes: sem isto, um teste de limite envenena os seguintes."""
    _balde.clear()


# --------------------------------------------------------------------------- autenticação

def _ator_do_request(request: Request, authorization: str | None, cookie: str | None
                     ) -> autenticacao.Ator:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        with leitura() as conn:
            linha = conn.execute("SELECT * FROM service_credentials WHERE token_hash = %s",
                                 (autenticacao.hash_token(token),)).fetchone()
        return autenticacao.ator_de_credencial(linha)
    if cookie:
        with leitura() as conn:
            linha = conn.execute(
                """SELECT s.user_id, s.expires_at, s.revoked_at, u.name, u.role, u.active
                     FROM sessions s JOIN users u ON u.id = s.user_id
                    WHERE s.token_hash = %s""",
                (autenticacao.hash_token(cookie),)).fetchone()
        return autenticacao.ator_de_sessao(linha)
    raise NaoAutenticado("Informe um token de serviço (Bearer) ou faça login.")


async def contexto(request: Request,
                   authorization: str | None = Header(default=None),
                   idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                   if_match: str | None = Header(default=None, alias="If-Match")) -> Contexto:
    ator = _ator_do_request(request, authorization, request.cookies.get("crm_session"))
    conferir_limite(ator.id or ator.nome)
    return Contexto(ator=ator, request_id=str(uuid.uuid4()),
                    chave_idempotencia=(idempotency_key or "").strip() or None,
                    if_match=if_match)


Ctx = Depends(contexto)


# --------------------------------------------------------------------------- execução de mutação

def envelope(dados, request_id: str) -> dict:
    return {"data": dados, "request_id": request_id}


def executar(ctx: Contexto, method: str, rota: str, corpo: dict | None,
             fn: Callable[[object], tuple[int, dict]], *, exigir_chave: bool = True) -> JSONResponse:
    """Roda a mutação dentro de uma transação, com replay de idempotência e auditoria juntos.

    A ordem importa e é a que a seção 8 pede: **verificar replay ANTES de validar a versão**. Sem
    isso, a repetição de uma transição bem-sucedida que o cliente não chegou a ver receberia 412
    ("versão antiga") em vez do resultado original — e um agente com retry entraria em laço tentando
    reconciliar um estado que já era o desejado.
    """
    cfg = get_settings()
    if exigir_chave and ctx.chave_idempotencia is None:
        raise ErroDeNegocio("Esta operação exige o cabeçalho Idempotency-Key.",
                            hint="Use um identificador estável da ação lógica, não um novo a cada tentativa.")
    corpo_hash = protocolo.hash_corpo(corpo or {})

    with transacao() as conn:
        if ctx.chave_idempotencia:
            anterior = protocolo.buscar_replay(conn, ctx.credencial_id, ctx.chave_idempotencia,
                                               corpo_hash, method, rota)
            if anterior is not None:
                status, guardado = anterior
                return JSONResponse(status_code=status, content=guardado,
                                    headers={"Idempotent-Replay": "true"})
        status, resposta = fn(conn)
        # As linhas vêm do psycopg com UUID, datetime e Decimal — tipos que o JSONResponse não
        # serializa sozinho. Codificar ANTES de gravar o replay é o que garante que a repetição
        # devolva byte a byte o mesmo corpo da primeira vez.
        resposta = jsonable_encoder(resposta)
        if ctx.chave_idempotencia:
            protocolo.gravar_replay(conn, ctx.credencial_id, ctx.chave_idempotencia, corpo_hash,
                                    method, rota, status, resposta, cfg.idempotencia_horas)
    return JSONResponse(status_code=status, content=resposta)
