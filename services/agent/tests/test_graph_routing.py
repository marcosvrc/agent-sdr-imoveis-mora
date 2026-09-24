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


# ------------------------------------------- o cartão que só sabia escrever, nunca apagar

def _extracao_devolvendo(monkeypatch, saida):
    """Troca o modelo de extração por um que devolve exatamente `saida`."""
    from agent.nodes import qualificador

    class ModeloFalso:
        def with_structured_output(self, _schema):
            return self

        def invoke(self, _prompt):
            return saida

    monkeypatch.setattr(qualificador, "llm_roteamento", lambda: ModeloFalso())
    return qualificador


def test_extracao_guarda_requisito_nas_palavras_do_cliente(monkeypatch):
    """"Precisa aceitar pet" não cabe em nenhum campo — e antes disto morria no histórico."""
    from agent.nodes.qualificador import Extracao

    q = _extracao_devolvendo(monkeypatch, Extracao(requisitos=["aceita pet", "não quero térreo"]))
    cartao = q._extrair(CartaoQualificacao(bairros=["Moema"]), "tenho um cachorro, e nada de térreo")
    assert cartao.requisitos == ["aceita pet", "não quero térreo"]
    assert cartao.bairros == ["Moema"], "requisito não mexe no resto do cartão"


def test_requisito_entra_na_consulta_da_busca():
    """O requisito precisa influenciar o ranking em TODO turno, não só naquele em que foi dito."""
    from agent.tools.buscar_imoveis import _consulta

    cartao = CartaoQualificacao(intencao=Intencao.ALUGUEL, bairros=["Brooklin"],
                                requisitos=["aceita pet"])
    assert "aceita pet" in _consulta(cartao, preferencia="e aí, tem novidade?", local=None)


def test_studio_com_zero_quartos_sobrevive_ao_merge(monkeypatch):
    """`quartos = 0` é studio, não campo vazio. O filtro antigo descartava e a Mora perguntava de novo."""
    from agent.nodes.qualificador import Extracao

    q = _extracao_devolvendo(monkeypatch, Extracao(quartos=0, tipo_imovel="studio"))
    cartao = q._extrair(CartaoQualificacao(), "quero um studio")
    assert cartao.quartos == 0
    assert cartao.completo() is False or cartao.quartos == 0


def test_preco_zero_continua_sendo_descartado(monkeypatch):
    """Zero vale para quartos; para preço é erro de extração, e apagaria o orçamento real."""
    from agent.nodes.qualificador import Extracao

    q = _extracao_devolvendo(monkeypatch, Extracao(preco_max=0))
    cartao = q._extrair(CartaoQualificacao(preco_max=800_000), "sei lá")
    assert cartao.preco_max == 800_000


def test_cliente_pode_desfazer_um_criterio(monkeypatch):
    """"Tanto faz o bairro agora" tem de apagar o bairro — antes o valor antigo guiava toda busca."""
    from agent.nodes.qualificador import Extracao

    q = _extracao_devolvendo(monkeypatch, Extracao(limpar=["bairros", "preco_max", "pediu_visita"]))
    antes = CartaoQualificacao(bairros=["Moema"], preco_max=800_000, pediu_visita=True,
                               intencao=Intencao.COMPRA, quartos=2)
    cartao = q._extrair(antes, "tanto faz o bairro, e esquece o teto; a visita fica pra depois")
    assert cartao.bairros == []
    assert cartao.preco_max is None
    assert cartao.pediu_visita is False
    assert cartao.quartos == 2, "limpar só apaga o que o cliente retirou"
    assert cartao.intencao == Intencao.COMPRA


def test_limpar_nao_apaga_intencao_nem_contato(monkeypatch):
    """Sem intenção não há rota, e telefone não se retira por engano de extração."""
    from agent.nodes.qualificador import Extracao

    q = _extracao_devolvendo(monkeypatch, Extracao(limpar=["intencao", "telefone_informado", "xpto"]))
    antes = CartaoQualificacao(intencao=Intencao.ALUGUEL, telefone_informado="11978654432")
    cartao = q._extrair(antes, "deixa pra lá")
    assert cartao.intencao == Intencao.ALUGUEL
    assert cartao.telefone_informado == "11978654432"


def test_bairro_novo_substitui_a_lista(monkeypatch):
    """A lista devolvida é a que vale: acumular ou trocar é decisão da extração, não do merge."""
    from agent.nodes.qualificador import Extracao

    q = _extracao_devolvendo(monkeypatch, Extracao(bairros=["Moema", "Pinheiros"]))
    cartao = q._extrair(CartaoQualificacao(bairros=["Moema"]), "também quero ver Pinheiros")
    assert cartao.bairros == ["Moema", "Pinheiros"]


# --------------------------------------- o motivo do card era a descrição do anunciante

def test_linha_do_consultor_leva_fatos_e_motivo():
    """O modelo precisava de um diferencial e recebia um pedaço de anúncio. Agora recebe fatos."""
    from agent.nodes.consultor import _linha
    from sdr_shared.models import ImovelCard

    card = ImovelCard(id="SP-0007", titulo="Apartamento 2q · Moema", preco=800_000,
                      motivo="oportunidade única, agende já!")
    linha = _linha(card, {"SP-0007": {"ficha": "68 m² · 2 quarto(s), 1 suíte(s) · 1 vaga(s) · condomínio R$ 850",
                                      "motivos": ["em Moema, um dos bairros que ele citou"]}})
    assert "68 m²" in linha and "condomínio R$ 850" in linha
    assert "casa porque: em Moema" in linha
    assert "oportunidade única" not in linha, "o texto do anunciante não é razão de recomendação"


def test_linha_sem_ficha_ainda_descreve_o_imovel():
    """Sem ficha (busca degradada, imóvel vindo de outro caminho) a linha não pode ficar muda."""
    from agent.nodes.consultor import _linha
    from sdr_shared.models import ImovelCard

    card = ImovelCard(id="SP-0008", titulo="Loja 40 m² · Lapa", preco=4_000, motivo="ponto de esquina")
    assert "ponto de esquina" in _linha(card, {})


def test_ficha_distingue_condominio_zero_de_desconhecido():
    """Zero é 'não tem condomínio'; em branco é 'não sei' — a diferença é dinheiro no aluguel."""
    from agent.tools.buscar_imoveis import ficha
    from sdr_shared.models import Imovel

    def imovel(**kw):
        base = dict(id="SP-1", tipo="apartamento", operacao="aluguel", bairro="Moema", regiao="zona_sul",
                    cidade="São Paulo", quartos=2, area_m2=68.0, preco=4000.0, descricao="x")
        return Imovel(**{**base, **kw})

    assert "condomínio não informado" in ficha(imovel(condominio=None))
    assert "sem condomínio" in ficha(imovel(condominio=0))
    assert "condomínio R$ 850" in ficha(imovel(condominio=850))


# ------------------------------- a pergunta consultiva caía no nó sem fonte

def test_pergunta_de_juizo_vai_para_o_no_institucional():
    """"Esse bairro é bom?" não tem documento que responda — e é por isso que precisa ir para lá.

    No qualificador ou no consultor, um Sonnet sem fonte responde com a média do mercado: plausível,
    específica e frequentemente falsa. No nó institucional a busca não passa do piso e a resposta
    vira "vou confirmar com o corretor".
    """
    from agent.nodes import supervisor

    lead = _lead_com_visita_reservada()
    lead.cartao.pediu_visita = False
    consultivas = ("esse bairro é bom pra família?", "a região é tranquila?",
                   "o brooklin é seguro?", "vale a pena comprar agora?",
                   "quanto costuma ser o condomínio nessa região?")
    for pergunta in consultivas:
        destino = supervisor.run(_estado(pergunta, lead, imoveis_sugeridos=["SP-0001"]))["proximo"]
        assert destino == "informacoes", f"{pergunta!r} não tem fonte — não pode ser respondida de improviso"


def test_adjetivo_do_imovel_continua_sendo_busca(monkeypatch):
    """"Tem apartamento bom no Brooklin?" é catálogo: o adjetivo qualifica o imóvel, não o bairro."""
    from agent.nodes import supervisor

    class Falso:
        def invoke(self, _):
            return type("M", (), {"content": "consultor"})()

    monkeypatch.setattr(supervisor, "llm_roteamento", lambda: Falso())
    lead = _lead_com_visita_reservada()
    lead.cartao.pediu_visita = False
    for busca in ("tem apartamento bom no brooklin até 800 mil?", "quero um apê bom na zona sul"):
        destino = supervisor.run(_estado(busca, lead, imoveis_sugeridos=["SP-0001"]))["proximo"]
        assert destino != "informacoes", f"{busca!r} é busca de imóvel"


# ------------------------------- o resumo que ninguém lia de volta

def test_resumo_do_lead_volta_para_o_prompt():
    """O resumidor escrevia para o corretor e o texto parava ali. O que a poda apaga vive aqui."""
    from agent.prompts import carregar

    corpo = carregar("consultor", memoria="Tem um cachorro grande e o filho estuda no Butantã.",
                     nome="Ana", cartao={}, imoveis="(nenhum)", contexto_busca="").content
    assert "cachorro grande" in corpo
    assert "resumo da conversa até aqui" in corpo
    assert "<<<CLIENTE_" in corpo, "resumo é texto derivado do cliente — entra envelopado"
    assert "não o comente com o cliente" in corpo


def test_sem_resumo_o_prompt_nao_ganha_secao_vazia():
    from agent.prompts import carregar

    for vazio in (None, "", "   "):
        corpo = carregar("consultor", memoria=vazio, nome="Ana", cartao={}, imoveis="(nenhum)",
                         contexto_busca="").content
        assert "resumo da conversa" not in corpo
