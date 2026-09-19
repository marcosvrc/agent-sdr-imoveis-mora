"""Quais imóveis o cliente viu, quais gostou e quais recusou — no CRM.

É o que dá ao corretor o essencial antes de ligar: não "este cliente procura dois quartos em
Pinheiros", e sim "a Mora mostrou estes três, ele descartou aquele e pediu visita neste". Sem isso,
o corretor recomeça a conversa do início e reoferece o que a pessoa já recusou, que é exatamente o
que faz um atendimento parecer que ninguém leu nada.

Duas coisas que o módulo protege:

1. **Descarte é ato explícito.** Pedir mais opções não é recusar as anteriores. `sugerido` vira
   `presented`, e só um descarte de verdade vira `rejected` — marcar como recusado o que o cliente
   apenas ainda não escolheu tiraria do corretor um imóvel que continua valendo.

2. **A versão é encadeada.** Cada registro incrementa a versão da oportunidade, então publicar três
   imóveis com a MESMA versão faria o segundo e o terceiro baterem em 412. A versão devolvida
   alimenta a chamada seguinte, e o que sobra no fim é guardado no vínculo.
"""
import logging

from ..models import Lead
from ..ports import get_crm
from . import vinculo

log = logging.getLogger("crm.interesses")

# Vocabulário da Mora → vocabulário do CRM. `visita_marcada` vira `interested`: pedir visita é o
# sinal de interesse mais forte que existe, e o CRM registra a visita em si à parte.
SITUACAO = {
    "sugerido": "presented",
    "interessado": "interested",
    "descartado": "rejected",
    "visita_marcada": "interested",
}


def publicar_interesses(lead: Lead, itens: list[tuple[str, str]],
                        motivos: dict[str, str] | None = None) -> int:
    """Publica `(codigo_do_imovel, situacao_da_mora)`. Devolve quantos entraram.

    Nunca levanta: um interesse que não subiu é uma linha a menos na ficha do corretor, não um
    atendimento interrompido.
    """
    try:
        return _publicar(lead, itens, motivos or {})
    except Exception:
        log.warning("falha ao publicar interesses do lead %s", lead.id, exc_info=True)
        return 0


def _publicar(lead: Lead, itens: list[tuple[str, str]], motivos: dict[str, str]) -> int:
    crm = get_crm()
    if not (itens and crm.habilitado()):
        return 0
    v = vinculo.buscar(lead.id)
    if v is None:
        return 0            # sem oportunidade no CRM não há a que pendurar o interesse

    versao, entraram = v.crm_version, 0
    with crm.sessao() as s:
        for codigo, situacao in itens:
            alvo = SITUACAO.get(situacao)
            if not alvo:
                continue
            imovel = s.imovel_por_codigo(codigo)
            if not imovel:
                # Imóvel da vitrine que o CRM não conhece. Acontece enquanto os dois acervos não
                # estiverem sincronizados; não é motivo para parar os outros.
                log.debug("imóvel %s não existe no CRM; segui em frente", codigo)
                continue
            nova = s.registrar_interesse(crm_opportunity_id=v.crm_opportunity_id,
                                         crm_property_id=str(imovel["id"]), situacao=alvo,
                                         versao=versao, motivo=motivos.get(codigo))
            if nova is None:
                continue
            versao, entraram = nova, entraram + 1

    if versao != v.crm_version:
        vinculo.atualizar_versao(lead.id, versao)
    return entraram
