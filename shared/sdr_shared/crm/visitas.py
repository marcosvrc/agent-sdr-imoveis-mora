"""Agenda e pedido de visita no CRM.

A distinção que este módulo existe para preservar: **a Mora pede, o corretor confirma.** A
ferramenta do CRM diz isso na própria descrição, e é uma regra de negócio, não uma formalidade —
o CRM não pode afirmar "visita marcada" porque um agente achou que marcou. Quem aparece no imóvel
no sábado é uma pessoa.

Mas o cliente também não pode ouvir "vou ver e te aviso" e ficar sem nada: nesse meio-tempo outro
cliente pegaria o mesmo horário. Então a Mora **reserva** o horário na agenda dela e **pede** a
visita no CRM, e diz exatamente isso ao cliente — reservado, o corretor confirma. As duas metades
são verdadeiras ao mesmo tempo, e é a única combinação em que ninguém é enganado: nem o cliente,
que sabe que falta um passo, nem o corretor, cujo painel não diz "agendado" por conta do agente.

A disponibilidade tem duas fontes, e a escolha é por competência: **com imóvel definido, quem sabe
é o CRM**, porque horário de visita a um imóvel é dado comercial da imobiliária. Sem imóvel
escolhido ainda — ou sem CRM — vale a agenda do corretor, que é o que a Mora sempre soube fazer.
"""
import logging
from dataclasses import dataclass
from datetime import datetime

from ..models import Lead
from ..ports import get_crm
from . import traducao, vinculo

log = logging.getLogger("crm.visitas")


@dataclass(frozen=True)
class Horario:
    """Um horário oferecível. `slot_id` só existe quando veio do CRM — e é o que permite pedir a
    visita depois. Sem ele, a reserva é só da Mora."""
    inicio: datetime
    slot_id: str | None = None


def horarios_do_imovel(codigo_imovel: str | None, limite: int = 8) -> list[Horario]:
    """Horários livres daquele imóvel no CRM, ou lista vazia.

    Vazia significa "não sei", e quem chama deve cair na agenda do corretor. Nunca significa "não
    há": afirmar indisponibilidade a partir de uma falha de integração faria a Mora recusar uma
    visita que existe.
    """
    if not codigo_imovel:
        return []
    crm = get_crm()
    if not crm.habilitado():
        return []
    try:
        with crm.sessao() as s:
            imovel = s.imovel_por_codigo(codigo_imovel)
            if not imovel:
                return []
            livres = s.horarios_livres(str(imovel["id"]), limite=limite)
    except Exception:
        log.warning("não consegui ler os horários de %s no CRM", codigo_imovel, exc_info=True)
        return []

    saida = []
    for x in livres:
        quando = x.get("starts_at")
        if not quando:
            continue
        try:
            saida.append(Horario(inicio=datetime.fromisoformat(str(quando)),
                                 slot_id=str(x["id"])))
        except (ValueError, KeyError):
            continue
    return saida


def pedir_visita(lead: Lead, codigo_imovel: str | None, slot_id: str | None,
                 observacao: str | None = None) -> bool:
    """Registra no CRM o PEDIDO de visita. Devolve se o pedido entrou.

    `False` não desfaz a reserva que a Mora já fez: o cliente tem o horário, e o corretor recebe a
    notificação da Mora de qualquer jeito. O que se perde é o pedido aparecer no painel do CRM —
    ruim, mas muito menos ruim que derrubar o atendimento por causa disso.
    """
    if not (codigo_imovel and slot_id):
        return False
    crm = get_crm()
    if not crm.habilitado():
        return False
    v = vinculo.buscar(lead.id)
    if v is None:
        return False            # sem oportunidade no CRM não há a que pendurar o pedido
    try:
        with crm.sessao() as s:
            imovel = s.imovel_por_codigo(codigo_imovel)
            if not imovel:
                return False
            # O CRM exige oportunidade qualificada para aceitar pedido de visita, e o publicador só
            # move o estágio no FIM do turno — depois daqui. Sem este passo, o primeiro pedido de
            # todo lead seria recusado por uma questão de ordem, e voltaria a funcionar
            # "sozinho" no turno seguinte: o tipo de intermitência que ninguém liga à causa.
            nova = s.mover_estagio(v.crm_opportunity_id, destino=traducao.ESTAGIO_QUALIFICADO,
                                   versao=v.crm_version)
            if nova:
                vinculo.atualizar_versao(lead.id, nova)
            pedido = s.solicitar_visita(crm_opportunity_id=v.crm_opportunity_id,
                                        crm_property_id=str(imovel["id"]), slot_id=slot_id,
                                        observacao=observacao)
    except Exception:
        log.warning("não consegui registrar o pedido de visita do lead %s", lead.id, exc_info=True)
        return False
    return pedido is not None
