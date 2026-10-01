"""Os três cenários do desafio, ponta a ponta: compra, investimento e follow-up."""
from sdr_shared.messaging import MensagemNormalizada, Canal, TipoMensagem
from sdr_shared.models import Estagio, Intencao, Temperatura
from sdr_shared.db import LeadRepository, MensagemRepository, VisitaRepository
from agent.handler import processar


def msg(lead, texto, tipo=TipoMensagem.TEXTO, meta=None, canal=Canal.TELEGRAM):
    return MensagemNormalizada(lead_id=lead, canal=canal, identificador_canal="5511999990000", tipo=tipo, conteudo=texto, meta=meta or {})


def ultima(broker, topic="outbound-telegram"):
    return [b for t, b, _ in broker.msgs if t == topic][-1]["resposta"]


def test_cenario_compra(infra):
    broker, sched = infra
    processar(msg("l1", "Estou procurando apartamento na zona sul", meta={"nome": "Marcos"}))
    lead = LeadRepository().get("l1")
    assert lead.cartao.intencao == Intencao.COMPRA and lead.cartao.regiao == "zona_sul"
    assert lead.estagio == Estagio.QUALIFICANDO
    # a resposta falsa não pergunta nada: com campo faltando, a pergunta fixa do campo é acrescentada
    assert ultima(broker)["texto"] == "[resposta da Mora]\n\nAté quanto você pretende pagar?"
    # lead ainda frio: 2h da cadência padrão × 2 do ritmo de lead frio (ver sdr_shared/followup.py)
    assert "l1" in sched.agendados and sched.agendados["l1"][0] == 240

    processar(msg("l1", "até 800 mil, 2 quartos, é urgente"))
    lead = LeadRepository().get("l1")
    assert lead.cartao.completo()
    assert lead.temperatura == Temperatura.QUENTE                            # cartão completo + urgência

    processar(msg("l1", "me mostra as opções"))                              # consultor
    r = ultima(broker)
    assert r["imoveis"] and r["imoveis"][0]["id"] == "SP-0001"              # filtro híbrido: venda, zona_sul, ≤800k*1.15, ≥2q
    assert "Agendar visita" in r["opcoes"]
    assert LeadRepository().get("l1").estagio == Estagio.QUALIFICADO

    processar(msg("l1", "Agendar visita", tipo=TipoMensagem.BOTAO))          # agendador turno 1
    r = ultima(broker)
    assert r["opcoes"] and r["opcoes"][0].startswith("slot:")
    slot = r["opcoes"][0].split("|")[0]

    processar(msg("l1", slot, tipo=TipoMensagem.BOTAO))                     # agendador turno 2
    lead = LeadRepository().get("l1")
    assert lead.estagio == Estagio.AGENDADO and ultima(broker)["acao"] == "agendar"
    assert len(VisitaRepository().listar()) == 1
    assert "l1" not in sched.agendados                                       # follow-up cancelado
    assert any(t == "resumir" for t, _, _ in broker.msgs)                    # briefing para o corretor disparado
    from agent.handler import resumir
    assert resumir("l1") == "[resposta da Mora]"                             # briefing em texto
    l1 = LeadRepository().get("l1")
    assert l1.analise and l1.analise.sentimento == "positivo" and l1.analise.perfil_decisao == "objetivo" and l1.analisado_em
    assert len(MensagemRepository().historico("l1")) == 10                   # 5 in + 5 out


def test_cenario_investimento(infra):
    broker, _ = infra
    processar(msg("l2", "Quero investir em imóveis para renda"))
    assert LeadRepository().get("l2").cartao.intencao == Intencao.INVESTIMENTO
    processar(msg("l2", "perfil moderado, uns 500 mil, espero 0,6% ao mês"))
    lead = LeadRepository().get("l2")
    assert lead.cartao.completo() and lead.cartao.campos_faltantes() == []
    processar(msg("l2", "quero falar com um corretor especialista"))
    assert LeadRepository().get("l2").estagio == Estagio.HANDOFF
    assert ultima(broker)["acao"] == "handoff"
    # Em handoff o agente não conduz mais a conversa — mas o silêncio ABSOLUTO era um beco: quem
    # caía lá por engano escrevia e nada acontecia. A primeira mensagem depois do encaminhamento
    # recebe UM aviso, que diz que o corretor foi chamado e como voltar para a Mora.
    processar(msg("l2", "ok, aguardo"))
    aviso = MensagemRepository().historico("l2")[-1]
    assert aviso["direcao"] == "out" and aviso["meta"]["motivo"] == "handoff_aviso"
    assert "continuar com a Mora" in aviso["conteudo"]

    processar(msg("l2", "e aí, alguma novidade?"))                           # daí em diante, silêncio
    assert MensagemRepository().historico("l2")[-1]["direcao"] == "in"


def test_cenario_followup(infra):
    _broker, sched = infra
    processar(msg("l3", "Estou procurando apartamento na zona sul"))
    assert sched.agendados["l3"][0] == 240                                   # 2h × 2 (lead frio)
    payload = sched.agendados["l3"][1]
    processar(MensagemNormalizada.model_validate_json(payload))              # scheduler disparou
    lead = LeadRepository().get("l3")
    assert lead.estagio == Estagio.INATIVO and lead.followups_enviados == 1
    assert sched.agendados["l3"][0] == 24 * 60 * 2                           # próximo: 24h × 2
    processar(MensagemNormalizada.model_validate_json(sched.agendados["l3"][1]))
    processar(MensagemNormalizada.model_validate_json(sched.agendados["l3"][1]))
    lead = LeadRepository().get("l3")
    assert lead.estagio == Estagio.FRIO and lead.followups_enviados == 3 and "l3" not in sched.agendados
    processar(msg("l3", "oi, voltei! até 800 mil e 2 quartos"))               # lead reengajou
    assert LeadRepository().get("l3").cartao.quartos == 2


def test_contexto_do_site(infra):
    broker, _ = infra
    from sdr_shared.db import EventoNavegacaoRepository
    EventoNavegacaoRepository().registrar("sess-1", "viewed_imovel", {"imovel_id": "SP-0003"})
    m = MensagemNormalizada(lead_id="web_sess-1", canal=Canal.WEB, identificador_canal="sess-1", conteudo="oi, gostei desse",
                            meta={"imovel_origem": "SP-0001"})
    processar(m)
    lead = LeadRepository().get("web_sess-1")
    assert lead.cartao.imoveis_visualizados == ["SP-0001", "SP-0003"]
    assert ultima(broker, "outbound-web")["texto"]


def test_horario_digitado(infra):
    """Canal web: o cliente responde por escrito em vez de clicar. Horário inexistente reoferece; válido confirma."""
    broker, _ = infra
    processar(msg("l3", "quero visitar um imóvel", canal=Canal.WEB))            # PEDE_VISITA → agendador turno 1
    r = ultima(broker, "outbound-web")
    assert r["opcoes"] and r["opcoes"][0].startswith("slot:")
    rotulo = r["opcoes"][1].split("|")[1]                                        # ex.: "ter 15/09 às 14h"

    processar(msg("l3", "pode ser às 17h?", canal=Canal.WEB))                    # não existe na grade
    r = ultima(broker, "outbound-web")
    assert LeadRepository().get("l3").estagio != Estagio.AGENDADO
    assert r["opcoes"] and r["opcoes"][0].startswith("slot:")                    # reofereceu

    processar(msg("l3", f"então fica {rotulo}", canal=Canal.WEB))               # texto casa com um slot oferecido
    r = ultima(broker, "outbound-web")
    # no site, sem contato: o horário fica segurado até chegar o telefone
    assert LeadRepository().get("l3").estagio != Estagio.AGENDADO and "telefone" in r["texto"]

    processar(msg("l3", "11 98765-4321", canal=Canal.WEB))
    r = ultima(broker, "outbound-web")
    assert LeadRepository().get("l3").estagio == Estagio.AGENDADO
    assert r["acao"] == "agendar" and r["dados"]["visita"]["inicio"]
    assert len(VisitaRepository().listar()) == 1


def test_handoff_roteia_para_corretor_da_regiao(infra):
    """Com corretores cadastrados, o handoff escolhe quem atende a região (menor carga) e cita o nome ao cliente."""
    from sdr_shared.db import CorretorRepository
    from sdr_shared.models import Corretor
    CorretorRepository().upsert(Corretor(id="cor_ana", nome="Ana Souza", regioes=["zona_sul"]))
    CorretorRepository().upsert(Corretor(id="cor_bruno", nome="Bruno Lima", regioes=["zona_oeste"]))
    CorretorRepository().upsert(Corretor(id="cor_carla", nome="Carla Mendes", regioes=[], ativo=False))   # inativa: nunca
    broker, _ = infra
    processar(msg("l4", "Estou procurando apartamento na zona sul", meta={"nome": "Marcos"}))
    processar(msg("l4", "quero falar com um corretor"))
    lead = LeadRepository().get("l4")
    assert lead.estagio == Estagio.HANDOFF and lead.corretor_id == "cor_ana"
    assert "Ana" in ultima(broker)["texto"]
    # visita de um lead já vinculado herda o corretor
    processar(msg("l5", "Estou procurando apartamento na zona sul"))
    processar(msg("l5", "quero visitar um imóvel"))
    slot = ultima(broker)["opcoes"][0].split("|")[0]
    processar(msg("l5", slot, tipo=TipoMensagem.BOTAO))
    v = next(x for x in VisitaRepository().listar() if x["lead_id"] == "l5")
    assert v["corretor_id"] == "cor_ana" and v["corretor_nome"] == "Ana Souza"


def test_busca_respeita_o_bairro_pedido(infra):
    """Bug real: pedir Pinheiros trazia a zona oeste inteira e o agente concluía que não havia imóveis lá."""
    from agent.tools.buscar_imoveis import buscar_com_contexto
    from sdr_shared.models import CartaoQualificacao, Intencao

    cartao = CartaoQualificacao(intencao=Intencao.ALUGUEL, regiao="zona_oeste", bairros=["Pinheiros"], preco_max=5000, quartos=1)
    r = buscar_com_contexto(cartao, limite=6)
    assert r["cards"], "há imóveis de aluguel em Pinheiros na base"
    assert r["ampliou"] is False
    assert all("Pinheiros" in c.titulo for c in r["cards"]), "só pode devolver o bairro pedido"

    # bairro sem estoque no perfil: amplia para a região e avisa (em vez de dizer que não há nada)
    sem_estoque = CartaoQualificacao(intencao=Intencao.ALUGUEL, regiao="zona_oeste", bairros=["Perdizes"], preco_max=2000, quartos=1)
    r2 = buscar_com_contexto(sem_estoque, limite=6)
    if r2["cards"]:
        assert r2["ampliou"] is True and "Perdizes" in r2["bairros_pedidos"]


def test_briefing_marca_pedido_e_conclusao(infra):
    """O pedido de briefing fica registrado; o resumidor carimba a conclusão. A diferença entre os dois
    é o que o painel usa para dizer que o worker não respondeu, em vez de mostrar um card vazio."""
    from agent.handler import resumir
    processar(msg("lb", "Quero comprar apartamento na zona sul"))
    LeadRepository().marcar_analise_pedida("lb")
    lead = LeadRepository().get("lb")
    assert lead.analise_solicitada_em and (lead.analisado_em is None or lead.analisado_em < lead.analise_solicitada_em)

    assert resumir("lb") == "[resposta da Mora]"
    depois = LeadRepository().get("lb")
    assert depois.resumo and depois.analisado_em >= depois.analise_solicitada_em      # pedido atendido


# ------------------------------------------------------------------ interesses

def test_o_que_o_agente_mostra_vira_interesse_registrado(infra):
    """O vínculo lead↔imóvel precisa sobreviver à conversa: é ele que evita repetir sugestão na
    semana seguinte e que diz ao corretor quem está de olho em cada imóvel."""
    from sdr_shared.db import InteresseRepository
    processar(msg("l1", "quero comprar apartamento na zona sul, até 800 mil, 2 quartos, urgente",
                  meta={"nome": "Marcos"}))
    processar(msg("l1", "me mostra as opções"))

    interesses = InteresseRepository().do_lead("l1")
    assert interesses, "o consultor mostrou imóveis e nada foi registrado"
    assert {i["situacao"] for i in interesses} == {"sugerido"}
    assert all(i["origem"] == "agente" and i["bairro"] for i in interesses)


def test_imovel_descartado_nao_volta_a_ser_oferecido(infra):
    from sdr_shared.db import InteresseRepository
    repo = InteresseRepository()
    processar(msg("l1", "quero comprar apartamento na zona sul, até 800 mil, 2 quartos, urgente"))
    processar(msg("l1", "me mostra as opções"))
    mostrados = {i["imovel_id"] for i in repo.do_lead("l1")}
    descartado = sorted(mostrados)[0]
    repo.registrar("l1", descartado, situacao="descartado", origem="corretor")

    processar(msg("l1", "tem outros?"))
    depois = {i["imovel_id"] for i in repo.do_lead("l1") if i["situacao"] == "sugerido"}
    assert descartado not in depois, "o descartado voltou para a lista de sugestões"
    assert repo.por_situacao("l1")["descartado"] == {descartado}, "o descarte não pode ser rebaixado"


def test_botao_do_site_registra_interesse_declarado(infra):
    """Clicar em 'falar sobre este imóvel' é diferente de passar os olhos na ficha."""
    from sdr_shared.db import InteresseRepository
    from sdr_shared.messaging import Canal
    processar(msg("l1", "esse aqui ainda está disponível?", canal=Canal.WEB,
                  meta={"imovel_origem": "SP-0001"}))
    interesse = next(i for i in InteresseRepository().do_lead("l1") if i["imovel_id"] == "SP-0001")
    assert interesse["situacao"] == "interessado" and interesse["origem"] == "site"


def test_visita_marcada_sobrepoe_qualquer_situacao_anterior(infra):
    from datetime import datetime, timedelta, timezone
    from sdr_shared.db import InteresseRepository, LeadRepository
    from sdr_shared.models import Lead
    from agent.tools.agenda import agendar
    LeadRepository().upsert(Lead(id="l1", nome="Marcos"))
    repo = InteresseRepository()
    repo.registrar("l1", "SP-0002", situacao="descartado", origem="corretor")
    agendar("l1", "SP-0002", datetime.now(timezone.utc) + timedelta(days=3))
    assert repo.por_situacao("l1")["visita_marcada"] == {"SP-0002"}


def test_interessados_ordena_por_score_e_ignora_descartado(infra):
    from sdr_shared.db import InteresseRepository, LeadRepository
    from sdr_shared.models import Lead
    repo = InteresseRepository()
    LeadRepository().upsert(Lead(id="l_quente", nome="Quente", score=90))
    LeadRepository().upsert(Lead(id="l_frio", nome="Frio", score=10))
    LeadRepository().upsert(Lead(id="l_fora", nome="Fora", score=99))
    for lead, situacao in (("l_quente", "interessado"), ("l_frio", "sugerido"), ("l_fora", "descartado")):
        repo.registrar(lead, "SP-0003", situacao=situacao, origem="corretor" if situacao != "sugerido" else "agente")

    nomes = [i["nome"] for i in repo.interessados("SP-0003")]
    assert "Fora" not in nomes, "quem descartou não entra na lista de quem chamar"
    assert nomes.index("Quente") < nomes.index("Frio"), "o mais quente vem primeiro"


# --------------------------------------------------- mudar de ideia depois de qualificado

def test_cliente_qualificado_pode_trocar_de_bairro(infra, monkeypatch):
    """Relato do cliente: mandou um áudio pedindo Vila Mariana e Vila Madalena e recebeu os imóveis
    da busca ANTERIOR, com um texto por cima dizendo "claro, posso buscar na Vila Madalena também".

    A causa: o cartão só era extraído no qualificador. Depois de completo, o supervisor manda a
    conversa para o consultor — que buscava com os bairros antigos. Os cards diziam uma coisa e o
    texto dizia outra, na mesma resposta.
    """
    from agent.nodes import consultor
    from sdr_shared.models import Estagio, Intencao, Lead

    lead = Lead(id="lead-muda", nome="Marcos", estagio=Estagio.QUALIFICADO)
    lead.cartao.intencao = Intencao.ALUGUEL
    lead.cartao.bairros = ["Pinheiros"]
    lead.cartao.regiao = "zona_oeste"
    lead.cartao.preco_max = 4000
    lead.cartao.quartos = 2
    lead.cartao.urgencia = "30 dias"

    # A extração é substituída: o que está sob prova aqui é o consultor ABSORVER o cartão novo no
    # lead, não a qualidade do extrator (que tem suíte própria e, no dublê, nem olha bairro).
    def extrair_falso(cartao, mensagem, pergunta=""):
        return cartao.model_copy(update={"bairros": ["Vila Mariana", "Vila Madalena"]})

    monkeypatch.setattr("agent.nodes.qualificador._extrair", extrair_falso)
    consultor._absorver_mudanca(lead, "quero ver na Vila Mariana e na Vila Madalena")
    # "Vila Madalena" canonicaliza para "Pinheiros" no catálogo do `sdr_shared.geo` — então a
    # presença de Pinheiros aqui é a RESOLUÇÃO do bairro novo, não sobra do antigo. Afirmar a
    # ausência dele seria afirmar algo falso sobre o catálogo.
    assert "Vila Mariana" in lead.cartao.bairros, "o bairro novo precisa alimentar a busca"
    assert lead.cartao.regiao == "zona_sul", "a região acompanha o bairro novo (era zona_oeste)"
    assert lead.cartao.intencao == Intencao.ALUGUEL, "mudar de bairro não muda a intenção"


def test_mudanca_nao_derruba_o_turno(infra, monkeypatch):
    """A extração é melhoria, não pré-requisito: se ela falhar, o cliente ainda recebe imóveis."""
    from agent.nodes import consultor
    from sdr_shared.models import Estagio, Intencao, Lead

    monkeypatch.setattr("agent.nodes.qualificador._extrair",
                        lambda c, m, p="": (_ for _ in ()).throw(RuntimeError("modelo fora do ar")))
    lead = Lead(id="lead-falha", estagio=Estagio.QUALIFICADO)
    lead.cartao.intencao = Intencao.ALUGUEL
    lead.cartao.bairros = ["Pinheiros"]
    consultor._absorver_mudanca(lead, "quero na Vila Mariana")
    assert lead.cartao.bairros == ["Pinheiros"], "sem extração, segue com o cartão anterior"


def test_cartao_completo_nao_extrai_a_mesma_frase_duas_vezes(infra, monkeypatch):
    """A frase que completa o cartão passava por DUAS extrações: a do qualificador e, no mesmo
    turno, a do consultor (`_absorver_mudanca`), que relia a mesma mensagem. Uma chamada de modelo
    a mais em todo turno que completava o cartão — introduzida sem ninguém medir."""
    import agent.nodes.qualificador as q
    extracoes = []
    original = q._extrair
    monkeypatch.setattr(q, "_extrair", lambda cartao, mensagem, pergunta="":
                        extracoes.append(mensagem) or original(cartao, mensagem, pergunta))
    processar(msg("l9", "Estou procurando apartamento na zona sul", meta={"nome": "Marcos"}))
    extracoes.clear()
    processar(msg("l9", "até 800 mil, 2 quartos, é urgente"))                 # completa o cartão → consultor
    lead = LeadRepository().get("l9")
    assert lead.cartao.completo() and lead.estagio == Estagio.QUALIFICADO, "o turno passou pelo consultor"
    assert extracoes == ["até 800 mil, 2 quartos, é urgente"], "uma extração por frase, não duas"
    # No turno seguinte, que vai direto ao consultor, a frase é nova e a extração acontece.
    extracoes.clear()
    processar(msg("l9", "me mostra as opções"))
    assert extracoes == ["me mostra as opções"]


def test_historico_longo_e_podado_e_o_cartao_sobrevive(infra):
    """`add_messages` só acrescenta e o checkpointer guarda tudo: um lead de três meses mandava a
    conversa inteira ao modelo em cada turno. A poda corta o histórico; o que é durável está no
    cartão e no banco, não nele."""
    from agent.handler import get_graph
    from agent.state import MAX_HISTORICO, HISTORICO_APOS_PODA
    from agent.guardrails import vazao
    processar(msg("l8", "Estou procurando apartamento na zona sul", meta={"nome": "Marcos"}))
    for i in range(MAX_HISTORICO):
        vazao.resetar()                       # o limitador por lead não é o assunto deste teste
        processar(msg("l8", f"mensagem número {i}"))
    estado = get_graph().get_state({"configurable": {"thread_id": "l8"}}).values
    assert len(estado["messages"]) <= MAX_HISTORICO
    assert len(estado["messages"]) >= HISTORICO_APOS_PODA
    # as mais recentes ficam; as mais antigas se foram
    textos = [getattr(m, "content", "") for m in estado["messages"]]
    assert any("mensagem número 39" in t for t in textos)
    assert not any("zona sul" in t for t in textos)
    lead = LeadRepository().get("l8")
    assert lead.cartao.regiao == "zona_sul" and lead.nome == "Marcos", "o cartão não depende do histórico"


# --------------------------------------------------------------- imóveis comerciais

def test_quem_procura_sala_nao_e_perguntado_sobre_quartos(infra):
    """O bug de produto que a separação por segmento evita: até setembro/2026 `quartos` era campo
    obrigatório de toda compra/aluguel, então o cartão de um lead comercial nunca fechava e a Mora
    insistia em perguntar dormitório para quem quer uma loja."""
    from sdr_shared.models import Segmento
    processar(msg("l-com", "Procuro uma sala comercial em Pinheiros para o meu escritório"))
    lead = LeadRepository().get("l-com")
    assert lead.cartao.segmento_efetivo() == Segmento.COMERCIAL, "o tipo pedido já declara o segmento"
    assert "quartos" not in lead.cartao.campos_faltantes()
    assert "area_min" in lead.cartao.campos_faltantes(), "o tamanho se pergunta em metros quadrados"


def test_cartao_comercial_fecha_com_area_e_leva_ao_consultor(infra):
    broker, _ = infra
    processar(msg("l-com2", "Quero alugar uma loja no Tatuapé"))
    processar(msg("l-com2", "até 8 mil por mês, uns 60 metros, é urgente"))
    lead = LeadRepository().get("l-com2")
    assert lead.cartao.completo(), lead.cartao.campos_faltantes()
    assert lead.estagio == Estagio.QUALIFICADO
    r = ultima(broker)
    assert r["imoveis"], "o consultor apresentou opções sem nunca ter perguntado quartos"


def test_busca_comercial_nao_devolve_apartamento_e_vice_versa(infra):
    """Os dois lados do catálogo são estanques: quem procura sala não recebe apartamento, e quem
    procura apartamento não recebe galpão quando deixa de informar quartos."""
    from agent.tools.buscar_imoveis import buscar_com_contexto
    from sdr_shared.models import CartaoQualificacao, Intencao, segmento_do_tipo, Segmento

    comercial = CartaoQualificacao(intencao=Intencao.ALUGUEL, tipo_imovel="sala comercial",
                                   regiao="zona_oeste", preco_max=20000, area_min=30, urgencia="imediata")
    cards = buscar_com_contexto(comercial, limite=6)["cards"]
    assert cards, "o acervo tem comerciais (ver scripts/gerar_imoveis.py)"
    assert all(segmento_do_tipo(c.titulo.split()[0]) == Segmento.COMERCIAL
               or "comercial" in c.titulo.lower() or c.titulo.lower().startswith(("loja", "galpão"))
               for c in cards), [c.titulo for c in cards]

    residencial = CartaoQualificacao(intencao=Intencao.ALUGUEL, regiao="zona_oeste",
                                     preco_max=20000, urgencia="imediata")   # sem quartos de propósito
    titulos = [c.titulo for c in buscar_com_contexto(residencial, limite=6)["cards"]]
    assert titulos and not any(t.lower().startswith(("sala", "loja", "galpão", "conjunto")) for t in titulos), titulos


def test_card_de_comercial_se_mede_em_metros_nao_em_quartos(infra):
    from agent.tools.buscar_imoveis import montar_card
    from sdr_shared.models import Imovel
    sala = Imovel(id="CJ-X", tipo="sala comercial", operacao="aluguel", cidade="São Paulo",
                  regiao="zona_oeste", bairro="Pinheiros", quartos=0, suites=0, vagas=2,
                  area_m2=45, preco=4200, descricao="Sala mobiliada.")
    assert montar_card(sala).titulo == "Sala comercial 45 m² · Pinheiros"


def test_segmento_comercial_sobrevive_aos_turnos_seguintes(infra):
    """Regressão de um defeito real: `model_copy(update=...)` não roda validadores, então um
    segmento gravado por validador sumia no merge do turno seguinte e o cartão voltava a exigir
    quartos no meio de uma conversa sobre loja. Hoje o segmento é derivado no ponto de uso."""
    from sdr_shared.models import Segmento
    processar(msg("l-com3", "Quero alugar uma loja no Tatuapé"))
    processar(msg("l-com3", "é urgente"))
    processar(msg("l-com3", "até 9 mil por mês"))
    cartao = LeadRepository().get("l-com3").cartao
    assert cartao.segmento_efetivo() == Segmento.COMERCIAL
    assert "quartos" not in cartao.campos_faltantes()


# --------------------------------------------------------- a porta de volta do handoff

def _em_handoff(lead_id="l_volta", nome="Marcos"):
    from sdr_shared.models import Lead
    lead = Lead(id=lead_id, nome=nome, estagio=Estagio.HANDOFF)
    lead.cartao.intencao = Intencao.ALUGUEL
    lead.cartao.regiao = "zona_oeste"
    lead.cartao.preco_max = 3000
    lead.cartao.quartos = 2
    lead.cartao.urgencia = "imediata"
    LeadRepository().upsert(lead)
    return lead


def test_quem_caiu_no_handoff_por_engano_consegue_voltar(infra):
    """Handoff era porta de mão única: a Mora cala e o cliente não tem como pedir para voltar.

    Um "dim" — erro de digitação — encaminhou um lead de verdade a um corretor; ele perguntou
    "pode falar mais sobre o imóvel?" e não recebeu resposta de ninguém.
    """
    broker, _ = infra
    _em_handoff()
    processar(msg("l_volta", "quero continuar com a Mora", canal=Canal.WEB))
    lead = LeadRepository().get("l_volta")
    assert lead.estagio != Estagio.HANDOFF, "o cliente pediu a assistente de volta"
    assert lead.estagio == Estagio.QUALIFICADO, "cartão completo: volta já qualificado"
    assert ultima(broker, "outbound-web")["texto"], "e o turno segue: ele recebe resposta agora"


def test_mensagem_qualquer_no_handoff_nao_tira_o_lead_do_corretor(infra):
    """A porta de volta é para quem PEDE. Handoff existe porque alguém quis uma pessoa — um "oi"
    não desfaz isso."""
    _em_handoff("l_fica")
    processar(msg("l_fica", "oi, tudo bem?", canal=Canal.WEB))
    assert LeadRepository().get("l_fica").estagio == Estagio.HANDOFF


def test_no_handoff_o_cliente_recebe_um_aviso_so_e_ele_ensina_a_voltar(infra):
    """Silêncio total é o que transformava o handoff acidental em beco. Um aviso — e um só —
    diz o que esperar e como sair. Repetir a cada mensagem seria a Mora falando por cima da
    equipe."""
    broker, _ = infra
    _em_handoff("l_aviso")
    processar(msg("l_aviso", "e aí?", canal=Canal.WEB))
    aviso = ultima(broker, "outbound-web")["texto"]
    assert "continuar com a Mora" in aviso, "o aviso precisa ensinar o caminho de volta"
    antes = len([b for t, b, _ in broker.msgs if t == "outbound-web"])

    processar(msg("l_aviso", "alguém aí?", canal=Canal.WEB))
    depois = len([b for t, b, _ in broker.msgs if t == "outbound-web"])
    assert depois == antes, "o aviso é uma vez por handoff, não a cada mensagem"


def test_aviso_nao_atropela_o_corretor_que_ja_respondeu(infra):
    """Se a equipe já está na conversa, a Mora não interrompe: aí o silêncio dela é o certo."""
    broker, _ = infra
    _em_handoff("l_corretor")
    MensagemRepository().registrar("l_corretor", Canal.WEB, "corretor", "Oi! Sou a Camila, vi seu caso.")
    antes = len([b for t, b, _ in broker.msgs if t == "outbound-web"])
    processar(msg("l_corretor", "oi Camila", canal=Canal.WEB))
    depois = len([b for t, b, _ in broker.msgs if t == "outbound-web"])
    assert depois == antes, "quem está atendendo é a pessoa; a Mora fica quieta"


# --------------------------------------------------------- localização da visita

def test_reserva_manda_o_mapa_da_regiao_e_nao_promete_endereco(infra):
    """Quem vai visitar precisa saber para onde ir — e o cadastro não tem logradouro.

    Nem o acervo da Mora nem o CRM guardam endereço (o seed do CRM escreve "endereço fictício" no
    próprio título). O link é do BAIRRO, e o texto diz isso: região agora, endereço exato com o
    corretor na confirmação. Um link de rua e número seria endereço inventado chegando ao cliente
    com cara de confirmado — e ele iria até lá.
    """
    broker, _ = infra
    processar(msg("l_mapa", "Estou procurando apartamento na zona sul", meta={"nome": "Marcos"},
                  canal=Canal.WEB))
    processar(msg("l_mapa", "até 800 mil, 2 quartos, é urgente", canal=Canal.WEB))
    processar(msg("l_mapa", "me mostra as opções", canal=Canal.WEB))
    r = ultima(broker, "outbound-web")
    assert r["imoveis"], "sem card não há imóvel para visitar"

    processar(msg("l_mapa", "Agendar visita", tipo=TipoMensagem.BOTAO, canal=Canal.WEB))
    slot = ultima(broker, "outbound-web")["opcoes"][0].split("|")[0]
    processar(msg("l_mapa", slot, tipo=TipoMensagem.BOTAO, canal=Canal.WEB))
    from agent.guardrails import vazao
    vazao.resetar()                         # seis mensagens em sequência: o limitador não é o assunto aqui
    processar(msg("l_mapa", "11 98765-4321", canal=Canal.WEB))                # o contato fecha a reserva

    r = ultima(broker, "outbound-web")
    visita = r["dados"]["visita"]
    assert visita["mapa"], "o card da visita precisa do link para o botão do mapa"
    assert "google.com/maps" in visita["mapa"] and "Brooklin" in visita["mapa"].replace("%2C", ",")
    assert visita["local"].startswith("Brooklin"), "o local vem do cadastro, não do título do card"
    assert "google.com/maps" not in r["texto"], "o mapa é botão do canal; link cru no texto enterra a pergunta"
    # o link é do bairro: nada de rua, número ou CEP — que o sistema não tem
    assert not any(t in visita["mapa"].lower() for t in ("rua+", "avenida+", "cep", "n%C2%BA"))
