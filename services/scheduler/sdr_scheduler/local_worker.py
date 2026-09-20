"""Worker de follow-up: polling a cada 30 s na tabela followups_agendados.

O mesmo laço carrega mais duas coisas que já cabiam no intervalo: a amostragem de saúde (ADR-0011)
e a reindexação do acervo do CRM. Nenhuma das duas justificaria um processo próprio, e as três
acordam no mesmo ritmo.
"""
import logging
import os
import time

from sdr_shared.db import amostrar, iniciar_batimento
from sdr_shared.log import configurar as configurar_log
from sdr_shared.ports import get_broker, get_scheduler

log = logging.getLogger("scheduler")

TOPICOS = ("inbound", "outbound-web", "outbound-telegram", "resumir")

# De quanto em quanto tempo o acervo do CRM volta para o índice. 0 desliga.
#
# Por que existe: preço e status são do CRM, e o agente busca no índice da Mora. Sem isto, o que o
# corretor marcou como vendido continua sendo oferecido até alguém rodar `make seed` — e é
# justamente isso que a ligação com o CRM existe para impedir. Quinze minutos é curto o bastante
# para não constranger numa demonstração e longo o bastante para não pesar: a passada é
# incremental e só gera embedding do que mudou de texto.
INTERVALO_ACERVO_S = int(os.getenv("SDR_ACERVO_REFRESH_S", "900"))


def _intervalo_acervo() -> int:
    """Lido a cada ciclo, não uma vez no import: mudar no painel precisa valer sem reiniciar o
    worker. O painel manda, o `.env` é o piso, e `0` desliga de verdade — diferente de vazio, que
    significa 'não opinei'."""
    try:
        from sdr_shared.db import operacao_numero
        v = operacao_numero("acervo_refresh_s")
        return int(v) if v is not None else INTERVALO_ACERVO_S
    except Exception:
        return INTERVALO_ACERVO_S
ACERVO = os.getenv("SDR_ACERVO_ARQUIVO", "/app/data/imoveis/imoveis.json")


def _sincronizar_acervo() -> None:
    """Best-effort. Uma falha aqui não pode derrubar o follow-up, que é o trabalho principal."""
    try:
        from sdr_ingestion.sincronia import sincronizar
        r = sincronizar(ACERVO)
        if r.get("ignorado"):
            return                       # sem CRM configurado: o arquivo manda e não há o que buscar
        if r["novos"] or r["mudados"] or r["saidos"]:
            log.info("acervo reindexado", extra={"acervo": r})
    except Exception:
        log.warning("reindexação do acervo falhou; o índice continua como estava", exc_info=True)


def main():
    configurar_log("scheduler")
    sch, broker = get_scheduler(), get_broker()
    iniciar_batimento("scheduler")
    proxima_sincronia = 0.0
    while True:
        for lead_id, payload in sch.vencidos():
            broker.publish("inbound", payload, key=lead_id)
        filas = broker.profundidade(list(TOPICOS)) if hasattr(broker, "profundidade") else {}
        amostrar(filas)
        intervalo = _intervalo_acervo()
        if intervalo and time.monotonic() >= proxima_sincronia:
            _sincronizar_acervo()
            proxima_sincronia = time.monotonic() + intervalo
        time.sleep(30)


if __name__ == "__main__":
    main()
