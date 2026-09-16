"""Perfil local: substitui API Gateway HTTP + WebSocket. Um processo FastAPI com:
  POST/GET /webhook  → mesmo adapter do WhatsApp (channels/whatsapp/canal_whatsapp/adapter.py)
  WS  /ws            → widget do site (papel=lead) e dashboard (papel=dashboard)
  worker de saída    → consome outbound-web do Redis e faz push nas conexões abertas
Exposto para a Meta via túnel (cloudflared) — ver local/docker-compose.yml."""
import asyncio
import json
import logging
import sys
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Response
from fastapi.middleware.cors import CORSMiddleware

sys.path.append(str(Path(__file__).parents[1] / "whatsapp"))
from canal_whatsapp.inbound import handler as wa_handler   # noqa: E402
from sdr_shared.config import get_settings                # noqa: E402
from sdr_shared.log import configurar as configurar_log  # noqa: E402
from sdr_shared.ports import get_broker                  # noqa: E402
from sdr_shared.messaging import TipoMensagem, MensagemNormalizada, Canal  # noqa: E402
from sdr_shared.seguranca import emitir, validar, painel  # noqa: E402

configurar_log("channels")
log = logging.getLogger("canal")
conexoes: dict[str, set[WebSocket]] = {"dashboard": set()}
# Respostas que chegaram enquanto o cliente estava desconectado — entregues quando ele volta,
# para que nenhuma resposta da Mora se perca num refresh ou numa queda de rede.
pendentes: dict[str, deque] = defaultdict(lambda: deque(maxlen=20))
JANELA_PENDENTE_S = 600


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Sobe o worker que consome `outbound-web` do Redis e empurra para as conexões abertas."""
    loop = asyncio.get_running_loop()

    def on_msg(body: str):
        b = json.loads(body)
        alvos = conexoes.get(b["identificador"], set())
        if not alvos:                                   # ninguém ouvindo: guarda para a reconexão
            pendentes[b["identificador"]].append((time.time(), b["resposta"]))
        else:
            asyncio.run_coroutine_threadsafe(_push(alvos, b["resposta"]), loop)
        asyncio.run_coroutine_threadsafe(_push(conexoes["dashboard"], {"evento": "mensagem", **b}), loop)

    tarefa = loop.run_in_executor(None, lambda: get_broker().consume("outbound-web", on_msg))
    yield
    tarefa.cancel()


app = FastAPI(title="Mora — canais (perfil local)", lifespan=lifespan)

# O site (5173) e o painel (5174) chamam este serviço (8001) de outra origem — sem isto, o navegador
# aceita a resposta do servidor mas BLOQUEIA a leitura no JS (erro de CORS), e o widget nunca chega a
# abrir o WebSocket: fica preso tentando de novo, sempre "sem conexão". Mesma config da `api`.
_origens = [o.strip() for o in (get_settings().cors_origins or "").split(",") if o.strip()] or ["*"]
app.add_middleware(CORSMiddleware, allow_origins=_origens, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health(response: Response):
    """Só responde 200 se o barramento estiver de pé (ADR-0011).

    O canal sem Redis aceita conexão de WebSocket e some com a mensagem: o cliente digita e nada
    acontece. Devolver 200 nessa situação é pior que devolver erro."""
    problemas: list[str] = []
    try:
        get_broker().ping()
    except Exception as e:
        problemas.append(f"barramento: {type(e).__name__}")
    if problemas:
        response.status_code = 503
    return {"ok": not problemas, "problemas": problemas,
            "conexoes": sum(len(v) for k, v in conexoes.items() if k != "dashboard"),
            "dashboards": len(conexoes["dashboard"])}


@app.post("/sessao")
def abrir_sessao():
    """O widget pede a sessão aqui. O id é emitido pelo servidor e vem assinado — assim ninguém
    entra na conversa de outro visitante só por saber (ou chutar) o id dele."""
    return emitir()


@app.api_route("/webhook", methods=["GET", "POST"])
async def webhook(req: Request):
    """Reaproveita o handler Lambda traduzindo Request → evento API Gateway v2."""
    event = {"requestContext": {"http": {"method": req.method}}, "queryStringParameters": dict(req.query_params),
             "headers": dict(req.headers), "body": (await req.body()).decode()}
    r = wa_handler(event, None)
    return Response(content=r.get("body", ""), status_code=r["statusCode"])


# `papel` é uma lista fechada: qualquer outro valor cai fora em vez de escorregar para o ramo
# `else` e virar uma conexão de painel sem credencial nenhuma.
PAPEIS = {"lead", "dashboard"}


@app.websocket("/ws")
async def ws(sock: WebSocket, papel: str = "lead", id: str = "", token: str = ""):
    if papel not in PAPEIS:
        await sock.close(code=4400)            # papel desconhecido: não existe conexão "genérica"
        return
    if papel == "lead" and not validar(id, token):
        await sock.close(code=4401)            # sessão não emitida por nós, ou expirada
        return
    # O painel recebe o espelho de TODAS as conversas (ver `on_msg` no lifespan): exige credencial
    # da equipe, senão qualquer um na rede abriria `?papel=dashboard` e leria os leads inteiros.
    if papel == "dashboard" and not painel.valido(token):
        await sock.close(code=4403)
        return
    await sock.accept()
    chave = id if papel == "lead" else "dashboard"
    conexoes.setdefault(chave, set()).add(sock)
    if papel == "lead":
        await _entregar_pendentes(sock, chave)
    try:
        while True:
            body = json.loads(await sock.receive_text())
            # Só a conexão de um lead escreve, e só pela sessão dela. O painel é somente-leitura
            # aqui (fala com o cliente pelo /handoff da API, que é auditado); sem esta guarda, uma
            # conexão de painel poderia publicar mensagens no nome de qualquer lead.
            if papel != "lead" or body.get("session_id") != id:
                continue
            meta = body.get("meta", {}) or {}
            texto = body["texto"]
            botao = bool(meta.pop("botao", False)) or texto.startswith("slot:")
            msg = MensagemNormalizada(lead_id=f"web_{body['session_id']}", canal=Canal.WEB,
                                      identificador_canal=body["session_id"], conteudo=texto, meta=meta,
                                      tipo=TipoMensagem.BOTAO if botao else TipoMensagem.TEXTO)
            try:
                get_broker().publish("inbound", msg.model_dump_json(), key=msg.lead_id)
                # Confirma o recebimento na hora: o widget mostra "digitando" só depois disto.
                await sock.send_text(json.dumps({"evento": "recebido", "ref": body.get("ref")}))
            except Exception:
                log.exception("falha ao enfileirar mensagem da sessão %s", body.get("session_id"))
                await sock.send_text(json.dumps({"evento": "falha_envio", "ref": body.get("ref"),
                                                 "texto": "Não consegui registrar sua mensagem. Pode tentar de novo?"}))
    except WebSocketDisconnect:
        for s in conexoes.values():
            s.discard(sock)


async def _entregar_pendentes(sock: WebSocket, chave: str) -> None:
    """Respostas que chegaram com o cliente offline (refresh, queda de rede) são entregues ao reconectar."""
    fila = pendentes.get(chave)
    if not fila:
        return
    agora = time.time()
    while fila:
        em, resposta = fila.popleft()
        if agora - em <= JANELA_PENDENTE_S:
            await sock.send_text(json.dumps(resposta))


async def _push(alvos: set[WebSocket], data: dict):
    for s in list(alvos):
        try:
            await s.send_text(json.dumps(data))
        except Exception:
            alvos.discard(s)


