from sdr_shared.models import CartaoQualificacao, Intencao


def test_cartao_compra_faltantes():
    c = CartaoQualificacao(intencao=Intencao.COMPRA, regiao="zona_sul")
    assert c.campos_faltantes() == ["preco_max", "quartos", "urgencia"]


def test_cartao_investimento_completo():
    c = CartaoQualificacao(intencao=Intencao.INVESTIMENTO, perfil_investidor="moderado",
                           ticket=500_000, retorno_esperado="0.6% a.m.")
    assert c.completo()
