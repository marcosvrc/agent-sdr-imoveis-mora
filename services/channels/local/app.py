"""Canal web do perfil local. Um processo FastAPI com:
  WS  /ws            → widget do site (papel=lead) e dashboard (papel=dashboard; credencial no 1º quadro)
  worker de saída    → consome outbound-web do Redis e faz push nas conexões abertas

Havia aqui um `/webhook` que reaproveitava o adaptador do WhatsApp para simular a entrega da Meta.
Saiu com o WhatsApp: o Telegram tem canal próprio (`services/channels/telegram`), e um endpoint que
traduzia Request em evento de API Gateway não servia a mais ninguém."""
import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Response
from fastapi.middleware.cors import CORSMiddleware

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


# `papel` é uma lista fechada: qualquer outro valor cai fora em vez de escorregar para o ramo
# `else` e virar uma conexão de painel sem credencial nenhuma.
PAPEIS = {"lead", "dashboard"}


PRAZO_CREDENCIAL_S = 5


@app.websocket("/ws")
async def ws(sock: WebSocket, papel: str = "lead", id: str = "", token: str = ""):
    if papel not in PAPEIS:
        await sock.close(code=4400)            # papel desconhecido: não existe conexão "genérica"
        return
    if papel == "lead" and not validar(id, token):
        await sock.close(code=4401)            # sessão não emitida por nós, ou expirada
        return
    await sock.accept()
    # O painel recebe o espelho de TODAS as conversas (ver `on_msg` no lifespan): exige credencial
    # da equipe, senão qualquer um na rede abriria `?papel=dashboard` e leria os leads inteiros.
    # A credencial vem no PRIMEIRO quadro, nunca na URL: query string fica em log de proxy, no
    # histórico do navegador e no Referer — e este token é o da equipe inteira, de longa duração.
    # Nada é entregue antes de ela ser conferida.
    if papel == "dashboard" and not await _credencial_do_painel(sock):
        await sock.close(code=4403)
        return
    chave = id if papel == "lead" else "dashboard"
    conexoes.setdefault(chave, set()).add(sock)
    try:
        if papel == "lead":
            await _entregar_pendentes(sock, chave)
        else:
            await sock.send_text(json.dumps({"evento": "pronto"}))
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
        pass
    except Exception:
        # Quadro malformado (JSON inválido, sem `texto`) derruba SÓ esta conexão, com log. Antes,
        # a exceção escapava e o socket ficava registrado em `conexoes` para sempre: cada envio
        # seguinte a esse lead tentava escrever num socket morto.
        log.exception("conexão %s encerrada por quadro inválido", chave)
        await sock.close(code=1003)            # 1003 = "dado que não aceito"; fecha de verdade
    finally:
        # Sempre sai do registro, seja qual for o motivo da saída. Um socket morto em `conexoes`
        # é vazamento e é `_push` falhando em série a cada resposta da Mora.
        for s in conexoes.values():
            s.discard(sock)


async def _credencial_do_painel(sock: WebSocket) -> bool:
    """Primeiro quadro do painel: `{"token": "..."}`. Qualquer outra coisa, ou silêncio por
    `PRAZO_CREDENCIAL_S`, é recusa — a conexão não fica pendurada esperando."""
    try:
        bruto = await asyncio.wait_for(sock.receive_text(), timeout=PRAZO_CREDENCIAL_S)
        corpo = json.loads(bruto)
    except (TimeoutError, WebSocketDisconnect, ValueError):
        return False
    credencial = corpo.get("token") if isinstance(corpo, dict) else None
    return isinstance(credencial, str) and painel.valido(credencial)


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


