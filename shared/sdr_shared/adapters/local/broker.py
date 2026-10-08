"""Redis Streams: um stream por tópico, consumer group por serviço. Ordem por lead garantida
porque cada worker processa sequencialmente e o lock por key evita concorrência entre workers."""
import logging
import threading
import time

import redis
from redis.exceptions import LockError

from ...config import get_settings

log = logging.getLogger(__name__)

BLOCK_MS = 5_000                    # quanto o XREADGROUP espera por mensagem no servidor
SOCKET_TIMEOUT_S = BLOCK_MS / 1000 + 10  # SEMPRE maior que o block, senão o cliente estoura antes do servidor responder
ESPERA_RETOMADA_S = 2               # com mensagem pendente por falta de barramento, quanto esperar antes de retomar
# Validade do lock por lead, RENOVADA enquanto o turno roda (`_manter_lock`). Um lock com a validade do
# pior caso do turno inteiro (750 s com timeout de 45 s; ~48 min com 180 s pelo painel) protegia o
# turno, mas sobrevivia ao worker que morria no meio: ao voltar, a retomada esperava o lock órfão
# vencer, e a fila inteira ficava parada. Curto e renovado, ele cobre o turno longo e some em um
# minuto quando o processo morre.
LOCK_S = 60


def _lock_s() -> float:
    """Validade do lock por lead. Era 180 s fixos, escolhidos à mão, enquanto o pior caso de um
    turno era 270 s: o lock expirava com o turno em curso e a mensagem seguinte do mesmo lead
    entrava em paralelo. Agora deriva do orçamento do turno, do mesmo lugar que define os retries."""
    from sdr_shared.ports.factory import orcamento_do_turno_s
    try:
        return orcamento_do_turno_s()
    except Exception:
        return 240.0


def _manter_lock(trava) -> threading.Event:
    """Renova o lock a cada terço da validade enquanto o turno roda; devolve o sinal de parar."""
    parar = threading.Event()

    def renovar():
        while not parar.wait(LOCK_S / 3):
            try:
                trava.reacquire()
            except Exception:
                log.warning("não consegui renovar o lock do turno; ele vence sozinho", exc_info=True)
                return

    threading.Thread(target=renovar, daemon=True, name="renova-lock").start()
    return parar


class RedisBroker:
    def __init__(self):
        self._r = redis.Redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_timeout=SOCKET_TIMEOUT_S,
            socket_connect_timeout=5,
            health_check_interval=30,
        )

    def publish(self, topic: str, body: str, key: str) -> None:
        self._r.xadd(f"sdr:{topic}", {"key": key, "body": body}, maxlen=10_000)

    def ping(self) -> None:
        """Levanta exceção se o Redis não responder — usado pelo /health do canal."""
        self._r.ping()

    def profundidade(self, topicos: list[str]) -> dict[str, int]:
        """Quantas mensagens estão esperando por tópico — o sinal de "worker parado ou atrasado".

        Soma o `lag` (entradas que o grupo nunca recebeu) com o `pending` (entregues e não
        confirmadas). XLEN não serve: conta o histórico retido pelo maxlen, não a espera.
        """
        saida = {}
        for t in topicos:
            stream, group = f"sdr:{t}", f"{t}-workers"
            try:
                grupos = self._r.xinfo_groups(stream)
            except Exception:
                continue                       # stream ainda não existe: nada esperando
            g = next((g for g in grupos if g.get("name") == group), None)
            if g:
                saida[t] = int(g.get("lag") or 0) + int(g.get("pending") or 0)
        return saida

    def consume(self, topic: str, handler, ao_falhar=None) -> None:
        """`ao_falhar(body, erro)` é chamado quando o handler estoura — é onde o serviço avisa o cliente
        em vez de deixá-lo esperando. Sem ele, a mensagem é apenas registrada e confirmada."""
        stream, group, consumer = f"sdr:{topic}", f"{topic}-workers", "w1"
        self._ensure_group(stream, group)
        log.info("consumindo %s (grupo %s)", stream, group)
        pendentes = not self._retomar_pendentes(stream, group, consumer, handler, ao_falhar)
        while True:
            if pendentes:
                # O laço lê só `>`: a mensagem que ficou pendente por falta de barramento só seria
                # relida no próximo boot. Espera um pouco e retoma a PEL daqui mesmo, até esvaziar.
                time.sleep(ESPERA_RETOMADA_S)
                pendentes = not self._retomar_pendentes(stream, group, consumer, handler, ao_falhar)
            try:
                lidos = self._r.xreadgroup(group, consumer, {stream: ">"}, count=1, block=BLOCK_MS) or []
            except (redis.TimeoutError, redis.ConnectionError) as e:
                # Fila vazia + timeout de rede, ou Redis reiniciando: espera e tenta de novo, sem derrubar o worker
                log.warning("redis indisponível em %s (%s); tentando de novo em 2s", stream, type(e).__name__)
                time.sleep(2)
                self._ensure_group(stream, group)
                continue
            for _, msgs in lidos:
                for mid, data in msgs:
                    pendentes |= not self._processar(stream, group, mid, data, handler, ao_falhar)

    def _processar(self, stream, group, mid, data, handler, ao_falhar) -> bool:
        """Processa uma mensagem. Devolve False quando ela ficou PENDENTE (o turno não começou por
        falta de barramento) — quem chama tenta retomá-la depois; nos outros casos ela é confirmada.

        A linha que separa os casos é o INÍCIO do turno. Sem barramento antes de começar (lock que
        não se obtém, `BarramentoIndisponivel` do agente), a mensagem fica para depois. Depois que o
        turno começou, reprocessar repetiria tudo — a entrada gravada duas vezes, a resposta enviada
        duas vezes, o CRM publicado duas vezes —, então um erro de Redis no meio do turno é
        registrado e a mensagem é confirmada, sem `ao_falhar` (que mandaria o cliente ao corretor
        por um problema de infraestrutura)."""
        from sdr_shared.ports.broker import BarramentoIndisponivel
        try:
            # thread_local=False: a renovação roda em outra thread, e o token do lock padrão do
            # redis-py é por thread — a renovação não o enxergava e o lock vencia no meio do turno.
            trava = self._r.lock(f"sdr:lock:{data['key']}", timeout=LOCK_S, thread_local=False)
            trava.acquire()
        except (redis.ConnectionError, redis.TimeoutError):
            log.warning("barramento indisponível em %s; %s fica pendente para ser retomada", stream, mid)
            return False
        parar = _manter_lock(trava)
        try:
            handler(data["body"])
        except BarramentoIndisponivel:
            # O agente conferiu o barramento ANTES de começar o turno e não encontrou: nada foi
            # feito ainda, e a mensagem fica na PEL para ser retomada.
            log.warning("barramento indisponível em %s; %s fica pendente para ser retomada", stream, mid)
            parar.set()
            self._liberar(trava, mid, stream)
            return False
        except (redis.ConnectionError, redis.TimeoutError):
            log.warning("redis caiu no meio do turno de %s em %s; confirmo para não repetir o turno",
                        mid, stream, exc_info=True)
        except Exception as e:
            log.exception("falha processando %s em %s", mid, stream)
            if ao_falhar:
                try:
                    ao_falhar(data["body"], e)      # avisa o cliente; sem isto ele espera para sempre
                except Exception:
                    log.exception("falha também no tratamento de erro de %s", mid)
        parar.set()
        self._liberar(trava, mid, stream)
        try:
            self._r.xack(stream, group, mid)        # confirma: reprocessar repetiria o turno
        except (redis.ConnectionError, redis.TimeoutError):
            log.warning("não consegui confirmar %s em %s; fica pendente", mid, stream)
            return False
        return True

    @staticmethod
    def _liberar(trava, mid, stream) -> None:
        """Liberar o lock é arrumação, não atendimento. Com `with`, o `LockNotOwnedError` de um lock
        que venceu durante o turno saía do `__exit__` como se o TURNO tivesse falhado: o cliente já
        tinha a resposta e recebia em seguida "tive um problema técnico", e o lead ia para o
        corretor sem ter pedido. O turno terminou; registra e segue."""
        try:
            trava.release()
        except LockError:
            log.warning("lock do lead venceu durante o turno de %s em %s (turno concluído)", mid, stream)
        except (redis.ConnectionError, redis.TimeoutError):
            log.warning("não consegui liberar o lock de %s em %s (redis fora); ele vence sozinho", mid, stream)

    def _retomar_pendentes(self, stream, group, consumer, handler, ao_falhar) -> bool:
        """Mensagem entregue e não confirmada quando o worker caiu fica na PEL do grupo — e o laço
        principal lê só com `>`, que é "o que nunca foi entregue". Sem isto, a mensagem de um
        cliente que chegou no instante da queda ficava pendente para sempre, contando em
        `profundidade()` como atraso e sem resposta nenhuma.

        Duas passadas: a PEL deste consumidor (id `0`: tudo que era meu), e depois o que estiver
        parado há mais que um turno inteiro em nome de qualquer outro consumidor (XAUTOCLAIM), que
        é o caso de um worker antigo que morreu com nome diferente.

        Devolve False se alguma continuou pendente (barramento ainda fora)."""
        retomadas, tudo_feito = 0, True
        try:
            for _, msgs in self._r.xreadgroup(group, consumer, {stream: "0"}, count=100) or []:
                for mid, data in msgs:
                    tudo_feito &= self._processar(stream, group, mid, data, handler, ao_falhar)
                    retomadas += 1
            inicio = "0-0"
            while True:
                proximo, msgs, *_ = self._r.xautoclaim(stream, group, consumer, min_idle_time=int(_lock_s() * 1000),
                                                       start_id=inicio, count=100)
                for mid, data in msgs:
                    if data is None:            # entrada apagada do stream (maxlen): só sobra o id na PEL
                        self._r.xack(stream, group, mid)
                        continue
                    tudo_feito &= self._processar(stream, group, mid, data, handler, ao_falhar)
                    retomadas += 1
                if proximo in ("0-0", "0") or not msgs:
                    break
                inicio = proximo
        except (redis.TimeoutError, redis.ConnectionError) as e:
            log.warning("não consegui retomar pendentes de %s (%s); sigo com a fila nova", stream, type(e).__name__)
            tudo_feito = False
        if retomadas:
            log.info("%d mensagem(ns) pendente(s) retomada(s) em %s", retomadas, stream)
        return tudo_feito

    def _ensure_group(self, stream: str, group: str) -> None:
        try:
            self._r.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.ResponseError:
            pass                                    # BUSYGROUP: já existe
        except (redis.TimeoutError, redis.ConnectionError):
            pass                                    # tratado no loop de consumo
