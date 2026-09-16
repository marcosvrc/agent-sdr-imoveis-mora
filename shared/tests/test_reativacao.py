"""Casamento imóvel novo → leads antigos.

Estes testes são sobre JULGAMENTO, não sobre encanamento: o que conta como notícia boa o bastante
para interromper alguém que não fala com a gente há semanas. Por isso quase todos afirmam uma
exclusão — o erro caro aqui não é deixar de avisar, é avisar quem não queria.
"""
from datetime import datetime, timedelta, timezone

from sdr_shared.models import CartaoQualificacao, Imovel, Intencao, Lead, Estagio
from sdr_shared.reativacao import DIAS_ENTRE_REATIVACOES, DIAS_SILENCIO, avaliar, elegivel, pontuar

AGORA = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def imovel(**kw) -> Imovel:
    base = dict(id="SP-9001", tipo="apartamento", operacao="venda", cidade="São Paulo",
                regiao="zona_sul", bairro="Brooklin", quartos=2, suites=1, vagas=1,
                area_m2=68, preco=760000, condominio=900, descricao="Andar alto, varanda.")
    return Imovel(**{**base, **kw})


def lead(**kw) -> Lead:
    cartao = kw.pop("cartao", CartaoQualificacao(
        intencao=Intencao.COMPRA, regiao="zona_sul", bairros=["Brooklin"],
        preco_max=800000, quartos=2, urgencia="imediata", telefone_informado="11999990000"))
    base = dict(id="l1", nome="Marcos", telefone="11999990000",
                ultima_mensagem_em=AGORA - timedelta(days=30))
    return Lead(**{**base, **kw}, cartao=cartao)


# ---------------------------------------------------------------- pontuação

def test_imovel_que_bate_no_bairro_e_abaixo_do_teto_pontua_alto():
    pontos, motivos = pontuar(lead(), imovel())
    assert pontos >= 90
    texto = " ".join(motivos)
    assert "Brooklin" in texto and "abaixo do teto" in texto, "o motivo vira a primeira frase da mensagem"


def test_eliminatorios_zeram_e_explicam():
    """Preço, quartos, operação e tipo não são 'peso': errá-los transforma notícia em incômodo."""
    exigente = lead(cartao=CartaoQualificacao(
        intencao=Intencao.COMPRA, regiao="zona_sul", bairros=["Brooklin"], preco_max=800000,
        quartos=2, tipo_imovel="apartamento", telefone_informado="11999990000"))
    casos = [
        (imovel(preco=900000), "acima do teto"),
        (imovel(quartos=1), "quarto"),
        (imovel(operacao="aluguel"), "procura venda"),
        (imovel(tipo="casa"), "é casa"),
    ]
    for im, esperado in casos:
        pontos, motivos = pontuar(exigente, im)
        assert pontos == 0, f"{im.id} deveria ser eliminado"
        assert esperado in " ".join(motivos)

    # Sem tipo pedido, qualquer tipo serve — não é eliminatório por omissão.
    assert pontuar(lead(), imovel(tipo="casa"))[0] > 0


def test_fora_do_bairro_pontua_menos_que_dentro():
    dentro, _ = pontuar(lead(), imovel(bairro="Brooklin"))
    mesma_regiao, _ = pontuar(lead(), imovel(bairro="Moema"))
    outra_regiao, _ = pontuar(lead(), imovel(bairro="Santana", regiao="zona_norte"))
    assert dentro > mesma_regiao > outra_regiao


def test_investidor_procura_venda_e_ganha_com_o_selo():
    investidor = lead(cartao=CartaoQualificacao(intencao=Intencao.INVESTIMENTO, regiao="zona_sul",
                                                preco_max=800000, telefone_informado="11999990000"))
    com_selo, motivos = pontuar(investidor, imovel(destaque_investimento=True))
    sem_selo, _ = pontuar(investidor, imovel())
    assert com_selo > sem_selo and "investir" in " ".join(motivos)
    assert pontuar(investidor, imovel(operacao="aluguel"))[0] == 0, "investidor procura imóvel à venda"


def test_cartao_sem_intencao_nao_vira_candidato():
    indefinido = lead(cartao=CartaoQualificacao(preco_max=800000, telefone_informado="11999990000"))
    assert pontuar(indefinido, imovel())[0] == 0


# -------------------------------------------------------------- elegibilidade

def test_quem_nao_pode_receber_e_por_que():
    casos = [
        (lead(aceita_reativacao=False), {}, "pediu para não receber"),
        (lead(encerrado_em=AGORA), {}, "encerrada"),
        (lead(estagio=Estagio.HANDOFF), {}, "já está com um corretor"),
        (lead(reativado_em=AGORA - timedelta(days=DIAS_ENTRE_REATIVACOES - 1)), {}, "últimos"),
        (lead(ultima_mensagem_em=AGORA - timedelta(days=DIAS_SILENCIO - 1)), {}, "menos de"),
        (lead(), {"descartado": {"SP-9001"}}, "já descartou"),
        (lead(), {"sugerido": {"SP-9001"}}, "já foi apresentado"),
        (lead(), {"visita_marcada": {"SP-9001"}}, "já tem visita"),
    ]
    for l, conhecidos, esperado in casos:
        motivo = elegivel(l, "SP-9001", conhecidos, agora=AGORA)
        assert motivo and esperado in motivo, f"esperava '{esperado}', veio '{motivo}'"


def test_lead_sem_contato_nao_e_avisado():
    sem_contato = Lead(id="l_mudo", cartao=CartaoQualificacao(intencao=Intencao.COMPRA))
    assert elegivel(sem_contato, "SP-9001", {}, agora=AGORA) == "sem canal de contato"


def test_lead_antigo_e_silencioso_pode_receber():
    assert elegivel(lead(), "SP-9001", {"sugerido": {"SP-0002"}}, agora=AGORA) is None


# ------------------------------------------------------------------ avaliação

def test_avaliar_separa_candidatos_de_excluidos_com_motivo():
    im = imovel()
    leads = [
        lead(id="l_bom"),
        lead(id="l_caro", cartao=CartaoQualificacao(intencao=Intencao.COMPRA, preco_max=500000,
                                                    telefone_informado="11999990000")),
        lead(id="l_optout", aceita_reativacao=False),
        lead(id="l_recente", ultima_mensagem_em=AGORA - timedelta(hours=2)),
    ]
    r = avaliar(im, leads, {"l_bom": {}, "l_caro": {}, "l_optout": {}, "l_recente": {}}, agora=AGORA)

    assert [c["lead_id"] for c in r["candidatos"]] == ["l_bom"]
    assert r["avaliados"] == 4 and len(r["excluidos"]) == 3
    fora = {e["lead_id"]: e["motivo"] for e in r["excluidos"]}
    assert "teto" in fora["l_caro"] and "não receber" in fora["l_optout"] and "menos de" in fora["l_recente"]


def test_candidatos_saem_ordenados_por_aderencia():
    im = imovel()
    perto = lead(id="l_perto")
    longe = lead(id="l_longe", cartao=CartaoQualificacao(
        intencao=Intencao.COMPRA, regiao="zona_norte", preco_max=800000, quartos=2,
        telefone_informado="11999990000"))
    r = avaliar(im, [longe, perto], {"l_perto": {}, "l_longe": {}}, agora=AGORA)
    ids = [c["lead_id"] for c in r["candidatos"]]
    assert ids[0] == "l_perto", "quem pediu o bairro exato vem antes de quem pediu outra região"
