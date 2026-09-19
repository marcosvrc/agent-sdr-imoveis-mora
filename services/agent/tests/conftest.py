"""Testes de integração: Postgres real (pgvector) + LLM falso + broker/scheduler em memória.
Requer SDR_DATABASE_DSN apontando para um Postgres com o schema aplicado."""
import os
import json
import pytest
os.environ.setdefault("SDR_DATABASE_DSN", "postgresql://sdr:sdr@localhost:5433/sdr_test")
from sdr_shared.db.guarda_teste import exigir_banco_de_teste; exigir_banco_de_teste()   # nunca rodar contra o banco de dev
os.environ["SDR_PROFILE"] = "local"

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from sdr_shared.models import CartaoQualificacao, Intencao, AnaliseLead


class FakeLLM(FakeMessagesListChatModel):
    """Responde texto genérico; `with_structured_output` devolve um extrator por palavras-chave."""
    def __init__(self):
        super().__init__(responses=[AIMessage(content="[resposta da Mora]")])

    def with_structured_output(self, schema, **kw):
        if schema is AnaliseLead:
            return _AnaliseFake()
        return _Extractor()


class _AnaliseFake:
    def invoke(self, _msgs):
        return AnaliseLead(sentimento="positivo", engajamento="alto", perfil_decisao="objetivo", confianca=0.8,
                           estilo_comunicacao="curto e direto", motivadores=["prazo"], como_abordar=["ir direto ao ponto"], resumo_perfil="Decidido e com pressa.")


class _Extractor:
    def invoke(self, prompt: str):
        m = _mensagem_do_cliente(prompt).lower()
        c = CartaoQualificacao()
        if "investir" in m or "renda" in m: c.intencao = Intencao.INVESTIMENTO
        elif "alugar" in m: c.intencao = Intencao.ALUGUEL
        elif "apartamento" in m or "comprar" in m: c.intencao = Intencao.COMPRA
        if "zona sul" in m or "brooklin" in m: c.regiao = "zona_sul"
        if "800" in m: c.preco_max = 800000
        if "2 quartos" in m: c.quartos = 2
        if "urgente" in m or "esse mês" in m: c.urgencia = "imediata"
        if "moderado" in m: c.perfil_investidor = "moderado"
        if "500 mil" in m: c.ticket = 500000
        if "0,6%" in m or "6%" in m: c.retorno_esperado = "0,6% a.m."
        if "visitar" in m: c.pediu_visita = True
        return c


def _mensagem_do_cliente(prompt: str) -> str:
    """A mensagem do cliente vai dentro de um bloco delimitado (agent/prompts/__init__.py).
    O fake lê de lá, como o modelo real leria — e assim o teste cobre a blindagem em vez de furá-la."""
    import re
    if (m := re.search(r"<<<CLIENTE_[0-9a-f]+>>>\n(.*?)\n<<<FIM_CLIENTE_", prompt, re.S)):
        return m.group(1)
    return ""


class MemBroker:
    def __init__(self): self.msgs = []
    def publish(self, topic, body, key): self.msgs.append((topic, json.loads(body), key))
    def consume(self, *a, **k): raise NotImplementedError


class MemScheduler:
    def __init__(self): self.agendados = {}
    def schedule(self, lead_id, delay_min, payload): self.agendados[lead_id] = (delay_min, payload)
    def cancel(self, lead_id): self.agendados.pop(lead_id, None)


class FakeEmbedder:
    dimensoes = 1024
    def embed(self, texto):
        import random; random.seed(hash(texto) % 1000); return [random.random() for _ in range(1024)]


@pytest.fixture
def infra(monkeypatch):
    import agent.llm as llm
    import sdr_shared.ports.factory as f
    import agent.dispatch as d
    broker, sched = MemBroker(), MemScheduler()
    llm._modelo.cache_clear()
    monkeypatch.setattr(llm, "llm_conversa", lambda: FakeLLM())
    monkeypatch.setattr(llm, "llm_roteamento", lambda: FakeLLM())
    monkeypatch.setattr(llm, "llm_analise", lambda: FakeLLM())
    # Derivada de ESPECIALISTAS, e não escrita à mão: com a lista fixa, um nó novo ficava de fora
    # do dublê e o teste batia no modelo de verdade — falhando com um "ModuleNotFoundError" do
    # pacote do provedor em vez de dizer o que faltava. Mesma armadilha que o `strict=True` do grafo
    # resolve lá.
    from agent.graph import ESPECIALISTAS
    for mod in [f"agent.nodes.{n}" for n in (*ESPECIALISTAS, "supervisor")]:
        import importlib; m = importlib.import_module(mod)
        for fn in ("llm_conversa", "llm_roteamento", "llm_analise"):
            if hasattr(m, fn): monkeypatch.setattr(m, fn, lambda: FakeLLM())
    monkeypatch.setattr(d, "get_broker", lambda: broker); monkeypatch.setattr(d, "get_scheduler", lambda: sched)
    import sdr_shared.ports as ports
    monkeypatch.setattr(f, "get_embedder", lambda: FakeEmbedder()); monkeypatch.setattr(ports, "get_embedder", lambda: FakeEmbedder())
    import agent.handler as h
    h._graph = None
    # O limitador é estado de PROCESSO: sem zerar, a partir do 6º turno do mesmo lead no mesmo
    # arquivo os testes começam a ter as mensagens engolidas por vazão — e falham em outro lugar,
    # com outra mensagem, sem relação aparente com a causa.
    from agent.guardrails import vazao
    vazao.resetar()

    # Relógio fixo para a cadência de follow-up. `calcular()` empurra o horário para dentro da
    # janela civilizada (08:00–20:00 em São Paulo): rodando a suíte às 16h, os 240 min de um lead
    # frio caem às 20h12, fora da janela, e viram "amanhã às 8" — 947 min. O teste passava de manhã
    # e falhava à tarde, sem ninguém ter mexido em nada. Fixar um instante dentro da janela faz o
    # teste medir a POLÍTICA, não a hora em que a suíte rodou.
    from datetime import datetime
    from sdr_shared import followup as fu
    referencia = datetime.now(fu.FUSO).replace(hour=10, minute=0, second=0, microsecond=0)
    calcular_real = fu.calcular
    monkeypatch.setattr(fu, "calcular",
                        lambda feitas, temperatura="morno", agora=None:
                        calcular_real(feitas, temperatura, agora or referencia))
    return broker, sched


@pytest.fixture(autouse=True)
def seed_db():
    from sdr_shared.db import ImovelRepository, get_pool
    from sdr_shared.models import Imovel
    import pathlib
    import random
    with get_pool().connection() as c:
        for t in ("visitas", "mensagens", "canais", "followups_agendados", "eventos_navegacao", "interesses", "leads", "corretores", "uso_llm", "configuracoes"):
            c.execute(f"DELETE FROM {t}")
        for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):          # memória do LangGraph
            c.execute(f"DELETE FROM {t}") if c.execute("SELECT to_regclass(%s) AS t", (t,)).fetchone()["t"] else None
    data = pathlib.Path(__file__).parent / "fixtures/imoveis.json"
    for x in json.load(open(data, encoding="utf-8")):
        random.seed(x["id"]); ImovelRepository().upsert(Imovel(**x), [random.random() for _ in range(1024)])


@pytest.fixture
def db_limpo():
    """Tabelas de governança zeradas (uso e configurações) para testes de orçamento."""
    from sdr_shared.db import get_pool, invalidar_cache_orcamento
    with get_pool().connection() as c:
        c.execute("DELETE FROM uso_llm")
        c.execute("DELETE FROM configuracoes WHERE chave IN ('governanca', 'precos')")
    invalidar_cache_orcamento()
    yield
    with get_pool().connection() as c:
        c.execute("DELETE FROM uso_llm")
        c.execute("DELETE FROM configuracoes WHERE chave IN ('governanca', 'precos')")
    invalidar_cache_orcamento()
