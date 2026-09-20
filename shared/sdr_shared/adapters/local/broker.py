"""Redis Streams: um stream por tópico, consumer group por serviço. Ordem por lead garantida
porque cada worker processa sequencialmente e o lock por key evita concorrência entre workers."""
import logging
import time

import redis

from ...config import get_settings

log = logging.getLogger(__name__)

BLOCK_MS = 5_000                    # quanto o XREADGROUP espera por mensagem no servidor
SOCKET_TIMEOUT_S = BLOCK_MS / 1000 + 10  # SEMPRE maior que o block, senão o cliente estoura antes do servidor responder


def _lock_s() -> float:
    """Validade do lock por lead. Era 180 s fixos, escolhidos à mão, enquanto o pior caso de um
    turno era 270 s: o lock expirava com o turno em curso e a mensagem seguinte do mesmo lead
    entrava em paralelo. Agora deriva do orçamento do turno, do mesmo lugar que define os retries."""
    from sdr_shared.ports.factory import orcamento_do_turno_s
    try:
        return orcamento_do_turno_s()
    except Exception:
        return 240.0


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
        self._retomar_pendentes(stream, group, consumer, handler, ao_falhar)
        while True:
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
                    self._processar(stream, group, mid, data, handler, ao_falhar)

    def _processar(self, stream, group, mid, data, handler, ao_falhar) -> None:
        try:
            with self._r.lock(f"sdr:lock:{data['key']}", timeout=_lock_s()):
                handler(data["body"])
        except Exception as e:
            log.exception("falha processando %s em %s", mid, stream)
            if ao_falhar:
                try:
                    ao_falhar(data["body"], e)      # avisa o cliente; sem isto ele espera para sempre
                except Exception:
                    log.exception("falha também no tratamento de erro de %s", mid)
        self._r.xack(stream, group, mid)            # sempre confirma: reprocessar repetiria o erro

    def _retomar_pendentes(self, stream, group, consumer, handler, ao_falhar) -> None:
        """Mensagem entregue e não confirmada quando o worker caiu fica na PEL do grupo — e o laço
        principal lê só com `>`, que é "o que nunca foi entregue". Sem isto, a mensagem de um
        cliente que chegou no instante da queda ficava pendente para sempre, contando em
        `profundidade()` como atraso e sem resposta nenhuma.

        Duas passadas: a PEL deste consumidor (id `0`: tudo que era meu), e depois o que estiver
        parado há mais que um turno inteiro em nome de qualquer outro consumidor (XAUTOCLAIM), que
        é o caso de um worker antigo que morreu com nome diferente."""
        retomadas = 0
        try:
            for _, msgs in self._r.xreadgroup(group, consumer, {stream: "0"}, count=100) or []:
                for mid, data in msgs:
                    self._processar(stream, group, mid, data, handler, ao_falhar)
                    retomadas += 1
            inicio = "0-0"
            while True:
                proximo, msgs, *_ = self._r.xautoclaim(stream, group, consumer, min_idle_time=int(_lock_s() * 1000),
                                                       start_id=inicio, count=100)
                for mid, data in msgs:
                    if data is None:            # entrada apagada do stream (maxlen): só sobra o id na PEL
                        self._r.xack(stream, group, mid)
                        continue
                    self._processar(stream, group, mid, data, handler, ao_falhar)
                    retomadas += 1
                if proximo in ("0-0", "0") or not msgs:
                    break
                inicio = proximo
        except (redis.TimeoutError, redis.ConnectionError) as e:
            log.warning("não consegui retomar pendentes de %s (%s); sigo com a fila nova", stream, type(e).__name__)
        if retomadas:
            log.info("%d mensagem(ns) pendente(s) retomada(s) em %s", retomadas, stream)

    def _ensure_group(self, stream: str, group: str) -> None:
        try:
            self._r.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.ResponseError:
            pass                                    # BUSYGROUP: já existe
        except (redis.TimeoutError, redis.ConnectionError):
            pass                                    # tratado no loop de consumo
