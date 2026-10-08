"""Canal web do perfil local. Um processo FastAPI com:
  WS  /ws            → widget do site (papel=lead) e dashboard (papel=dashboard); nos dois a credencial
                       vai no 1º quadro, nunca na URL
  worker de saída    → consome outbound-web do Redis e faz push nas conexões abertas

Havia aqui um `/webhook` que reaproveitava o adaptador do WhatsApp para simular a entrega da Meta.
Saiu com o WhatsApp: o Telegram tem canal próprio (`services/channels/telegram`), e um endpoint que
traduzia Request em evento de API Gateway não servia a mais ninguém."""
import asyncio
import json
import logging
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
from sdr_shared.seguranca.cors import origens as _origens_cors  # noqa: E402
app.add_middleware(CORSMiddleware, allow_origins=_origens_cors(), allow_methods=["*"], allow_headers=["*"])


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


class JanelaDeslizante:
    """Conta eventos por chave numa janela de tempo e recusa o que passar de `maximo`.

    Fica na MEMÓRIA DO PROCESSO: com mais de um processo (workers do uvicorn, réplicas) cada um
    conta sozinho, e o teto efetivo vira `maximo × processos`; reiniciar zera a conta. No perfil
    local é um processo só. Ao escalar o canal, mover a contagem para o Redis (INCR + EXPIRE).
    """

    def __init__(self, maximo: int, janela_s: float):
        self.maximo, self.janela_s = maximo, janela_s
        self._marcas: dict[str, deque] = {}

    def permite(self, chave: str) -> bool:
        agora = time.monotonic()
        if len(self._marcas) > 10_000:          # não cresce sem fim com IPs/sessões que já foram embora
            self._marcas = {k: d for k, d in self._marcas.items() if d and agora - d[-1] <= self.janela_s}
        marcas = self._marcas.setdefault(chave, deque())
        while marcas and agora - marcas[0] > self.janela_s:
            marcas.popleft()
        if len(marcas) >= self.maximo:
            return False
        marcas.append(agora)
        return True

    def limpar(self) -> None:
        self._marcas.clear()


# Tetos de gasto: cada mensagem aceita é um turno de LLM pago. Um script abria sessão nova a cada
# 5 mensagens — sem limite por IP, trocar de sessão zerava qualquer conta por sessão.
# Folgados para gente de verdade: um visitante abre 1 sessão por aba e escreve bem menos de 1 msg
# a cada 4 s; um escritório inteiro atrás do mesmo IP (NAT) ainda cabe nos tetos por IP.
LIMITE_SESSOES = JanelaDeslizante(20, 3600)       # POST /sessao por IP
LIMITE_MSG_SESSAO = JanelaDeslizante(15, 60)      # mensagens por sessão
LIMITE_MSG_IP = JanelaDeslizante(200, 3600)       # mensagens por IP, somando todas as sessões


def zerar_limites() -> None:
    for limite in (LIMITE_SESSOES, LIMITE_MSG_SESSAO, LIMITE_MSG_IP):
        limite.limpar()


def _ip(origem: Request | WebSocket) -> str:
    """IP de quem chama. Atrás de proxy, o uvicorn precisa de `--proxy-headers` e
    `--forwarded-allow-ips` — senão todo mundo vira o IP do proxy e divide o mesmo teto."""
    return origem.client.host if origem.client else "?"


@app.post("/sessao")
def abrir_sessao(request: Request, response: Response):
    """O widget pede a sessão aqui. O id é emitido pelo servidor e vem assinado — assim ninguém
    entra na conversa de outro visitante só por saber (ou chutar) o id dele."""
    if not LIMITE_SESSOES.permite(_ip(request)):
        response.status_code = 429
        response.headers["Retry-After"] = str(int(LIMITE_SESSOES.janela_s))
        return {"erro": "muitas sessões abertas deste endereço; tente mais tarde"}
    return emitir()


class PedidoHistorico(BaseModel):
    session_id: str
    token: str


HISTORICO_MAX = 60


@app.post("/historico")
def historico(pedido: PedidoHistorico, response: Response):
    """A conversa desta sessão, para o widget redesenhar depois de recarregar a página.

    A sessão sobrevive ao recarregar (fica na aba), mas as bolhas não: o cliente via só a saudação
    e a Mora continuava de onde parou — falando de imóveis e horários que tinham sumido da tela.
    POST com o token no corpo, e não na URL, pelo mesmo motivo do WebSocket: URL vai para log e
    histórico do navegador. Sessão inválida não lê nada.
    """
    if not validar(pedido.session_id, pedido.token):
        response.status_code = 401
        return {"mensagens": []}
    from sdr_shared.db import MensagemRepository
    linhas = MensagemRepository().historico(f"web_{pedido.session_id}", limite=HISTORICO_MAX)
    quem = {"in": "lead", "out": "Mora", "corretor": "corretor"}
    return {"mensagens": [
        {"de": quem[m["direcao"]], "texto": m["conteudo"], "em": m["em"].isoformat(),
         "opcoes": (m.get("meta") or {}).get("opcoes") or [] if m["direcao"] == "out" else [],
         "imoveis": (m.get("meta") or {}).get("imoveis") or [] if m["direcao"] == "out" else []}
        for m in linhas if m["direcao"] in quem and m["canal"] == "web"]}


# `papel` é uma lista fechada: qualquer outro valor cai fora em vez de escorregar para o ramo
# `else` e virar uma conexão de painel sem credencial nenhuma.
PAPEIS = {"lead", "dashboard"}


PRAZO_CREDENCIAL_S = 5

# Tamanho máximo de um quadro. O campo do site corta em 1000 caracteres (LIMITE_TEXTO no
# ChatWidget); 1000 caracteres em UTF-8 + session_id + meta + ref cabem com folga em 8 KiB.
# Acima disso não é gente digitando — e cada byte de texto vira token de LLM pago.
MAX_QUADRO_BYTES = 8 * 1024
LIMITE_TEXTO = 1000

# O que o site manda em `meta` (ChatWidget.enviar). Nada além disso chega ao agente: antes ia o
# `meta` inteiro, e `nome`/`telefone` forjados no navegador viravam dado do lead (handler.py usa
# os dois no upsert). `botao` não passa adiante: vira o `tipo` da mensagem.
# Mesmo formato de id de imóvel de services/api/src/api/routers/eventos.py (ID_IMOVEL): o valor
# entra no contexto do agente, então é id, não texto livre.
ID_IMOVEL = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _meta_do_site(bruto: object) -> tuple[dict, bool]:
    """Filtra o `meta` vindo do navegador. Devolve (meta para o agente, é clique de botão)."""
    if not isinstance(bruto, dict):
        return {}, False
    meta: dict = {}
    origem = bruto.get("imovel_origem")
    if isinstance(origem, str) and ID_IMOVEL.fullmatch(origem):
        meta["imovel_origem"] = origem
    if bruto.get("saudacao_exibida") is True:
        meta["saudacao_exibida"] = True
    return meta, bruto.get("botao") is True


class QuadroGrandeDemais(Exception):
    pass


async def _receber(sock: WebSocket) -> str:
    bruto = await sock.receive_text()
    if len(bruto.encode()) > MAX_QUADRO_BYTES:
        raise QuadroGrandeDemais
    return bruto


async def _recusar_envio(sock: WebSocket, ref: object, texto: str) -> None:
    """Recusa com aviso, nunca em silêncio: o widget troca o "digitando" por "Tentar de novo"."""
    await sock.send_text(json.dumps({"evento": "falha_envio", "ref": ref, "texto": texto}))


@app.websocket("/ws")
async def ws(sock: WebSocket, papel: str = "lead"):
    if papel not in PAPEIS:
        await sock.close(code=4400)            # papel desconhecido: não existe conexão "genérica"
        return
    await sock.accept()
    # A credencial vem no PRIMEIRO quadro, nunca na URL: query string fica em log de proxy, no
    # histórico do navegador e no Referer. Nada é entregue antes de ela ser conferida.
    # O painel recebe o espelho de TODAS as conversas (ver `on_msg` no lifespan): exige o token da
    # equipe, senão qualquer um na rede abriria `?papel=dashboard` e leria os leads inteiros.
    if papel == "dashboard":
        if not await _credencial_do_painel(sock):
            await sock.close(code=4403)
            return
        chave = "dashboard"
    else:
        # O widget manda `{session_id, token}`. A recusa (sessão inventada ou expirada) é 4401
        # DEPOIS do aceite: fechar antes do aceite chega ao navegador como 1006, e o widget não
        # saberia que precisa descartar a sessão e pedir outra — ficava "reconectando…" para sempre.
        sid = await _credencial_do_lead(sock)
        if not sid:
            await sock.close(code=4401)
            return
        chave = sid
    conexoes.setdefault(chave, set()).add(sock)
    ip = _ip(sock)
    try:
        await sock.send_text(json.dumps({"evento": "pronto"}))
        if papel == "lead":
            await _entregar_pendentes(sock, chave)
        while True:
            body = json.loads(await _receber(sock))
            # O painel é somente-leitura aqui (fala com o cliente pelo /handoff da API, que é
            # auditado); sem esta guarda, poderia publicar mensagens no nome de qualquer lead.
            if papel != "lead":
                continue
            if not isinstance(body, dict) or not isinstance(body.get("texto"), str) or not body["texto"].strip():
                raise ValueError("quadro sem texto")
            ref = body.get("ref")
            # Só pela sessão que esta conexão autenticou. Avisa em vez de ignorar: antes, uma
            # mensagem da fila offline com `session_id` vazio sumia sem resposta nenhuma.
            if body.get("session_id") != chave:
                await _recusar_envio(sock, ref, "Sua conversa foi renovada. Pode mandar a mensagem de novo?")
                continue
            texto = body["texto"]
            if len(texto) > LIMITE_TEXTO:
                await _recusar_envio(sock, ref, f"Sua mensagem passou de {LIMITE_TEXTO} caracteres. Pode resumir?")
                continue
            # As duas contas andam juntas: a da sessão segura a rajada; a do IP pega o script que
            # troca de sessão para zerar a da sessão.
            if not (LIMITE_MSG_SESSAO.permite(chave) and LIMITE_MSG_IP.permite(ip)):
                log.warning("limite de mensagens atingido (sessão %s, ip %s)", chave, ip)
                await _recusar_envio(sock, ref, "Recebi muitas mensagens em pouco tempo. Aguarde um instante e tente de novo.")
                continue
            meta, botao = _meta_do_site(body.get("meta"))
            botao = botao or texto.startswith("slot:")
            msg = MensagemNormalizada(lead_id=f"web_{chave}", canal=Canal.WEB,
                                      identificador_canal=chave, conteudo=texto, meta=meta,
                                      tipo=TipoMensagem.BOTAO if botao else TipoMensagem.TEXTO)
            try:
                get_broker().publish("inbound", msg.model_dump_json(), key=msg.lead_id)
                # Confirma o recebimento na hora: o widget mostra "digitando" só depois disto.
                await sock.send_text(json.dumps({"evento": "recebido", "ref": body.get("ref")}))
            except Exception:
                log.exception("falha ao enfileirar mensagem da sessão %s", chave)
                await _recusar_envio(sock, ref, "Não consegui registrar sua mensagem. Pode tentar de novo?")
    except WebSocketDisconnect:
        pass
    except QuadroGrandeDemais:
        log.warning("conexão %s encerrada: quadro acima de %d bytes", chave, MAX_QUADRO_BYTES)
        await sock.close(code=1009)            # 1009 = "mensagem grande demais"
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


async def _primeiro_quadro(sock: WebSocket) -> dict | None:
    """Primeiro quadro como objeto JSON, ou None se vier outra coisa, grande demais, ou nada
    dentro de `PRAZO_CREDENCIAL_S` — a conexão não fica pendurada esperando."""
    try:
        corpo = json.loads(await asyncio.wait_for(_receber(sock), timeout=PRAZO_CREDENCIAL_S))
    except (TimeoutError, WebSocketDisconnect, ValueError, QuadroGrandeDemais):
        return None
    return corpo if isinstance(corpo, dict) else None


async def _credencial_do_lead(sock: WebSocket) -> str | None:
    """Primeiro quadro do widget: `{"session_id": "...", "token": "..."}`. Devolve o id se a
    sessão foi emitida por nós e ainda vale."""
    corpo = await _primeiro_quadro(sock) or {}
    sid, token = corpo.get("session_id"), corpo.get("token")
    if isinstance(sid, str) and isinstance(token, str) and validar(sid, token):
        return sid
    return None


async def _credencial_do_painel(sock: WebSocket) -> bool:
    """Primeiro quadro do painel: `{"token": "..."}`. Qualquer outra coisa, ou silêncio por
    `PRAZO_CREDENCIAL_S`, é recusa — a conexão não fica pendurada esperando."""
    credencial = (await _primeiro_quadro(sock) or {}).get("token")
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


