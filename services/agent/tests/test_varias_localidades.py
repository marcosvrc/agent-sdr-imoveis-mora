"""Cliente que pede mais de um lugar ("Tatuapé ou Tucuruvi") vê os dois — e escolhe o imóvel sem espera.

Caso real (lead web_bDoQTsrm…): o cartão guardou os dois bairros, mas a região do PRIMEIRO
(`zona_leste`) entrava junto no filtro SQL e o Tucuruvi (zona norte) sumia. A Mora respondeu
"achei duas opções em Tatuapé", com quatro imóveis do Tucuruvi no perfil sem aparecer.

Sem banco: o repositório é um dublê que aplica os mesmos filtros do SQL de `buscar_por_filtros`,
então o que se testa é a cascata e a montagem dos filtros — exatamente onde estava o defeito.
"""
import pytest

from sdr_shared.models import CartaoQualificacao, Imovel, Intencao


def _im(id, bairro, regiao, tipo, quartos, preco, operacao="aluguel"):
    return Imovel(id=id, tipo=tipo, operacao=operacao, cidade="São Paulo", regiao=regiao, bairro=bairro,
                  quartos=quartos, area_m2=30, preco=preco, descricao="")


ACERVO = [
    _im("SP-0133", "Tatuapé", "zona_leste", "kitnet", 1, 770),
    _im("SP-0240", "Tatuapé", "zona_leste", "kitnet", 1, 1220),
    _im("SP-0275", "Tatuapé", "zona_leste", "apartamento", 3, 8310),          # acima do teto
    _im("SP-0157", "Tucuruvi", "zona_norte", "kitnet", 1, 750),
    _im("SP-0124", "Tucuruvi", "zona_norte", "kitnet", 1, 940),
    _im("SP-0160", "Tucuruvi", "zona_norte", "apartamento", 1, 3940),
    _im("SP-0285", "Tucuruvi", "zona_norte", "apartamento", 3, 4860),
    _im("SP-0900", "Mooca", "zona_leste", "apartamento", 2, 3000),            # vizinho do Tatuapé
    _im("SP-0901", "Santana", "zona_norte", "apartamento", 2, 3100),          # zona norte, não pedido
]


class RepoFalso:
    """Os filtros de `ImovelRepository.buscar_por_filtros`, em memória."""
    chamadas: list[dict] = []

    def buscar_por_filtros(self, f: dict, limite: int = 5):
        RepoFalso.chamadas.append(f)
        ok = [i for i in ACERVO
              if (f.get("operacao") is None or i.operacao == f["operacao"])
              and (f.get("regiao") is None or i.regiao == f["regiao"])
              and (not f.get("bairros") or i.bairro in f["bairros"])
              and (f.get("preco_max") is None or i.preco <= f["preco_max"] * 1.15)
              and (f.get("quartos") is None or i.quartos >= f["quartos"])
              and (not f.get("tipos") or i.tipo.lower() in f["tipos"])]
        return sorted(ok, key=lambda i: (i.preco, i.id))[:limite]

    buscar_hibrido = None                                   # sem embedder: o caminho é o dos filtros


@pytest.fixture
def busca(monkeypatch):
    import agent.tools.buscar_imoveis as bi
    RepoFalso.chamadas = []
    monkeypatch.setattr(bi, "ImovelRepository", RepoFalso)
    monkeypatch.setattr(bi, "_vetor", lambda _consulta: None)
    return bi


def _cartao(bairros, regiao="zona_leste", **kw):
    return CartaoQualificacao(intencao=Intencao.ALUGUEL, bairros=bairros, regiao=regiao,
                              preco_max=5000, quartos=1, **kw)


def test_dois_bairros_de_regioes_diferentes_aparecem_os_dois(busca):
    r = busca.buscar_com_contexto(_cartao(["Tatuapé", "Tucuruvi"]), limite=6)
    assert r["nivel"] == "bairro" and r["ampliou"] is False
    assert r["bairros_encontrados"] == ["Tatuapé", "Tucuruvi"]
    assert r["bairros_sem_resultado"] == []
    assert {c.id for c in r["cards"]} == {"SP-0133", "SP-0240", "SP-0157", "SP-0124", "SP-0160", "SP-0285"}


def test_os_tres_primeiros_cards_intercalam_os_bairros(busca):
    """O consultor mostra os três primeiros: não podem sair todos de um bairro só."""
    r = busca.buscar_com_contexto(_cartao(["Tatuapé", "Tucuruvi"]), limite=6)
    primeiros = [c.titulo.split("·")[-1].strip() for c in r["cards"][:3]]
    assert set(primeiros) == {"Tatuapé", "Tucuruvi"}
    assert primeiros[:2] == ["Tatuapé", "Tucuruvi"], "na ordem em que o cliente citou"


def test_bairro_pedido_nao_leva_o_filtro_de_regiao(busca):
    """O defeito em si: bairro E região no mesmo SQL."""
    busca.buscar_com_contexto(_cartao(["Tatuapé", "Tucuruvi"]), limite=6)
    com_bairro = [f for f in RepoFalso.chamadas if f.get("bairros")]
    assert com_bairro and all(f["regiao"] is None for f in com_bairro)


def test_bairro_vazio_e_avisado_em_vez_de_sumir(busca, monkeypatch):
    sem_tucuruvi = [i for i in ACERVO if i.bairro != "Tucuruvi"]
    monkeypatch.setattr(__import__(__name__), "ACERVO", sem_tucuruvi)
    r = busca.buscar_com_contexto(_cartao(["Tatuapé", "Tucuruvi"]), limite=6)
    assert r["nivel"] == "bairro" and r["bairros_sem_resultado"] == ["Tucuruvi"]
    assert r["bairros_encontrados"] == ["Tatuapé"]

    from agent.nodes.consultor import _contexto_da_busca
    contexto = _contexto_da_busca(r, r["cards"])
    assert "Em Tucuruvi NÃO há imóvel" in contexto, contexto


def test_regiao_da_cascata_cobre_cada_bairro_pedido(busca, monkeypatch):
    """Nenhum dos dois bairros tem nada no perfil (nem os vizinhos): a cascata desce para a região
    de CADA um — zona leste e zona norte —, e não só a do primeiro."""
    import agent.tools.buscar_imoveis as bi
    monkeypatch.setattr(__import__(__name__), "ACERVO",
                        [i for i in ACERVO if i.bairro not in ("Tatuapé", "Tucuruvi")])
    monkeypatch.setattr(bi, "vizinhos", lambda _b: [])
    r = busca.buscar_com_contexto(_cartao(["Tatuapé", "Tucuruvi"]), limite=6)
    assert r["nivel"] == "regiao" and r["ampliou"] is True
    assert r["bairros_encontrados"] == ["Mooca", "Santana"]


def test_um_bairro_so_continua_como_antes(busca):
    r = busca.buscar_com_contexto(_cartao(["Tucuruvi"], regiao="zona_norte"), limite=6)
    assert r["nivel"] == "bairro" and r["bairros_encontrados"] == ["Tucuruvi"]
    assert r["bairros_sem_resultado"] == []


def test_botoes_de_escolha_nao_repetem_rotulo():
    """Dois "Kitnet 1q · Tatuapé" idênticos: o cliente escolhia sem saber qual era qual."""
    from agent.nodes.agendador import rotulo_do_imovel
    from sdr_shared.models import ImovelCard
    a = ImovelCard(id="SP-0240", titulo="Kitnet 1q · Tatuapé", preco=1220, motivo="")
    b = ImovelCard(id="SP-0133", titulo="Kitnet 1q · Tatuapé", preco=770, motivo="")
    rotulos = [rotulo_do_imovel(c, n) for n, c in enumerate([a, b], 1)]
    assert rotulos == ["1. Kitnet 1q · Tatuapé · R$ 1.220", "2. Kitnet 1q · Tatuapé · R$ 770"]


def test_grade_de_horarios_no_caso_comum_nao_chama_o_modelo(monkeypatch):
    """"Quero visitar" → grade: a frase é sempre a mesma, e o modelo custava de 1 a 7 s nela."""
    from datetime import datetime, timedelta, timezone
    import agent.nodes.agendador as ag
    from sdr_shared.models import ImovelCard, Lead

    def nao_chame():
        raise AssertionError("o caso comum da grade não deve chamar o modelo")
    monkeypatch.setattr(ag, "llm_conversa", nao_chame)
    monkeypatch.setattr(ag, "horarios_do_imovel", lambda _id: [])
    amanha = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(days=1)
    monkeypatch.setattr(ag, "listar_horarios", lambda **kw: [amanha, amanha + timedelta(hours=2)])
    card = ImovelCard(id="SP-0240", titulo="Kitnet 1q · Tatuapé", preco=1220, motivo="")
    lead = Lead(id="tg_1", nome="Camara")
    out = ag._oferecer({"imoveis_sugeridos": [card], "messages": []}, lead, "SP-0240", "imovel:SP-0240")
    r = out["resposta"]
    assert r.texto.startswith("Ótima escolha, Camara!") and "(Kitnet 1q · Tatuapé)" in r.texto
    assert len(r.opcoes) == 2 and all(o.startswith("slot:") for o in r.opcoes)
    assert out["imovel_escolhido"] == "SP-0240"


def test_horario_pedido_que_nao_existe_ainda_passa_pelo_modelo(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from langchain_core.messages import AIMessage
    import agent.nodes.agendador as ag
    from sdr_shared.models import Lead

    chamadas = []
    class Modelo:
        def invoke(self, msgs): chamadas.append(msgs); return AIMessage(content="Às 20h não tenho; que tal estes?")
    monkeypatch.setattr(ag, "llm_conversa", lambda: Modelo())
    monkeypatch.setattr(ag, "descrever_imovel", lambda *_: "o imóvel")
    monkeypatch.setattr(ag, "horarios_do_imovel", lambda _id: [])
    amanha = datetime.now(timezone.utc) + timedelta(days=1)
    monkeypatch.setattr(ag, "listar_horarios", lambda **kw: [amanha])
    estado = {"imoveis_sugeridos": [], "messages": [], "horarios_oferecidos": [amanha.isoformat()]}
    ag._oferecer(estado, Lead(id="tg_1"), "SP-0240", "pode ser às 20h?")
    assert len(chamadas) == 1, "há algo a explicar: o modelo escreve"
