"""O follow-up retoma de onde a conversa parou, oferece resposta de um toque e deixa o cliente sair.

Caso real: lead parado na pergunta do bairro recebeu "você prefere mobiliado ou sem mobília?" —
um atributo que o cartão não guarda e a busca não filtra. Agora o texto é fixo e decidido no
código; o modelo, se chamado, derruba o teste. Sem banco: auditoria e política são dublês.
"""

import pytest
from langchain_core.messages import AIMessage

from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
from sdr_shared.models import CartaoQualificacao, Estagio, ImovelCard, Intencao, Lead


@pytest.fixture(autouse=True)
def seed_db():
    """Substitui o `seed_db` do conftest: este arquivo não toca banco."""
    yield


@pytest.fixture
def fu(monkeypatch):
    import agent.nodes.followup as fu
    import agent.llm as llm

    def nao_chame(*_a, **_k):
        raise AssertionError("o follow-up é texto fixo: não chama modelo")
    for nome in llm.ACESSORES:
        monkeypatch.setattr(llm, nome, nao_chame)
    monkeypatch.setattr(fu, "auditar", lambda **kw: None)
    monkeypatch.setattr(fu.politica_followup, "politica_cacheada", lambda: {"tempos_min": [5, 10, 15]})
    monkeypatch.setattr(fu, "_imovel_novo", lambda *_: None)
    return fu


def _estado(lead, conteudo="", mensagens=None, **extra):
    entrada = MensagemNormalizada(lead_id=lead.id, canal=Canal.TELEGRAM, identificador_canal="555",
                                  tipo=TipoMensagem.FOLLOWUP if not conteudo else TipoMensagem.BOTAO,
                                  conteudo=conteudo)
    return {"lead": lead, "entrada": entrada, "messages": mensagens or [], **extra}


def _lead_sem_regiao(**kw):
    return Lead(id="tg_1", nome="Marcos", estagio=Estagio.QUALIFICANDO,
                cartao=CartaoQualificacao(intencao=Intencao.ALUGUEL), **kw)


PERGUNTA_DO_BAIRRO = [("user", "Alugar"),
                      AIMessage(content="Só me falta saber onde: em que região ou bairro de São Paulo?")]


def test_primeira_tentativa_retoma_a_pergunta_que_ficou_sem_resposta(fu):
    out = fu.run(_estado(_lead_sem_regiao(), mensagens=PERGUNTA_DO_BAIRRO))
    r = out["resposta"]
    assert r.texto == "Oi, Marcos! Ficou faltando só a região para eu te mostrar os imóveis para alugar. Onde você prefere?"
    assert r.opcoes[:5] == ["Zona Sul", "Zona Oeste", "Zona Leste", "Zona Norte", "Centro"]
    assert r.opcoes[-1] == fu.ENCONTREI
    assert out["lead"].estagio == Estagio.INATIVO and out["lead"].followups_enviados == 1


def test_nunca_pergunta_o_que_ja_foi_respondido_nem_o_que_o_sistema_nao_guarda(fu):
    texto = fu.run(_estado(_lead_sem_regiao(), mensagens=PERGUNTA_DO_BAIRRO))["resposta"].texto
    assert "alugar ou investir" not in texto, "ele já disse que quer alugar"
    assert "mobília" not in texto and "mobiliado" not in texto


def test_segunda_tentativa_facilita_com_os_botoes(fu):
    r = fu.run(_estado(_lead_sem_regiao(followups_enviados=1)))["resposta"]
    assert r.texto.startswith("Marcos, se ficar mais fácil") and "Zona Leste" in r.opcoes


def test_sem_nome_a_frase_continua_natural(fu):
    lead = Lead(id="tg_1", cartao=CartaoQualificacao(intencao=Intencao.ALUGUEL), followups_enviados=1)
    assert fu.run(_estado(lead))["resposta"].texto.startswith("Se ficar mais fácil")
    assert fu.run(_estado(Lead(id="tg_2", cartao=CartaoQualificacao(intencao=Intencao.ALUGUEL))))[
        "resposta"].texto.startswith("Oi! Ficou faltando")


def test_cada_campo_que_falta_tem_sua_frase_e_seus_botoes(fu):
    lead = Lead(id="tg_1", nome="Ana", cartao=CartaoQualificacao(intencao=Intencao.ALUGUEL, regiao="zona_leste"))
    r = fu.run(_estado(lead))["resposta"]
    assert "até quanto você pensa em pagar por mês" in r.texto and "por mês" in r.opcoes[0]
    compra = Lead(id="tg_2", cartao=CartaoQualificacao(intencao=Intencao.COMPRA, regiao="zona_leste"))
    r2 = fu.run(_estado(compra))["resposta"]
    assert "por mês" not in r2.texto and "milh" in r2.opcoes[1]


def test_ultima_tentativa_se_despede_sem_pergunta(fu):
    out = fu.run(_estado(_lead_sem_regiao(followups_enviados=2), mensagens=PERGUNTA_DO_BAIRRO))
    assert "?" not in out["resposta"].texto
    assert out["resposta"].opcoes == [fu.CONTINUAR, fu.ENCONTREI]
    assert out["lead"].estagio == Estagio.FRIO


def test_quem_viu_imoveis_e_perguntado_sobre_eles(fu):
    cards = [ImovelCard(id="SP-0240", titulo="Kitnet 1q · Tatuapé", preco=1220, motivo="")]
    lead = Lead(id="tg_1", nome="Marcos", cartao=CartaoQualificacao(
        intencao=Intencao.ALUGUEL, regiao="zona_leste", preco_max=4000, quartos=1, urgencia="sem_prazo"))
    r = fu.run(_estado(lead, imoveis_sugeridos=cards, ultimos_sugeridos=["SP-0240"]))["resposta"]
    assert r.texto.startswith("Oi, Marcos! O imóvel que te mostrei chamou sua atenção?")
    assert r.opcoes[0] == "Agendar visita"


def test_imovel_novo_vai_como_card_e_vira_o_lote_da_tela(fu, monkeypatch):
    novo = ImovelCard(id="SP-0157", titulo="Kitnet 1q · Tucuruvi", preco=750, motivo="")
    monkeypatch.setattr(fu, "_imovel_novo", lambda *_: novo)
    lead = Lead(id="tg_1", followups_enviados=1,
                cartao=CartaoQualificacao(intencao=Intencao.ALUGUEL, regiao="zona_leste", preco_max=4000,
                                          quartos=1, urgencia="sem_prazo"))
    out = fu.run(_estado(lead))
    assert out["resposta"].imoveis == [novo] and out["ultimos_sugeridos"] == ["SP-0157"]
    assert out["resposta"].texto.startswith("Entrou um imóvel no seu perfil")


@pytest.mark.parametrize("botao,trecho", [("followup:encontrei", "deu certo"), ("followup:depois", "Não vou mais")])
def test_ja_encontrei_e_agora_nao_encerram_sem_chamar_o_modelo(fu, botao, trecho):
    out = fu.run(_estado(_lead_sem_regiao(), conteudo=botao))
    assert out["lead"].estagio == Estagio.FRIO, "FRIO é o que faz o handler cancelar a fila"
    assert trecho in out["resposta"].texto


def test_supervisor_leva_o_botao_de_saida_ao_followup():
    from agent.nodes import supervisor
    estado = _estado(_lead_sem_regiao(), conteudo="followup:encontrei")
    assert supervisor.run(estado)["proximo"] == "followup"


@pytest.mark.parametrize("estagio", [Estagio.INATIVO, Estagio.FRIO])
def test_cliente_que_responde_volta_a_conversa_e_a_cadencia_zera(estagio):
    from agent.handler import _voltou_a_conversar
    lead = _lead_sem_regiao(followups_enviados=2)
    lead.estagio = estagio
    _voltou_a_conversar(lead)
    assert lead.estagio == Estagio.QUALIFICANDO and lead.followups_enviados == 0


def test_lead_agendado_nao_e_mexido():
    from agent.handler import _voltou_a_conversar
    lead = _lead_sem_regiao(followups_enviados=1)
    lead.estagio = Estagio.AGENDADO
    _voltou_a_conversar(lead)
    assert lead.estagio == Estagio.AGENDADO and lead.followups_enviados == 1
