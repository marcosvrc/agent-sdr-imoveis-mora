from sdr_shared.models import CartaoQualificacao, Intencao


def test_cartao_compra_faltantes():
    c = CartaoQualificacao(intencao=Intencao.COMPRA, regiao="zona_sul")
    assert c.campos_faltantes() == ["preco_max", "quartos", "urgencia"]


def test_cartao_investimento_completo():
    c = CartaoQualificacao(intencao=Intencao.INVESTIMENTO, perfil_investidor="moderado",
                           ticket=500_000, retorno_esperado="0.6% a.m.")
    assert c.completo()


# --------------------------------------------------------- a rota que ficava grudada

def _estado(texto: str, lead, **extra):
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
    entrada = MensagemNormalizada(lead_id=lead.id, canal=Canal.TELEGRAM, tipo=TipoMensagem.TEXTO,
                                  identificador_canal="123", conteudo=texto)
    return {"lead": lead, "entrada": entrada, "messages": [], "saltos": 0, **extra}


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


def test_modelo_nao_devolve_visita_reservada_ao_agendador(monkeypatch):
    """As regras determinísticas já decidiram que a mensagem não pede visita, e a visita deste lead
    já está reservada. Se o modelo de roteamento mandar para o agendador mesmo assim, o cliente —
    que só quis mudar de bairro — recebe a grade de horários de novo."""
    from agent.nodes import supervisor

    class Falso:
        def invoke(self, _):
            return type("M", (), {"content": "agendador"})()

    monkeypatch.setattr(supervisor, "llm_roteamento", lambda: Falso())
    lead = _lead_com_visita_reservada()
    lead.cartao.pediu_visita = False          # força a decisão a cair no modelo
    destino = supervisor.run(_estado("prefiro na Vila Madalena", lead))["proximo"]
    assert destino != "agendador"


def test_especialista_que_nao_responde_nem_reencaminha_roda_uma_vez_so(infra, monkeypatch):
    """Nó sem `resposta` e sem mudar `proximo` voltava a rodar até MAX_SALTOS: três execuções do
    mesmo nó para o mesmo silêncio. Hoje é leitura de banco; com um LLM no caminho triplicaria o
    custo do turno."""
    import agent.nodes.reativador as reativador
    from agent.handler import processar
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
    execucoes = []
    monkeypatch.setattr(reativador, "run", lambda state: execucoes.append(1) or {})
    processar(MensagemNormalizada(lead_id="l-rep", canal=Canal.TELEGRAM, identificador_canal="5511999990000",
                                  tipo=TipoMensagem.REATIVACAO, conteudo="reativar"))
    assert len(execucoes) == 1, execucoes


def test_extracao_recebe_a_ultima_pergunta_da_mora(monkeypatch):
    """Resposta curta só tem sentido junto da pergunta: a extração precisa recebê-la.

    "1" depois de "quantos quartos?" é o caso que deixou um lead pendurado — o cartão não fechava,
    o consultor não rodava, e a Mora tinha acabado de prometer que ia buscar.
    """
    from agent.nodes import qualificador

    visto = {}

    class ModeloFalso:
        def with_structured_output(self, _schema):
            return self
        def invoke(self, prompt):
            visto["prompt"] = str(prompt)
            return CartaoQualificacao(quartos=1)

    monkeypatch.setattr(qualificador, "llm_roteamento", lambda: ModeloFalso())
    cartao = qualificador._extrair(CartaoQualificacao(), "1", "Quantos quartos você precisa?")
    assert cartao.quartos == 1
    assert "Quantos quartos você precisa?" in visto["prompt"], "a pergunta tem de ir no prompt"
    assert "CONTEXTO, não é dado do cliente" in visto["prompt"], (
        "sem essa marcação o modelo extrai os bairros que a própria Mora citou como exemplo")


def test_ultima_pergunta_ignora_o_que_o_cliente_disse():
    """A última fala da MORA, não a última mensagem. O histórico chega com a do cliente no fim."""
    from agent.nodes.qualificador import ultima_pergunta
    from langchain_core.messages import AIMessage, HumanMessage

    assert ultima_pergunta([]) == ""
    assert ultima_pergunta([HumanMessage(content="oi")]) == ""
    historico = [HumanMessage(content="quero alugar"), AIMessage(content="Em qual região?"),
                 HumanMessage(content="Tucuruvi")]
    assert ultima_pergunta(historico) == "Em qual região?"
    assert ultima_pergunta([("ai", "Quantos quartos?"), ("user", "1")]) == "Quantos quartos?"


def test_erro_de_digitacao_nao_manda_o_cliente_para_um_humano(monkeypatch):
    """Relato do cliente: digitou "dim" (por "sim") logo depois de reservar a visita, o roteador
    leu como assunto fora de imóveis e encaminhou ao corretor. A Mora silenciou; ele escreveu
    "não entendi, pode falar mais sobre o imóvel?" e não recebeu resposta de ninguém.

    Handoff é caro e, para quem está do outro lado, sem volta. Ruído de três palavras não é
    reclamação nem pedido de atendente.
    """
    from agent.nodes import supervisor

    class Falso:
        def invoke(self, _):
            return type("M", (), {"content": "handoff"})()

    monkeypatch.setattr(supervisor, "llm_roteamento", lambda: Falso())
    lead = _lead_com_visita_reservada()
    lead.cartao.pediu_visita = False                   # força a decisão a cair no modelo
    for ruido in ("dim", "ok", "???", "aa bb cc"):
        destino = supervisor.run(_estado(ruido, lead, imoveis_sugeridos=["SP-0001"]))["proximo"]
        assert destino != "handoff", f"{ruido!r} não é pedido de atendimento humano"


def test_quem_pede_uma_pessoa_continua_chegando_ao_handoff(monkeypatch):
    """A correção não pode fechar a porta: pedir gente é legítimo, e curto."""
    from agent.nodes import supervisor

    class Falso:
        def invoke(self, _):
            return type("M", (), {"content": "handoff"})()

    monkeypatch.setattr(supervisor, "llm_roteamento", lambda: Falso())
    lead = _lead_com_visita_reservada()
    lead.cartao.pediu_visita = False
    for pedido in ("quero um corretor", "Falar com corretor", "me passa um humano"):
        assert supervisor.run(_estado(pedido, lead))["proximo"] == "handoff"
    # Frase longa de reclamação continua sob a alçada do modelo: o guarda só vale para ruído curto.
    longo = "isso aqui não está me ajudando em nada, estou perdendo meu tempo com esse atendimento"
    assert supervisor.run(_estado(longo, lead, imoveis_sugeridos=["SP-0001"]))["proximo"] == "handoff"
