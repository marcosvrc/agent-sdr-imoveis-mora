import pytest

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

    monkeypatch.setattr(qualificador, "llm_extracao", lambda: ModeloFalso())
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

    monkeypatch.setattr(qualificador, "llm_extracao", lambda: ModeloFalso())
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


@pytest.mark.parametrize("bruto, esperado", [
    ("consultor", "consultor"),
    ("Consultor.", "consultor"),
    ("**informacoes**", "informacoes"),
    ("informações", "informacoes"),
    ("Decisão: agendador", "agendador"),
    ([{"type": "text", "text": "handoff"}], "handoff"),
    ("", None),
    ("não sei", None),
])
def test_decisao_do_roteador_e_lida_mesmo_fora_do_formato(bruto, esperado):
    """A matriz mediu um modelo que roteou tudo para o qualificador: pontuação, markdown ou acento
    faziam a resposta cair no valor padrão, em silêncio."""
    from agent.nodes.supervisor import interpretar_decisao
    assert interpretar_decisao(bruto) == esperado


def test_nao_se_apresenta_de_novo_quando_o_site_ja_deu_boas_vindas():
    """O chat do site abre com "Olá! Eu sou a Mora…"; a resposta ao primeiro "oi" repetia a
    apresentação. O widget avisa que já saudou, e a Mora vai direto ao ponto."""
    from types import SimpleNamespace
    from agent.nodes.qualificador import _abertura

    site = SimpleNamespace(meta={"saudacao_exibida": True})
    telegram = SimpleNamespace(meta={})
    assert "NÃO se apresente" in _abertura({"primeira_interacao": True, "entrada": site})
    assert "apresente-se" in _abertura({"primeira_interacao": True, "entrada": telegram})
    assert "não se apresente de novo" in _abertura({"primeira_interacao": False, "entrada": telegram})


@pytest.mark.parametrize("txt, esperado", [
    ("11 98765-4321", True), ("(81) 99876-5442", True), ("meu whats é 11987654321", True),
    ("pode mandar em marcos@exemplo.com.br", True),
    ("tem outro de 2 quartos até 500 mil?", False), ("sábado às 10h", False), ("oi", False),
])
def test_reconhece_mensagem_que_e_so_contato(txt, esperado):
    from agent.nodes.qualificador import so_contato
    assert so_contato(txt) is esperado


def test_telefone_depois_da_reserva_nao_traz_mais_imoveis():
    """Um lead real: a Mora pediu o telefone ao reservar a visita, o cliente mandou, o modelo de
    rota viu cartão completo e mandou para o consultor — que respondeu com mais dois imóveis."""
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
    from sdr_shared.models import Estagio, ImovelCard, Intencao, Lead
    from agent.nodes import supervisor

    lead = Lead(id="l_tel", estagio=Estagio.AGENDADO)
    c = lead.cartao
    c.intencao, c.regiao, c.preco_max, c.quartos, c.urgencia = Intencao.COMPRA, "zona_leste", 500000, 1, "imediata"
    c.pediu_visita = True
    entrada = MensagemNormalizada(lead_id="l_tel", canal=Canal.WEB, tipo=TipoMensagem.TEXTO,
                                  identificador_canal="s", conteudo="81 99876-5442")
    card = ImovelCard(id="SP-1", titulo="Studio · Mooca", preco=1.0, foto=None, motivo="x")
    out = supervisor.run({"lead": lead, "entrada": entrada, "imoveis_sugeridos": [card], "saltos": 0})
    assert out["proximo"] == "qualificador"


@pytest.mark.parametrize("msg, pergunta, esperado", [
    ("estou com uma urgencia", "Tem alguma urgência nessa compra?", "imediata"),
    ("o quanto antes", "Pra quando você precisa?", "imediata"),
    ("sem pressa, só pesquisando", "Tem prazo?", "sem_prazo"),
    ("não é urgente", "É urgente?", "sem_prazo"),
    ("em uns 3 meses", "Pra quando pretende se mudar?", "3_meses"),
    ("logo ali perto do metrô", "Qual região?", None),     # "logo" sem falar de prazo não é urgência
])
def test_urgencia_por_regra(msg, pergunta, esperado):
    from agent.nodes.qualificador import urgencia_por_regra
    assert urgencia_por_regra(msg, pergunta) == esperado


def test_com_campo_faltando_nao_promete_imoveis_e_pergunta_o_que_falta():
    """Um lead real ouviu "Vou te apresentar as opções que temos" com a urgência ainda em aberto,
    e nada aconteceu: quem mostra imóvel é o consultor, e só com o cartão completo."""
    from sdr_shared.models import Intencao, Lead
    from agent.nodes.qualificador import _conferir

    lead = Lead(id="l_prom")
    c = lead.cartao
    c.intencao, c.regiao, c.preco_max, c.quartos = Intencao.COMPRA, "zona_oeste", 600000, 2
    assert _conferir("Combinado! Vou te apresentar as opções que temos por aqui.", lead) == \
        "Anotado! E pra quando você precisa? É urgente ou dá pra ir com calma?"
    assert _conferir("Perfeito, anotado.", lead).endswith("É urgente ou dá pra ir com calma?")
    assert _conferir("E pra quando você pretende se mudar?", lead) == "E pra quando você pretende se mudar?"
    c.urgencia = "imediata"                                  # completo: nada a corrigir
    assert _conferir("Vou te apresentar as opções.", lead) == "Vou te apresentar as opções."


# --------------------------------------------------------- sem imóvel exato: perguntar antes

def _lead_moema():
    from sdr_shared.models import Intencao, Lead
    lead = Lead(id="l_moema", nome="Marcos")
    c = lead.cartao
    c.intencao, c.bairros, c.regiao, c.preco_max, c.quartos, c.urgencia = \
        Intencao.ALUGUEL, ["Moema"], "zona_sul", 6000, 2, "sem_prazo"
    return lead


def _estado_consultor(lead, texto, **extra):
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
    e = MensagemNormalizada(lead_id=lead.id, canal=Canal.WEB, tipo=TipoMensagem.TEXTO,
                            identificador_canal="s", conteudo=texto)
    return {"lead": lead, "entrada": e, "messages": [], "cartao_extraido_de": texto, **extra}


def _busca_falsa(monkeypatch, chamadas):
    from sdr_shared.models import ImovelCard
    from agent.nodes import consultor

    def buscar(cartao, preferencia=None, limite=6):
        chamadas.append(cartao)
        card = ImovelCard(id="SP-9", titulo="Apartamento 3q · Moema", preco=9000.0, foto=None, motivo="x")
        if cartao.preco_max is None:                         # sem teto, há em Moema
            return {"cards": [card], "nivel": "bairro", "bairros_pedidos": ["Moema"],
                    "bairros_encontrados": ["Moema"], "ampliou": False, "fichas": {}}
        viz = ImovelCard(id="SP-8", titulo="Apartamento 2q · Butantã", preco=5500.0, foto=None, motivo="y")
        return {"cards": [viz], "nivel": "cidade", "bairros_pedidos": ["Moema"],
                "bairros_encontrados": ["Butantã"], "ampliou": True, "fichas": {}}
    monkeypatch.setattr(consultor, "buscar_com_contexto", buscar)
    monkeypatch.setattr(consultor, "InteresseRepository", lambda: type("R", (), {
        "por_situacao": lambda self, _: {}, "registrar_varios": lambda self, *a: None})())


def test_sem_imovel_no_bairro_pergunta_como_ampliar_antes_de_mostrar(monkeypatch):
    """Um lead pediu 2 quartos em Moema até R$ 6 mil e recebeu, num parágrafo só, um studio que não
    servia e imóveis na Mooca e no Butantã. Agora a Mora pergunta antes, com botões."""
    from agent.nodes import consultor
    _busca_falsa(monkeypatch, [])
    monkeypatch.setattr(consultor, "llm_conversa", lambda: pytest.fail("a pergunta é fixa"))
    out = consultor.run(_estado_consultor(_lead_moema(), "pode esperar"))
    r = out["resposta"]
    assert not r.imoveis, "nenhum imóvel antes de o cliente escolher"
    assert r.texto.startswith("Marcos, em Moema não encontrei") and "R$ 6 mil/mês" in r.texto
    assert [o.split("|")[0] for o in r.opcoes] == ["ajuste:preco", "ajuste:vizinhos", "ajuste:quartos"]
    assert out["ajuste_pendente"]


def test_escolher_acima_do_valor_busca_no_bairro_sem_teto(monkeypatch):
    from langchain_core.messages import AIMessage
    from agent.nodes import consultor
    chamadas = []
    _busca_falsa(monkeypatch, chamadas)

    class _Llm:
        def invoke(self, msgs):
            return AIMessage(content="Em Moema:\n• Moema — 3 quartos\n\nQuer agendar?")
    monkeypatch.setattr(consultor, "llm_conversa", lambda: _Llm())
    lead = _lead_moema()
    out = consultor.run(_estado_consultor(lead, "ajuste:preco"))
    assert chamadas[-1].preco_max is None and chamadas[-1].bairros == ["Moema"]
    assert [c.id for c in out["resposta"].imoveis] == ["SP-9"]
    assert out["ajuste"]["tipo"] == "preco" and lead.cartao.preco_max == 6000, "o cartão não muda"


@pytest.mark.parametrize("texto, tipo", [
    ("pode ser em bairro vizinho", "vizinhos"), ("pode aumentar um pouco o valor", "preco"),
    ("aceito com 1 quarto", "quartos"), ("hmm não sei", None),
])
def test_resposta_escrita_a_pergunta_de_ajuste(texto, tipo):
    from agent.nodes import consultor
    lead = _lead_moema()
    criterio = consultor._criterio(lead.cartao)
    assert consultor._ajuste_escolhido({"ajuste_pendente": criterio}, texto, criterio) == tipo


def test_estado_salvo_aceita_todos_os_tipos_do_lead():
    """`Segmento` e `AnaliseLead` entraram no Lead depois da lista fixa de tipos do checkpoint, e o
    LangGraph passou a recusar desserializá-los. A lista agora sai dos módulos."""
    from agent.graph import tipos_do_checkpoint
    tipos = set(tipos_do_checkpoint())
    for nome in ("Lead", "CartaoQualificacao", "Segmento", "AnaliseLead", "Intencao", "Estagio"):
        assert ("sdr_shared.models.lead", nome) in tipos
    assert ("sdr_shared.models.imovel", "ImovelCard") in tipos
    assert ("sdr_shared.messaging.contracts", "RespostaAgente") in tipos


@pytest.mark.parametrize("txt, esperado", [
    ("bom dia. Gostaria de avaliar imóveis em Moema de até 5 mil de aluguel", "aluguel"),
    ("na verdade quero comprar", "compra"),
    ("quero comprar para alugar depois", None),
    ("tem outro em Moema?", None),
])
def test_intencao_citada(txt, esperado):
    from agent.nodes.supervisor import intencao_citada
    r = intencao_citada(txt)
    assert (r.value if r else None) == esperado


def test_trocar_compra_por_aluguel_depois_de_qualificado_vai_ao_qualificador():
    """Um teste real: compra em Perdizes já qualificada, e a mensagem pedindo ALUGUEL em Moema foi
    para o consultor, que mantém a intenção — buscou compra até R$ 5 mil e a resposta saiu errada."""
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
    from sdr_shared.models import Estagio, ImovelCard, Intencao, Lead
    from agent.nodes import supervisor
    lead = Lead(id="l_troca", estagio=Estagio.AGENDADO)
    c = lead.cartao
    c.intencao, c.bairros, c.regiao, c.preco_max, c.quartos, c.urgencia = \
        Intencao.COMPRA, ["Perdizes"], "zona_oeste", 1_000_000, 1, "imediata"
    e = MensagemNormalizada(lead_id=lead.id, canal=Canal.WEB, tipo=TipoMensagem.TEXTO, identificador_canal="s",
                            conteudo="bom dia. Gostaria de avaliar imóveis em Moema de até 5 mil de aluguel com urgência")
    card = ImovelCard(id="SP-1", titulo="Studio · Perdizes", preco=1.0, foto=None, motivo="x")
    out = supervisor.run({"lead": lead, "entrada": e, "imoveis_sugeridos": [card], "saltos": 0})
    assert out["proximo"] == "qualificador"


# ------------------------------------------- horário segurado não sequestra a conversa

def _lead_escolhendo_horario():
    from sdr_shared.models import Estagio, Lead
    lead = Lead(id="lead-pend", nome="Marcos", estagio=Estagio.QUALIFICADO)
    c = lead.cartao
    c.intencao, c.regiao, c.preco_max, c.quartos, c.urgencia = Intencao.ALUGUEL, "zona_oeste", 3500, 2, "imediata"
    c.pediu_visita = True
    return lead


_PENDENTE = "2099-01-05T13:00:00+00:00"


@pytest.mark.parametrize("texto, destino", [
    ("vocês aceitam pet?", "informacoes"),
    ("Ver outros", "consultor"),
])
def test_depois_de_insistir_o_horario_e_solto_e_a_mensagem_segue(texto, destino):
    """Um lead real: escolheu o horário, não quis passar telefone, perguntou se aceitam pet — e
    recebeu "pra reservar eu preciso de um contato" de novo, a cada mensagem, sem saída."""
    from agent.nodes import supervisor
    out = supervisor.run(_estado(texto, _lead_escolhendo_horario(), horario_pendente=_PENDENTE,
                                 contato_insistido=True, horarios_oferecidos=[_PENDENTE],
                                 imoveis_sugeridos=["SP-0001"]))
    assert out["proximo"] == destino
    assert out["horario_pendente"] is None and out["horarios_oferecidos"] == []


@pytest.mark.parametrize("texto, destino", [
    ("vocês aceitam pet?", "informacoes"),
    ("Ver outros", "consultor"),
    ("me mostra outras opções", "consultor"),
])
def test_pergunta_que_nao_e_contato_nem_horario_nao_vai_ao_agendador(texto, destino):
    """Pendente não é passe livre para o agendador: pergunta institucional e pedido de opções têm
    dono, mesmo com a grade de horários ainda no estado."""
    from agent.nodes import supervisor
    out = supervisor.run(_estado(texto, _lead_escolhendo_horario(), horario_pendente=_PENDENTE,
                                 horarios_oferecidos=[_PENDENTE], imoveis_sugeridos=["SP-0001"]))
    assert out["proximo"] == destino


def test_resposta_ao_pedido_de_contato_continua_indo_ao_agendador():
    from agent.nodes import supervisor
    lead = _lead_escolhendo_horario()
    for texto in ("11 98765-4321", "Marcos", f"slot:{_PENDENTE}"):
        assert supervisor.run(_estado(texto, lead, horario_pendente=_PENDENTE))["proximo"] == "agendador"
    # antes de insistir, resposta curta ainda é a resposta ao pedido (o agendador insiste uma vez)
    assert supervisor.run(_estado("prefiro não", lead, horario_pendente=_PENDENTE))["proximo"] == "agendador"


def test_com_a_grade_na_tela_pergunta_institucional_vai_ao_no_institucional():
    """`horarios_oferecidos` ficava no estado e trancava a rota de informações para sempre."""
    from agent.nodes import supervisor
    out = supervisor.run(_estado("precisa de fiador?", _lead_escolhendo_horario(),
                                 horarios_oferecidos=[_PENDENTE]))
    assert out["proximo"] == "informacoes"


# ------------------------------------------- "corretor" na frase não é pedido de corretor

@pytest.mark.parametrize("texto", [
    "quando o corretor vai me ligar?",
    "vocês cobram comissão do corretor?",
    "o corretor vai junto na visita?",
    "não quero falar com corretor, só ver as opções",
])
def test_pergunta_sobre_o_corretor_nao_e_handoff(texto, monkeypatch):
    """Logo depois de reservar a visita, "quando o corretor vai me ligar?" encaminhava o lead a um
    humano — a Mora calava, e a pergunta ficava sem resposta até alguém abrir o painel."""
    from agent.nodes import supervisor

    class Falso:                                   # o que não casa regra nenhuma vai ao modelo
        def invoke(self, _):
            return type("M", (), {"content": "consultor"})()
    monkeypatch.setattr(supervisor, "llm_roteamento", lambda: Falso())
    assert not supervisor.pede_humano(texto), texto
    assert supervisor.run(_estado(texto, _lead_com_visita_reservada(),
                                  imoveis_sugeridos=["SP-0001"]))["proximo"] != "handoff"


@pytest.mark.parametrize("texto", [
    "quero falar com um corretor", "me passa um corretor", "chama o corretor", "Falar com corretor",
    "quero um atendente", "tem um humano aí?", "quero falar com uma pessoa de verdade",
    "posso falar com alguém?", "cadê o corretor?",
    # a primeira versão do filtro não pegava preposição nem infinitivo:
    "preciso de um corretor", "me passa pro corretor", "pode chamar o corretor?",
    "me transfere para um corretor", "tem corretor?", "consegue me passar para um corretor?",
])
def test_pedido_explicito_de_pessoa_continua_indo_ao_handoff(texto):
    from agent.nodes import supervisor
    assert supervisor.run(_estado(texto, _lead_com_visita_reservada()))["proximo"] == "handoff"


# ------------------------------------------- "horário" sozinho não é pedido de visita

def test_horario_de_atendimento_e_pergunta_institucional():
    from agent.nodes import supervisor
    lead = _lead_com_visita_reservada()
    lead.cartao.pediu_visita = False
    assert supervisor.run(_estado("qual o horário de atendimento de vocês?", lead))["proximo"] == "informacoes"


@pytest.mark.parametrize("texto", ["posso remarcar?", "preciso desmarcar a visita", "tem outro horário?",
                                   "dá pra reagendar pra semana que vem?"])
def test_remarcar_chega_ao_agendador(texto):
    from agent.nodes import supervisor
    lead = _lead_com_visita_reservada()
    assert supervisor.run(_estado(texto, lead, imoveis_sugeridos=["SP-0001"]))["proximo"] == "agendador"


# ------------------------------------------- troca de intenção só quando é troca

@pytest.mark.parametrize("txt", [
    "quanto rende o aluguel desse?",
    "não quero comprar agora",
    "nao vou alugar, era só curiosidade",
    "dá pra alugar depois?",
])
def test_citar_o_outro_uso_nao_e_trocar_de_intencao(txt):
    """"quanto rende o aluguel desse?" é pergunta de comprador; "não quero comprar agora" é
    locatário dizendo que segue locatário. Os dois iam para o qualificador como troca."""
    from agent.nodes.supervisor import intencao_citada
    assert intencao_citada(txt) is None


def test_troca_real_de_intencao_nao_reaproveita_o_teto(monkeypatch):
    """Lead QUALIFICADO em compra até 800 mil diz que agora quer alugar: o cartão seguia com
    `preco_max = 800000`, e a busca procurava aluguel de até R$ 800 mil por mês."""
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
    from sdr_shared.models import CartaoQualificacao, Estagio, ImovelCard, Lead
    from langchain_core.messages import AIMessage
    from agent.nodes import qualificador

    monkeypatch.setattr(qualificador, "_extrair", lambda cartao, msg, pergunta="":
                        cartao.model_copy(update={"intencao": Intencao.ALUGUEL}))
    monkeypatch.setattr(qualificador, "llm_conversa", lambda: type("L", (), {
        "invoke": lambda self, _m: AIMessage(content="Anotado! Até quanto por mês?")})())
    monkeypatch.setattr(qualificador, "auditar", lambda **k: None)
    lead = Lead(id="l-troca-q", estagio=Estagio.QUALIFICADO, cartao=CartaoQualificacao(
        intencao=Intencao.COMPRA, bairros=["Pinheiros"], regiao="zona_oeste", preco_max=800_000,
        quartos=2, urgencia="imediata"))
    e = MensagemNormalizada(lead_id=lead.id, canal=Canal.TELEGRAM, tipo=TipoMensagem.TEXTO,
                            identificador_canal="1", conteudo="na verdade quero alugar")
    card = ImovelCard(id="SP-1", titulo="Apto · Pinheiros", preco=790000.0, foto=None, motivo="x")
    out = qualificador.run({"lead": lead, "entrada": e, "messages": [], "imoveis_sugeridos": [card]})
    assert out["lead"].cartao.intencao == Intencao.ALUGUEL
    assert out["lead"].cartao.preco_max is None, "teto de compra não vira teto de aluguel"
    assert out["imoveis_sugeridos"] == [], "os imóveis de compra não contam como já mostrados"


@pytest.mark.parametrize("texto", ["tanto faz", "sim", "qualquer um"])
def test_resposta_vaga_a_pergunta_de_ajuste_nao_repete_a_pergunta(monkeypatch, texto):
    """"Como prefere que eu continue?" — "tanto faz". A Mora perguntava de novo, igual, com os mesmos
    botões; e de novo a cada "sim". Resposta que não escolhe nada vira bairros vizinhos."""
    from langchain_core.messages import AIMessage
    from agent.nodes import consultor
    _busca_falsa(monkeypatch, [])

    class _Llm:
        def invoke(self, msgs):
            return AIMessage(content="Em bairros vizinhos:\n• Butantã\n\nQuer agendar?")
    monkeypatch.setattr(consultor, "llm_conversa", lambda: _Llm())
    lead = _lead_moema()
    criterio = consultor._criterio(lead.cartao)
    out = consultor.run(_estado_consultor(lead, texto, ajuste_pendente=criterio))
    assert out["resposta"].imoveis, "mostra as alternativas em vez de perguntar de novo"
    assert out["ajuste"]["tipo"] == "vizinhos" and not out.get("ajuste_pendente")


@pytest.mark.parametrize("texto", ["ok", "agora não", "prefiro não passar", "depois eu mando"])
def test_recusa_depois_da_insistencia_vai_ao_agendador_que_solta_e_diz(texto):
    """Soltar o horário no supervisor e seguir o fluxo mandava "agora não" de volta ao agendador
    pela rota de `pediu_visita`, e ele oferecia a grade de novo para quem tinha acabado de recusar.
    Agora vai ao agendador AINDA com o pendente, e ele responde "deixei o horário livre"."""
    from agent.nodes import supervisor
    out = supervisor.run(_estado(texto, _lead_escolhendo_horario(), horario_pendente=_PENDENTE,
                                 contato_insistido=True, horarios_oferecidos=[_PENDENTE]))
    assert out["proximo"] == "agendador"



def _lead_com_opcoes_na_tela():
    from sdr_shared.models import Estagio, ImovelCard, Lead
    lead = Lead(id="lead-detalhe", nome="Ramos", estagio=Estagio.QUALIFICADO)
    c = lead.cartao
    c.intencao, c.bairros, c.regiao, c.preco_max, c.quartos, c.urgencia = \
        Intencao.ALUGUEL, ["Pinheiros"], "zona_oeste", 4000, 1, "30 dias"
    cards = [ImovelCard(id="SP-1", titulo="Studio · Pinheiros", preco=3200.0, foto=None, motivo="x"),
             ImovelCard(id="SP-2", titulo="Apartamento 1q · Pinheiros", preco=3800.0, foto=None, motivo="y")]
    return lead, {"imoveis_sugeridos": cards, "ultimos_sugeridos": ["SP-1", "SP-2"]}


@pytest.mark.parametrize("grade", [False, True])
def test_pedir_detalhes_antes_de_agendar_nao_traz_a_grade(grade):
    """Relato do cliente: "Antes de agendar pode mandar mais detalhes da segunda opção?" casava
    PEDE_VISITA ("agendar"), ia ao agendador, e a resposta falava dos detalhes com a grade de
    horários embaixo. Com a grade já na tela, "segunda" ainda casava ESCOLHE_HORARIO (segunda-feira)."""
    from agent.nodes import supervisor
    lead, extra = _lead_com_opcoes_na_tela()
    if grade:
        extra["horarios_oferecidos"] = ["2026-10-12T13:00:00+00:00"]
        lead.cartao.pediu_visita = True
    txt = "Antes de agendar pode mandar mais detalhes da segunda opção?"
    assert supervisor.run(_estado(txt, lead, **extra))["proximo"] == "consultor"


def test_adiar_a_visita_nao_e_pedir_visita():
    from agent.nodes import supervisor
    lead, _ = _lead_com_opcoes_na_tela()
    lead.cartao.pediu_visita = True              # a rota grudada também não vale para quem adia
    assert supervisor.run(_estado("ainda não quero agendar, to pensando", lead))["proximo"] != "agendador"


def test_pedido_de_visita_continua_chegando_ao_agendador():
    from agent.nodes import supervisor
    lead, extra = _lead_com_opcoes_na_tela()
    assert supervisor.run(_estado("quero agendar uma visita", lead, **extra))["proximo"] == "agendador"
    assert supervisor.run(_estado("Agendar visita", lead, **extra))["proximo"] == "agendador"


def test_consultor_detalha_o_imovel_citado_sem_buscar_nem_mostrar_horarios(monkeypatch):
    from langchain_core.messages import AIMessage
    from sdr_shared.models import Imovel
    from agent.nodes import consultor
    lead, extra = _lead_com_opcoes_na_tela()
    monkeypatch.setattr(consultor, "buscar_com_contexto", lambda *a, **k: pytest.fail("não busca de novo"))
    vistos = []

    class Repo:
        def get(self, imovel_id):
            vistos.append(imovel_id)
            return Imovel(id=imovel_id, tipo="apartamento", operacao="aluguel", cidade="São Paulo",
                          regiao="zona_oeste", bairro="Pinheiros", quartos=1, area_m2=42, preco=3800.0,
                          condominio=650, descricao="Mobiliado, varanda.")
    monkeypatch.setattr(consultor, "ImovelRepository", Repo)
    prompts = []

    class Modelo:
        def invoke(self, msgs):
            prompts.append(msgs[0].content)
            return AIMessage(content="O de 42 m² é mobiliado e tem varanda. Quer agendar uma visita?")
    monkeypatch.setattr(consultor, "llm_conversa", lambda: Modelo())
    out = consultor.run(_estado_consultor(lead, "mais detalhes da segunda opção?", **extra))
    r = out["resposta"]
    assert vistos == ["SP-2"] and "Mobiliado, varanda." in prompts[0]
    assert not r.imoveis and not any(o.startswith("slot:") for o in r.opcoes)
    assert r.opcoes == ["Agendar visita", "Ver outros", "Falar com corretor"]
    assert out["imovel_escolhido"] == "SP-2"     # "Agendar visita" em seguida já vai para a grade dele
