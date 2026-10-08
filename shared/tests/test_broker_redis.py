"""Broker Redis contra um servidor de verdade (sobe um `redis-server` descartável).

O laço principal lê com `>` — "o que nunca foi entregue". Mensagem entregue a um worker que caiu
antes do XACK fica na PEL e, sem retomada, nunca mais é lida: o cliente que escreveu no instante da
queda fica sem resposta e a fila "atrasa" para sempre em `profundidade()`."""
import shutil
import socket
import subprocess
import time

import pytest

redis = pytest.importorskip("redis")
pytestmark = pytest.mark.skipif(not shutil.which("redis-server"), reason="sem redis-server")


@pytest.fixture
def servidor(monkeypatch):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); porta = s.getsockname()[1]
    proc = subprocess.Popen(["redis-server", "--port", str(porta), "--save", "", "--appendonly", "no"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"redis://127.0.0.1:{porta}/0"
    for _ in range(50):
        try:
            redis.Redis.from_url(url).ping(); break
        except Exception:
            time.sleep(0.1)
    monkeypatch.setenv("SDR_REDIS_URL", url)
    from sdr_shared.config import get_settings
    get_settings.cache_clear()
    yield url
    proc.kill(); proc.wait()
    get_settings.cache_clear()


def _consumir_um_ciclo(broker, topico, handler):
    """`consume` é infinito; interrompe depois da retomada + um XREADGROUP vazio."""
    original = broker._r.xreadgroup
    vezes = {"n": 0}

    def limitado(group, consumer, streams, **kw):
        if ">" in streams.values():
            vezes["n"] += 1
            if vezes["n"] > 1:
                raise KeyboardInterrupt
            kw["block"] = 50
        return original(group, consumer, streams, **kw)
    broker._r.xreadgroup = limitado
    try:
        broker.consume(topico, handler)
    except KeyboardInterrupt:
        pass


def test_mensagem_pendente_de_um_worker_que_caiu_e_retomada_no_boot(servidor):
    from sdr_shared.adapters.local.broker import RedisBroker
    b = RedisBroker()
    b.publish("t1", '{"x": 1}', key="lead-a")
    b.publish("t1", '{"x": 2}', key="lead-b")
    # Simula o worker anterior: entregou as duas para "w1" e morreu antes do XACK.
    b._ensure_group("sdr:t1", "t1-workers")
    entregues = b._r.xreadgroup("t1-workers", "w1", {"sdr:t1": ">"}, count=10)
    assert sum(len(m) for _, m in entregues) == 2
    assert b.profundidade(["t1"])["t1"] == 2, "pendentes contam como atraso"

    processadas = []
    _consumir_um_ciclo(RedisBroker(), "t1", processadas.append)
    assert processadas == ['{"x": 1}', '{"x": 2}'], "as duas foram retomadas, na ordem"
    assert b.profundidade(["t1"])["t1"] == 0, "e confirmadas"


def test_pendente_de_outro_consumidor_so_e_tomada_depois_de_um_turno_inteiro(servidor, monkeypatch):
    """Worker antigo com outro nome: o que está parado há menos que um turno pode estar EM CURSO
    (processar de novo seria resposta dupla); o que passou disso está morto e é retomado."""
    from sdr_shared.adapters.local import broker as mod
    b = mod.RedisBroker()
    b.publish("t2", "antiga", key="lead-a")
    b._ensure_group("sdr:t2", "t2-workers")
    b._r.xreadgroup("t2-workers", "worker-antigo", {"sdr:t2": ">"}, count=10)

    processadas = []
    monkeypatch.setattr(mod, "_lock_s", lambda: 3600.0)          # turno "longo": ainda pode estar em curso
    _consumir_um_ciclo(mod.RedisBroker(), "t2", processadas.append)
    assert processadas == []

    monkeypatch.setattr(mod, "_lock_s", lambda: 0.0)             # já passou o prazo: está morta
    _consumir_um_ciclo(mod.RedisBroker(), "t2", processadas.append)
    assert processadas == ["antiga"]
    assert b.profundidade(["t2"])["t2"] == 0


def test_lock_curto_e_renovado_cobre_o_turno_longo_e_some_quando_o_worker_morre(servidor, monkeypatch):
    """Validade do pior caso do turno inteiro (até ~48 min) sobrevivia ao worker que morria no meio:
    ao voltar, a retomada esperava o lock órfão vencer e a fila parava. Agora é curto e renovado
    enquanto o turno roda — cobre o turno longo e, sem renovação, vence sozinho."""
    from sdr_shared.adapters.local import broker as mod
    monkeypatch.setattr(mod, "LOCK_S", 0.6)
    b = mod.RedisBroker()
    b.publish("t3", "corpo", key="lead-lento")
    visto = {}

    def turno_lento(_body):
        time.sleep(1.5)                                    # mais que duas validades do lock
        visto["lock_vivo"] = b._r.exists("sdr:lock:lead-lento") == 1
    _consumir_um_ciclo(b, "t3", turno_lento)
    assert visto["lock_vivo"], "o lock foi renovado enquanto o turno rodava"
    assert b._r.exists("sdr:lock:lead-lento") == 0, "liberado no fim do turno"

    orfao = b._r.lock("sdr:lock:orfao", timeout=mod.LOCK_S)  # worker que morreu: ninguém renova
    orfao.acquire()
    time.sleep(1.0)
    assert b._r.exists("sdr:lock:orfao") == 0, "lock órfão vence sozinho em LOCK_S"


def test_lock_por_lead_cobre_todas_as_chamadas_de_modelo_do_turno():
    """O lock durava o pior caso de UMA chamada de modelo, mas o turno faz até quatro (rota,
    extração, conversa e a extração do consultor). Vencido no meio, a mensagem seguinte do mesmo
    lead entrava em paralelo."""
    from sdr_shared.ports.factory import CHAMADAS_POR_TURNO, MAX_RETRIES, orcamento_do_turno_s
    from sdr_shared.config import get_settings
    uma_chamada = get_settings().llm_timeout_s * (1 + MAX_RETRIES) * 2
    assert CHAMADAS_POR_TURNO >= 4
    assert orcamento_do_turno_s() >= uma_chamada * 4
