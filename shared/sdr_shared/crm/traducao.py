"""Tradução do vocabulário da Mora para o do CRM.

Os dois sistemas modelam a mesma realidade com palavras diferentes, e a tradução tem duas
armadilhas que valem estar escritas:

1. **`Lead` da Mora é uma oportunidade, não uma pessoa.** No CRM, `Lead` é a pessoa e `Opportunity`
   é a intenção. Então um lead da Mora vira DOIS registros lá. Ignorar isso faria o mesmo cliente
   com duas intenções (comprar e alugar) virar dois cadastros, com o histórico partido ao meio.

2. **`agendado` não se traduz.** O CRM só aceita `visit_scheduled` com visita confirmada por uma
   pessoa, e o agente não confirma visita. Então `agendado` na Mora vira `qualified` no CRM, e o
   estágio avança lá quando o corretor confirmar. É uma divergência de propósito: o CRM não pode
   dizer "visita marcada" porque o agente achou que marcou.
"""
from ..models import Estagio, Intencao, Lead

# Investimento é compra: o CRM tem duas finalidades, e o que distingue o investidor é o cartão de
# preferências — não um terceiro propósito que o catálogo não saberia filtrar.
PROPOSITO = {
    Intencao.ALUGUEL: "rent",
    Intencao.COMPRA: "buy",
    Intencao.INVESTIMENTO: "buy",
}

# O agente só move até `qualified` (seção 6 da especificação do CRM). Estágios que não estão aqui
# significam "não mexer": `handoff` é tratado pelo encaminhamento, e `inativo`/`frio` seriam `lost`,
# que é decisão humana.
ESTAGIO = {
    Estagio.NOVO: "new",
    Estagio.QUALIFICANDO: "in_service",
    Estagio.QUALIFICADO: "qualified",
    Estagio.AGENDADO: "qualified",
}


def proposito(lead: Lead) -> str | None:
    """`None` enquanto a intenção não estiver clara: abrir uma oportunidade de compra para quem
    ainda não disse o que quer é inventar informação comercial."""
    return PROPOSITO.get(lead.cartao.intencao)


def reais_para_centavos(valor: float | None) -> int | None:
    """A Mora guarda reais em float; o CRM, centavos inteiros. `round` e não `int`: truncar faria
    R$ 3.000,00 virar R$ 2.999,99 quando o float chegasse como 2999.9999999996."""
    if valor is None:
        return None
    return max(0, round(float(valor) * 100))


def preferencias(lead: Lead) -> dict:
    """O cartão inteiro, sempre. `PUT /preferences` é substituição: mandar só o que mudou apagaria
    o resto — e mandar tudo é o que permite uma exigência retirada pelo cliente realmente sumir."""
    c = lead.cartao
    aluguel = c.intencao == Intencao.ALUGUEL
    return {
        "city": c.regiao,
        "neighborhoods": list(c.bairros or []),
        "property_types": [c.tipo_imovel] if c.tipo_imovel else [],
        "budget_min_cents": reais_para_centavos(c.preco_min),
        # Investidor informa `ticket` em vez de faixa de preço; sem isto, a oportunidade dele
        # ficaria eternamente sem teto e nunca poderia ser qualificada.
        "budget_max_cents": reais_para_centavos(c.preco_max if c.preco_max is not None else c.ticket),
        # `monthly_total` só existe em aluguel, e é a base certa lá: o cliente de aluguel fala em
        # "3 mil com tudo", não no valor do aluguel isolado.
        "budget_basis": "monthly_total" if aluguel else "base_price",
        "bedrooms_min": c.quartos,
        "requirements": [x for x in [c.urgencia and f"urgência: {c.urgencia}",
                                     c.perfil_investidor and f"perfil: {c.perfil_investidor}",
                                     c.retorno_esperado and f"retorno esperado: {c.retorno_esperado}"]
                         if x],
    }


def identificadores(lead: Lead) -> dict:
    """`external_contact_id` é sempre preenchido: o lead da Mora pode não ter e-mail nem telefone
    (chat do site é anônimo), e sem nenhum identificador o CRM recusa a criação — com razão."""
    return {
        "name": lead.nome or lead.cartao.nome_informado or f"Contato {lead.id[:8]}",
        "source": "mora_agent",
        "email": lead.email or lead.cartao.email_informado,
        "phone": lead.telefone or lead.cartao.telefone_informado,
        "external_contact_id": f"mora-{lead.id}",
    }
