from sdr_shared.models import CartaoQualificacao, Intencao


def test_cartao_compra_faltantes():
    c = CartaoQualificacao(intencao=Intencao.COMPRA, regiao="zona_sul")
    assert c.campos_faltantes() == ["preco_max", "quartos", "urgencia"]


def test_cartao_investimento_completo():
    c = CartaoQualificacao(intencao=Intencao.INVESTIMENTO, perfil_investidor="moderado",
                           ticket=500_000, retorno_esperado="0.6% a.m.")
    assert c.completo()


# --------------------------------------------------------- a rota que ficava grudada

def _estado(texto: str, lead):
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
    entrada = MensagemNormalizada(lead_id=lead.id, canal=Canal.TELEGRAM, tipo=TipoMensagem.TEXTO,
                                  identificador_canal="123", conteudo=texto)
    return {"lead": lead, "entrada": entrada, "messages": [], "saltos": 0}


def _lead_com_visita_reservada():
    from sdr_shared.models import Estagio, Lead
    lead = Lead(id="lead-rota", nome="Marcos", estagio=Estagio.AGENDADO)
    lead.cartao.intencao = Intencao.ALUGUEL
    lead.cartao.regiao = "zona_oeste"
    lead.cartao.preco_max = 3500
    lead.cartao.quartos = 2
    lead.cartao.urgencia = "30 dias"
    lead.cartao.pediu_visita = True          # fica ligado para sempre, por desenho
    return lead


def test_telefone_depois_da_reserva_nao_volta_para_o_agendador():
    """Relato do cliente: a Mora reservou a visita, pediu o telefone, ele mandou o telefone — e
    recebeu a grade de horários de novo, sobre uma visita que já estava reservada.

    A causa é `pediu_visita`, que liga no primeiro pedido e nunca desliga. Ele é o que faz o
    agendador retomar de onde parou, mas depois da reserva vira rota grudada: TODA mensagem
    seguinte cai nele.
    """
    from agent.nodes import supervisor
    destino = supervisor.run(_estado("012 88888-3703", _lead_com_visita_reservada()))["proximo"]
    assert destino != "agendador", "telefone não é pedido de remarcação"


def test_quem_quer_remarcar_continua_chegando_ao_agendador():
    """A correção não pode fechar a porta: remarcar é legítimo e o cliente diz isso com todas as
    letras."""
    from agent.nodes import supervisor
    lead = _lead_com_visita_reservada()
    assert supervisor.run(_estado("preciso remarcar a visita", lead))["proximo"] == "agendador"
    assert supervisor.run(_estado("Agendar visita", lead))["proximo"] == "agendador"
