from datetime import datetime, timedelta, timezone
import logging

from sdr_shared.db import VisitaRepository, auditar, notificar, InteresseRepository
from sdr_shared.models import Visita

log = logging.getLogger("agent.agenda")

DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def formatar(dt: datetime) -> str:
    local = dt.astimezone(timezone(timedelta(hours=-3)))
    return f"{DIAS[local.weekday()]} {local:%d/%m} às {local:%Hh}"


def listar_horarios(dias: int = 5, corretor_id: str | None = None) -> list[datetime]:
    """Com corretor definido, a grade já vem descontada da agenda real dele."""
    return VisitaRepository().horarios_disponiveis(dias, corretor_id)


class HorarioOcupado(Exception):
    """Entre a oferta e o clique, alguém pegou o horário. Quem chama reoferece."""


def agendar(lead_id: str, imovel_id: str | None, inicio: datetime, tipo: str = "visita",
            corretor_id: str | None = None, titulo: str = "", local: str = "",
            email_cliente: str | None = None) -> Visita:
    repo = VisitaRepository()
    # A checagem na oferta não basta: dois clientes podem estar olhando a mesma lista agora.
    if not repo.slot_livre(inicio, corretor_id):
        raise HorarioOcupado(inicio.isoformat())

    v = Visita(id=f"vis_{lead_id}_{int(inicio.timestamp())}", lead_id=lead_id, imovel_id=imovel_id, tipo=tipo, inicio=inicio, corretor_id=corretor_id)
    visita = repo.agendar(v)
    if imovel_id:
        # Visita é o interesse mais forte que existe; sobrescreve qualquer situação anterior.
        InteresseRepository().registrar(lead_id, imovel_id, situacao="visita_marcada", origem="agente")
    _registrar_no_calendario(v, titulo, local, email_cliente)
    auditar(acao="visita.agendada", entidade="visita", entidade_id=v.id, ator_tipo="agente", ator_nome="Mora",
            dados={"lead_id": lead_id, "imovel_id": imovel_id, "tipo": tipo,
                   "inicio": inicio.isoformat(), "corretor_id": corretor_id})
    notificar(tipo="visita.agendada", corretor_id=corretor_id, lead_id=lead_id,
              titulo=f"Visita marcada para {formatar(inicio)}",
              detalhe=(f"Imóvel {imovel_id}. " if imovel_id else "") + "Confirme com o cliente antes do dia.",
              dados={"visita_id": v.id, "inicio": inicio.isoformat(), "imovel_id": imovel_id},
              chave=v.id)
    return visita


def _registrar_no_calendario(v: Visita, titulo: str, local: str, email_cliente: str | None) -> None:
    """Escreve na agenda do corretor, quando ele conectou uma.

    Se o Google falhar, a visita continua marcada: o cliente não pode perder o compromisso porque
    um token expirou. O painel mostra a visita do mesmo jeito — só não haverá evento lá fora.
    """
    if not v.corretor_id:
        return
    try:
        from sdr_shared.ports import get_calendario
        cal = get_calendario()
        if not cal.conectado(v.corretor_id):
            return
        evento = cal.criar_evento(
            v.corretor_id, titulo=titulo or "Visita — Vértice Imóveis", inicio=v.inicio, duracao_min=60,
            descricao="Visita agendada pela Mora. Confirme com o cliente antes do dia.",
            local=local, convidados=[email_cliente] if email_cliente else [])
        if evento:
            VisitaRepository().marcar_evento_externo(v.id, evento)
    except Exception:
        log.exception("visita %s marcada, mas não foi para o calendário do corretor", v.id)
