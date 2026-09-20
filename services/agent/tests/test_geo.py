"""Calibração do RAG por localidade: o cliente escreve de qualquer jeito e a busca tem que entender."""
import pytest
from sdr_shared.geo import descrever, resolver, vizinhos
from sdr_shared.models import CartaoQualificacao, Intencao

# (o que o cliente escreve, tipo esperado, o que deve resolver)
CASOS = [
    ("Pinheiros", "bairro", "Pinheiros"), ("pinheiros", "bairro", "Pinheiros"),
    ("PINHEIROS", "bairro", "Pinheiros"), ("pinheiro", "bairro", "Pinheiros"),
    ("pinheros", "bairro", "Pinheiros"),                      # erro de digitação
    ("Tatuapé", "bairro", "Tatuapé"), ("tatuape", "bairro", "Tatuapé"),
    ("analia franco", "bairro", "Anália Franco"), ("Anália Franco", "bairro", "Anália Franco"),
    ("itaim", "bairro", "Itaim Bibi"), ("bixiga", "bairro", "Bela Vista"),
    ("Vila Madalena", "bairro", "Pinheiros"),                 # vizinho conhecido pelo apelido
    ("USP", "bairro", "Butantã"), ("ibirapuera", "bairro", "Moema"),
    ("perto do metrô Faria Lima", "bairro", "Pinheiros"),     # ponto de referência dentro da frase
    ("quero algo na zona sul", "regiao", "zona_sul"), ("zona oeste", "regiao", "zona_oeste"),
    ("centro", "regiao", "centro"),
    ("São Paulo", "cidade", "São Paulo"), ("sp", "cidade", "São Paulo"),
    ("Osasco", "fora", "Osasco"), ("quero em Alphaville", "fora", "Alphaville"),
]


@pytest.mark.parametrize("texto,tipo,esperado", CASOS)
def test_resolver_localidade(texto, tipo, esperado):
    l = resolver(texto)
    assert l.tipo == tipo, f"{texto!r} deveria ser {tipo}, veio {l.tipo}"
    alvo = l.bairros[0] if l.tipo == "bairro" else (l.regiao if l.tipo == "regiao" else l.cidade)
    assert alvo == esperado, f"{texto!r} → {alvo}, esperado {esperado}"


def test_taxa_de_acerto_minima():
    """Métrica da calibração: nenhuma forma comum de escrever um local pode ficar sem resolução."""
    acertos = sum(1 for t, tipo, _ in CASOS if resolver(t).tipo == tipo)
    assert acertos == len(CASOS), f"{acertos}/{len(CASOS)} — a calibração regrediu"


def test_desconhecido_nao_inventa():
    l = resolver("xpto lugar nenhum")
    assert l.tipo == "desconhecido" and not l.bairros          # melhor não saber do que chutar bairro


def test_vizinhos_sao_da_mesma_regiao():
    from sdr_shared.geo import BAIRROS
    for b in ("Pinheiros", "Moema", "Tatuapé"):
        assert vizinhos(b) and all(BAIRROS[v]["regiao"] == BAIRROS[b]["regiao"] for v in vizinhos(b))
    assert descrever(resolver("zona sul")) == "zona sul"


def test_cascata_do_bairro_ate_a_cidade(infra):
    """Bairro com estoque responde no bairro; sem estoque, desce a cascata avisando o nível."""
    from agent.tools.buscar_imoveis import buscar_com_contexto

    # a fixture tem SP-0002 (aluguel, Pinheiros, 1q, 3800)
    exato = CartaoQualificacao(intencao=Intencao.ALUGUEL, bairros=["pinheiro"], preco_max=5000, quartos=1)
    r = buscar_com_contexto(exato, limite=5)
    assert r["nivel"] == "bairro" and r["ampliou"] is False
    assert all("Pinheiros" in c.titulo for c in r["cards"])

    # ponto de referência resolve para o mesmo bairro
    ref = CartaoQualificacao(intencao=Intencao.ALUGUEL, bairros=["perto da Faria Lima"], preco_max=5000, quartos=1)
    assert buscar_com_contexto(ref, limite=5)["bairros_encontrados"] == ["Pinheiros"]

    # bairro sem estoque no perfil: desce a cascata e sinaliza que ampliou
    sem = CartaoQualificacao(intencao=Intencao.ALUGUEL, bairros=["Tatuapé"], preco_max=5000, quartos=1)
    r2 = buscar_com_contexto(sem, limite=5)
    assert r2["nivel"] in ("vizinhos", "regiao", "cidade", "vazio")
    if r2["cards"]:
        assert r2["ampliou"] is True                            # nunca apresenta outro bairro como se fosse o pedido


def test_local_fora_de_cobertura_nao_vira_bairro():
    from agent.nodes.qualificador import _normalizar_local
    cartao, fora = _normalizar_local(CartaoQualificacao(bairros=["Osasco"]), "quero em Osasco")
    assert fora == "Osasco" and cartao.bairros == [] and cartao.regiao is None
    cartao2, fora2 = _normalizar_local(CartaoQualificacao(bairros=["Vila Madalena"]), "")
    assert fora2 is None and cartao2.bairros == ["Pinheiros"] and cartao2.regiao == "zona_oeste"


def test_a_cascata_inteira_calcula_um_embedding_so(infra, monkeypatch):
    """Bairro sem estoque desce até a cidade e ainda tenta as alternativas: até seis buscas com a
    MESMA consulta. Cada uma ia ao Ollama pelo mesmo vetor."""
    import agent.tools.buscar_imoveis as bi
    import sdr_shared.ports as ports
    vezes = []
    real = ports.get_embedder()

    class Contador:
        dimensoes = real.dimensoes
        def embed(self, texto): vezes.append(texto); return real.embed(texto)
    monkeypatch.setattr(ports, "get_embedder", lambda: Contador())
    sem = CartaoQualificacao(intencao=Intencao.ALUGUEL, bairros=["Tatuapé"], preco_max=5000, quartos=1)
    r = bi.buscar_com_contexto(sem, limite=5)
    assert r["nivel"] != "bairro", "o cenário precisa descer a cascata"
    assert len(vezes) == 1, vezes
