"""Teto de corpo contado em bytes recebidos, não só no Content-Length.

O teto antigo (seção 11) só olhava o cabeçalho. Com `Transfer-Encoding: chunked` não há
Content-Length, e nada era limitado: a rota lia o corpo inteiro para a memória — um POST de 2 GB em
pedaços era 2 GB de RAM, inclusive no login, que não exige credencial.

Cópia do módulo de mesmo nome da API da Mora: o CRM é um serviço separado e não depende do pacote
compartilhado de lá. Agora o `receive` é embrulhado e conta o que chega;
passou do teto, a leitura para ali e a resposta é 413.

O Content-Length continua sendo conferido primeiro: quando ele existe, recusar ANTES de ler é melhor.
"""
import json

from starlette.exceptions import HTTPException


class CorpoGrande(HTTPException):
    """Levantada de dentro do `receive`. É HTTPException de propósito: o FastAPI embrulha qualquer
    outra exceção da leitura do corpo num 400 genérico, mas deixa HTTPException passar — e aí o 413
    chega ao cliente pelo caminho normal de erro."""

    def __init__(self, teto: int):
        super().__init__(status_code=413, detail=f"corpo acima de {teto} bytes")
        self.teto = teto


async def _responder_413(send, teto: int) -> None:
    corpo = json.dumps({"detail": f"corpo acima de {teto} bytes"}).encode()
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(corpo)).encode())]})
    await send({"type": "http.response.body", "body": corpo})


class LimiteDeCorpo:
    """Middleware ASGI. `teto_para(scope)` devolve o limite daquela requisição (a foto tem o seu)."""

    def __init__(self, app, teto_para, responder=_responder_413):
        self.app, self.teto_para, self.responder = app, teto_para, responder

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        teto = self.teto_para(scope)
        cabecalhos = dict(scope.get("headers") or [])
        tamanho = cabecalhos.get(b"content-length", b"").decode("latin-1")
        if tamanho.isdigit() and int(tamanho) > teto:
            return await self.responder(send, teto)

        recebido = 0
        respondeu = False

        async def receive_contado():
            nonlocal recebido
            msg = await receive()
            if msg["type"] == "http.request":
                recebido += len(msg.get("body") or b"")
                if recebido > teto:
                    raise CorpoGrande(teto)
            return msg

        async def send_marcado(msg):
            nonlocal respondeu
            if msg["type"] == "http.response.start":
                respondeu = True
            await send(msg)

        try:
            await self.app(scope, receive_contado, send_marcado)
        except CorpoGrande:
            # Chegou até aqui quando quem leu o corpo foi um middleware, antes da rota.
            if not respondeu:
                await self.responder(send, teto)
