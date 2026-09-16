"""Perfil local: substitui EventBridge Scheduler. Polling a cada 30 s na tabela followups_agendados.

O mesmo laço carrega a amostragem de saúde (ADR-0011): já acorda de 30 em 30 segundos, então não
custa nada e evita subir um processo só para observar.
"""
import time

from sdr_shared.db import amostrar, iniciar_batimento
from sdr_shared.log import configurar as configurar_log
from sdr_shared.ports import get_broker, get_scheduler

TOPICOS = ("inbound", "outbound-web", "outbound-telegram", "resumir")


def main():
    configurar_log("scheduler")
    sch, broker = get_scheduler(), get_broker()
    iniciar_batimento("scheduler")
    while True:
        for lead_id, payload in sch.vencidos():
            broker.publish("inbound", payload, key=lead_id)
        filas = broker.profundidade(list(TOPICOS)) if hasattr(broker, "profundidade") else {}
        amostrar(filas)
        time.sleep(30)


if __name__ == "__main__":
    main()
