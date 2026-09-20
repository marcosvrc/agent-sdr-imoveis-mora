"""A comparação de modelos da tela de configuração."""
from sdr_shared.governanca.comparacao import comparar, recomendacoes
from sdr_shared.ports.factory import _EQUIVALENTE, catalogo_de_modelos

CATALOGO = catalogo_de_modelos()


def _ordem(mix: dict) -> list[str]:
    return [l["modelo"] for l in comparar(catalogo=CATALOGO, mix=mix, latencias={}, recomendado={})]


def test_a_ordem_reage_ao_mix_quando_a_tabela_tem_razoes_diferentes():
    """O mecanismo: um modelo caro na entrada e barato na saída troca de posição conforme o papel.

    Com a tabela de preços de HOJE isso não acontece — todos os modelos mantêm a mesma ordem em
    qualquer mix, porque a razão saída/entrada varia pouco (5x a 8x) perto da distância entre os
    preços. Então a lista por papel NÃO se justifica pela ordem; ela se justifica pelo custo
    estimado e pela latência, que são por papel de verdade. O teste abaixo usa uma tabela inventada
    só para provar que a conta reage ao mix — se um dia entrar um modelo com razão extrema, a
    ordenação por papel já está certa."""
    catalogo = {"x": ["caro-na-entrada", "caro-na-saida"]}
    tabela = {"caro-na-entrada": (10.0, 1.0, 0.0, 0.0), "caro-na-saida": (1.0, 10.0, 0.0, 0.0)}
    pede = lambda e, s: [l["modelo"] for l in comparar(  # noqa: E731
        catalogo=catalogo, mix={"chamadas": 1, "entrada": e, "saida": s},
        latencias={}, recomendado={}, tabela=tabela)]
    assert pede(1_000_000, 0)[0] == "caro-na-saida"
    assert pede(0, 1_000_000)[0] == "caro-na-entrada"


def test_ordem_da_tabela_atual_e_a_mesma_em_todos_os_papeis():
    """Registra o fato acima como fato, e não como suposição: se alguém cadastrar um preço que
    quebre isso, este teste cai e a descoberta aparece em vez de passar batida."""
    pede = lambda e, s: _ordem({"chamadas": 1, "entrada": e, "saida": s})  # noqa: E731
    assert pede(1_000_000, 0) == pede(0, 1_000_000) == pede(3000, 1000)


def test_sem_uso_gravado_a_ordem_sai_do_mix_de_referencia_e_se_declara():
    linhas = comparar(catalogo=CATALOGO, mix={}, latencias={}, recomendado={})
    assert all(l["custo"]["base"] == "referencia" for l in linhas)
    assert all(l["custo"]["dias"] is None for l in linhas), "não pode dizer '30 dias' sem ter 30 dias"
    custos = [l["custo"]["usd"] for l in linhas]
    assert custos == sorted(custos), "o combo depende desta ordem"


def test_uso_gravado_vira_contrafactual_declarado_como_tal():
    mix = {"chamadas": 12, "entrada": 500_000, "saida": 100_000, "cache_escrita": 0, "cache_leitura": 0}
    linhas = comparar(catalogo=CATALOGO, mix=mix, latencias={}, recomendado={}, dias=7)
    um = next(l for l in linhas if l["modelo"] == "claude-haiku-4-5")
    # 500k entrada a 1.0 + 100k saída a 5.0 por 1M
    assert um["custo"] == {"usd": 1.0, "base": "uso", "dias": 7, "chamadas": 12}


def test_latencia_medida_entra_e_ausencia_fica_explicita():
    medida = {"claude-haiku-4-5": {"mediana_ms": 420, "amostras": 31, "escopo": "papel"}}
    linhas = comparar(catalogo=CATALOGO, mix={}, latencias=medida, recomendado={})
    por_modelo = {l["modelo"]: l["latencia"] for l in linhas}
    assert por_modelo["claude-haiku-4-5"]["mediana_ms"] == 420
    # Modelo nunca chamado não recebe número nenhum: inventar velocidade é o que esta tela não faz.
    assert por_modelo["claude-opus-4"] == {"mediana_ms": None, "amostras": 0, "escopo": None}


def test_recomendacao_sai_da_tabela_do_projeto_e_prefere_conversa():
    r = recomendacoes(_EQUIVALENTE)
    assert r["claude-sonnet-4-5"] == "conversa", "conversa e análise apontam para o mesmo modelo"
    assert r["claude-haiku-4-5"] == "roteamento"
    assert r["gpt-5.6-luna"] == "roteamento"
    assert "claude-opus-5" not in r, "o projeto não recomenda o que não escolheu"
