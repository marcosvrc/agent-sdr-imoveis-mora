"""Fase 3 da reativação: do imóvel que entra até a mensagem que sai (e até o "não quero mais").

A régua de QUEM recebe já é testada em `shared/tests/test_reativacao.py`, com dados puros. Aqui o
que está sob teste é o encanamento: o evento, o turno pelo grafo, o carimbo que impede o segundo
aviso e a saída pedida pelo cliente. Quase todo teste deste arquivo afirma um NÃO-envio — o erro
caro da reativação não é deixar de avisar, é avisar duas vezes, ou avisar quem pediu para parar.
"""
from datetime import datetime, timedelta, timezone

import pytest

from sdr_shared.db import (CanalRepository, ImovelRepository, InteresseRepository, LeadRepository,
                           get_pool)
from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
from sdr_shared.models import CartaoQualificacao, Imovel, Intencao, Lead

NOVIDADE = dict(id="SP-9100", tipo="apartamento", operacao="venda", cidade="São Paulo", regiao="zona_sul",
                bairro="Brooklin", quartos=2, suites=1, vagas=1, area_m2=68, preco=700000,
                condominio=850, descricao="Andar alto, duas vagas.", fotos=[])


@pytest.fixture(autouse=True)
def sem_imoveis_de_teste():
    """`seed_db` recarrega os imóveis do fixture, mas não apaga os que um teste inseriu — e a
    primeira coisa que se testa aqui é justamente "esta gravação é inserção ou atualização?".
    Sem isto a suíte passa na primeira execução e falha em todas as seguintes."""
    with get_pool().connection() as c:
        c.execute("DELETE FROM imoveis WHERE id LIKE 'SP-9%'")
    yield


def _lead_adormecido(lead_id: str = "l_reat", dias: int = 30, **kw) -> Lead:
    """Lead que combina com NOVIDADE e sumiu há um mês — o alvo exato da reativação."""
    lead = LeadRepository().upsert(Lead(
        id=lead_id, nome="Marcos", telefone="5511999990000",
        cartao=CartaoQualificacao(intencao=Intencao.COMPRA, regiao="zona_sul", bairros=["Brooklin"],
                                  preco_max=800000, quartos=2, urgencia="imediata",
                                  telefone_informado="5511999990000"),
        **kw))
    CanalRepository().vincular(lead_id, "telegram", f"tg-{lead_id}")
    with get_pool().connection() as c:
        c.execute("UPDATE leads SET ultima_mensagem_em = %s WHERE id = %s",
                  (datetime.now(timezone.utc) - timedelta(days=dias), lead_id))
    return lead


@pytest.fixture
def reativador(monkeypatch, infra):
    """O worker publica pela porta do shared; o teste troca a porta por um broker de memória."""
    broker, _ = infra
    import agent.reativador as r
    monkeypatch.setattr(r, "get_broker", lambda: broker)
    return r, broker


def _entrada_de_reativacao(lead_id: str, motivos: list[str], imovel_id: str = "SP-9100") -> MensagemNormalizada:
    return MensagemNormalizada(lead_id=lead_id, canal=Canal.TELEGRAM, identificador_canal=f"tg-{lead_id}",
                               tipo=TipoMensagem.REATIVACAO, conteudo="",
                               meta={"imovel_id": imovel_id, "motivos": motivos, "pontos": 95})


# ------------------------------------------------------------------ o evento

def test_imovel_que_ja_existia_nao_gera_evento():
    """`make seed` roda toda hora. Se atualizar contasse como novidade, a base inteira seria avisada
    de novo a cada execução — o disparo em massa que a reativação existe para não ser."""
    repo = ImovelRepository()
    assert repo.upsert(Imovel(**NOVIDADE)) is True, "primeira gravação é inserção"
    assert repo.upsert(Imovel(**{**NOVIDADE, "preco": 690000})) is False, "a segunda é atualização"


def test_carga_de_catalogo_nao_vira_aviso(monkeypatch, tmp_path):
    """Uma rodada que insere dezenas de imóveis é carga, não notícia — e não anuncia nada."""
    import json
    import sdr_ingestion.ingest_imoveis as ing
    anunciados = []
    monkeypatch.setattr(ing, "embed", lambda _t: None)
    monkeypatch.setattr("agent.reativador.publicar_imovel_novo", lambda i: anunciados.append(i))

    muitos = [{**NOVIDADE, "id": f"SP-92{n:02d}"} for n in range(ing.LIMITE_AVISOS_POR_LOTE + 1)]
    arquivo = tmp_path / "imoveis.json"
    arquivo.write_text(json.dumps(muitos), encoding="utf-8")
    ing.main(str(arquivo))
    assert anunciados == [], "carga de catálogo não avisa ninguém"

    poucos = [{**NOVIDADE, "id": "SP-9301"}]
    arquivo.write_text(json.dumps(poucos), encoding="utf-8")
    ing.main(str(arquivo))
    assert anunciados == ["SP-9301"], "um imóvel novo, sim: é disso que a reativação vive"


# ---------------------------------------------------------------- a seleção

def test_anunciar_enfileira_um_turno_por_candidato(reativador):
    r, broker = reativador
    ImovelRepository().upsert(Imovel(**NOVIDADE))
    _lead_adormecido()
    _lead_adormecido("l_recente", dias=0)                     # falou hoje → cedo demais para cutucar

    resultado = r.anunciar("SP-9100")

    enfileirados = [m for m in broker.msgs if m[0] == "inbound"]
    assert resultado["avisados"] == 1 and len(enfileirados) == 1
    corpo = enfileirados[0][1]
    assert corpo["lead_id"] == "l_reat" and corpo["tipo"] == "reativacao"
    assert corpo["meta"]["imovel_id"] == "SP-9100" and corpo["meta"]["motivos"], "o motivo vira a mensagem"


def test_lead_sem_canal_aberto_nao_recebe(reativador):
    """Telefone no cadastro não é conversa aberta. Quem fala primeiro com quem nunca escreveu é o
    corretor — a Mora aparecendo do nada num número que ela nunca usou é outra coisa."""
    r, broker = reativador
    ImovelRepository().upsert(Imovel(**NOVIDADE))
    _lead_adormecido()
    with get_pool().connection() as c:
        c.execute("DELETE FROM canais WHERE lead_id = 'l_reat'")

    resultado = r.anunciar("SP-9100")
    assert resultado["avisados"] == 0 and resultado["sem_canal"] == 1
    assert not [m for m in broker.msgs if m[0] == "inbound"]


def test_imovel_apagado_entre_o_evento_e_o_consumo_nao_quebra(reativador):
    r, _ = reativador
    assert r.anunciar("SP-NAO-EXISTE")["avisados"] == 0


# -------------------------------------------------------------------- o turno

def test_turno_de_reativacao_avisa_carimba_e_registra(infra):
    from agent.handler import processar
    broker, _ = infra
    ImovelRepository().upsert(Imovel(**NOVIDADE))
    _lead_adormecido()

    processar(_entrada_de_reativacao("l_reat", ["bairro exato: Brooklin", "R$ 100 mil abaixo do teto"]))

    saida = [m for m in broker.msgs if m[0] == "outbound-telegram"]
    assert len(saida) == 1, "o aviso saiu pelo canal do lead"
    assert saida[0][1]["resposta"]["imoveis"][0]["id"] == "SP-9100", "a mensagem leva o imóvel junto"

    lead = LeadRepository().get("l_reat")
    assert lead.reativado_em is not None, "sem carimbo, a cadência não tem em que se apoiar"
    assert InteresseRepository().por_situacao("l_reat").get("sugerido") == {"SP-9100"}


def test_reativacao_nao_conta_como_atividade_do_cliente(infra):
    """`ultima_mensagem_em` é o silêncio do cliente. Se o aviso da Mora carimbasse atividade, ela
    apagaria justamente o motivo pelo qual escreveu — e o histórico ganharia uma mensagem recebida
    que ninguém mandou."""
    from agent.handler import processar
    _lead_adormecido()
    ImovelRepository().upsert(Imovel(**NOVIDADE))
    antes = LeadRepository().get("l_reat").ultima_mensagem_em

    processar(_entrada_de_reativacao("l_reat", ["bairro exato: Brooklin"]))

    assert LeadRepository().get("l_reat").ultima_mensagem_em == antes
    with get_pool().connection() as c:
        recebidas = c.execute("SELECT count(*) AS n FROM mensagens WHERE lead_id = 'l_reat' AND direcao = 'in'").fetchone()
    assert recebidas["n"] == 0


def test_turno_de_reativacao_e_contabilizado_a_parte(infra):
    """Fase 4 (métricas) precisa distinguir aviso de conversa pedida pelo cliente."""
    from agent.handler import processar
    _lead_adormecido()
    ImovelRepository().upsert(Imovel(**NOVIDADE))
    processar(_entrada_de_reativacao("l_reat", ["bairro exato: Brooklin"]))
    with get_pool().connection() as c:
        r = c.execute("SELECT resultado FROM turnos WHERE lead_id = 'l_reat' ORDER BY em DESC LIMIT 1").fetchone()
    assert r["resultado"] == "reativacao"


def test_o_mesmo_imovel_nao_e_anunciado_duas_vezes(reativador):
    """O teste que justifica o carimbo e o interesse `sugerido` existirem."""
    from agent.handler import processar
    r, _broker = reativador
    ImovelRepository().upsert(Imovel(**NOVIDADE))
    _lead_adormecido()

    assert r.anunciar("SP-9100")["avisados"] == 1
    processar(_entrada_de_reativacao("l_reat", ["bairro exato: Brooklin"]))
    segunda = r.anunciar("SP-9100")

    assert segunda["avisados"] == 0
    motivos = " ".join(e["motivo"] for e in
                       __import__("sdr_shared.reativacao", fromlist=["avaliar"]).avaliar(
                           ImovelRepository().get("SP-9100"), LeadRepository().listar(),
                           {"l_reat": InteresseRepository().por_situacao("l_reat")})["excluidos"])
    assert "últimos" in motivos or "já foi apresentado" in motivos


# --------------------------------------------------------------------- a saída

def test_cliente_pede_para_nao_receber_e_a_mora_desliga_na_hora(infra):
    from agent.handler import processar
    from agent.nodes.reativador import CONFIRMACAO_SAIDA
    broker, _ = infra
    _lead_adormecido()

    processar(MensagemNormalizada(lead_id="l_reat", canal=Canal.TELEGRAM, identificador_canal="tg-l_reat",
                                  tipo=TipoMensagem.TEXTO, conteudo="não quero mais receber avisos"))

    assert LeadRepository().get("l_reat").aceita_reativacao is False
    saida = [m for m in broker.msgs if m[0] == "outbound-telegram"][-1]
    assert saida[1]["resposta"]["texto"] == CONFIRMACAO_SAIDA, "confirmação de preferência é recibo, não texto gerado"


def test_quem_saiu_nao_recebe_o_proximo_imovel(reativador):
    from agent.handler import processar
    r, _broker = reativador
    ImovelRepository().upsert(Imovel(**NOVIDADE))
    _lead_adormecido()
    processar(MensagemNormalizada(lead_id="l_reat", canal=Canal.TELEGRAM, identificador_canal="tg-l_reat",
                                  tipo=TipoMensagem.TEXTO, conteudo="pode parar de me avisar"))
    with get_pool().connection() as c:   # a conversa acima carimbou atividade; devolve ao silêncio
        c.execute("UPDATE leads SET ultima_mensagem_em = %s WHERE id = 'l_reat'",
                  (datetime.now(timezone.utc) - timedelta(days=30),))

    assert r.anunciar("SP-9100")["avisados"] == 0
