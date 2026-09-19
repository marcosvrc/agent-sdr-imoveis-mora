"""Saída do agente: entrega ao canal (tópico outbound-<canal>), agenda follow-up, publica evento de estágio.
Usa só as portas do shared — não conhece qual adaptador está por trás."""
import json
import logging

from sdr_shared import followup as politica_followup
from sdr_shared.ports import get_broker, get_scheduler
from sdr_shared.messaging import RespostaAgente, MensagemNormalizada, Canal, TipoMensagem
from sdr_shared.models import Lead, Estagio

log = logging.getLogger("agent.dispatch")
ENCERRADOS = (Estagio.HANDOFF, Estagio.FRIO, Estagio.AGENDADO)


def despachar(canal: Canal, identificador: str, resposta: RespostaAgente) -> None:
    get_broker().publish(f"outbound-{canal}", json.dumps(
        {"identificador": identificador, "resposta": resposta.model_dump(mode="json")}), key=resposta.lead_id)


def publicar_eventos(lead: Lead, estagio_antes: Estagio) -> None:
    if lead.estagio != estagio_antes:
        get_broker().publish("events", json.dumps({"tipo": "lead.stage_changed", "lead_id": lead.id,
                                                   "de": estagio_antes, "para": lead.estagio}), key=lead.id)
        if lead.estagio in ENCERRADOS:
            get_scheduler().cancel(lead.id)
        if lead.estagio in (Estagio.QUALIFICADO, Estagio.AGENDADO, Estagio.HANDOFF):   # briefing + análise para o corretor
            from sdr_shared.db import LeadRepository
            LeadRepository().marcar_analise_pedida(lead.id)
            get_broker().publish("resumir", json.dumps({"lead_id": lead.id}), key=lead.id)


def cancelar_followup(lead_id: str) -> None:
    """O cliente está falando agora: nada de o agente cutucar por cima."""
    get_scheduler().cancel(lead_id)


def reagendar_followup(lead: Lead, canal: Canal, identificador: str) -> None:
    """Quando (e se) a Mora volta a chamar este lead. A cadência vem do painel; ver sdr_shared.followup."""
    if lead.estagio in ENCERRADOS:
        get_scheduler().cancel(lead.id)          # nada pendente para quem já saiu do fluxo do agente
        return
    minutos = politica_followup.calcular(lead.followups_enviados, str(lead.temperatura))
    if minutos is None:                          # acabaram as tentativas, ou o follow-up está desligado
        get_scheduler().cancel(lead.id)
        return
    payload = MensagemNormalizada(lead_id=lead.id, canal=canal, identificador_canal=identificador,
                                  tipo=TipoMensagem.FOLLOWUP, conteudo="").model_dump_json()
    get_scheduler().schedule(lead.id, minutos, payload)
    log.info("follow-up %d do lead %s em %d min (temperatura=%s)",
             lead.followups_enviados + 1, lead.id, minutos, lead.temperatura)
