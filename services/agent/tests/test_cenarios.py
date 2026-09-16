"""Os três cenários do desafio, ponta a ponta: compra, investimento e follow-up."""
from sdr_shared.messaging import MensagemNormalizada, Canal, TipoMensagem
from sdr_shared.models import Estagio, Intencao, Temperatura
from sdr_shared.db import LeadRepository, MensagemRepository, VisitaRepository
from agent.handler import processar


def msg(lead, texto, tipo=TipoMensagem.TEXTO, meta=None, canal=Canal.WHATSAPP):
    return MensagemNormalizada(lead_id=lead, canal=canal, identificador_canal="5511999990000", tipo=tipo, conteudo=texto, meta=meta or {})


def ultima(broker, topic="outbound-whatsapp"):
    return [b for t, b, _ in broker.msgs if t == topic][-1]["resposta"]


def test_cenario_compra(infra):
    broker, sched = infra
    processar(msg("l1", "Estou procurando apartamento na zona sul", meta={"nome": "Marcos"}))
    lead = LeadRepository().get("l1")
    assert lead.cartao.intencao == Intencao.COMPRA and lead.cartao.regiao == "zona_sul"
    assert lead.estagio == Estagio.QUALIFICANDO
    assert ultima(broker)["texto"] == "[resposta da Mora]"
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
    processar(msg("l2", "ok, aguardo"))                                      # em handoff o agente fica em silêncio
    assert ultima(broker)["acao"] == "handoff"                               # nenhuma resposta nova
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
