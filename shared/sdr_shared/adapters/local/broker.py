"""Redis Streams: um stream por tópico, consumer group por serviço. Ordem por lead garantida
porque cada worker processa sequencialmente e o lock por key evita concorrência entre workers."""
import logging
import time

import redis

from ...config import get_settings

log = logging.getLogger(__name__)

BLOCK_MS = 5_000                    # quanto o XREADGROUP espera por mensagem no servidor
SOCKET_TIMEOUT_S = BLOCK_MS / 1000 + 10  # SEMPRE maior que o block, senão o cliente estoura antes do servidor responder


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
                    try:
                        with self._r.lock(f"sdr:lock:{data['key']}", timeout=180):
                            handler(data["body"])
                    except Exception as e:
                        log.exception("falha processando %s em %s", mid, stream)
                        if ao_falhar:
                            try:
                                ao_falhar(data["body"], e)      # avisa o cliente; sem isto ele espera para sempre
                            except Exception:
                                log.exception("falha também no tratamento de erro de %s", mid)
                    self._r.xack(stream, group, mid)            # sempre confirma: reprocessar repetiria o erro

    def _ensure_group(self, stream: str, group: str) -> None:
        try:
            self._r.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.ResponseError:
            pass                                    # BUSYGROUP: já existe
        except (redis.TimeoutError, redis.ConnectionError):
            pass                                    # tratado no loop de consumo
