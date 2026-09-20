import os
import json
os.environ.setdefault("SDR_DATABASE_DSN", "postgresql://sdr:sdr@localhost:5433/sdr_test")
from sdr_shared.db.guarda_teste import exigir_banco_de_teste; exigir_banco_de_teste()   # nunca rodar contra o banco de dev
os.environ["SDR_PROFILE"] = "local"
import pytest
from fastapi.testclient import TestClient
from api.main import app
import api.routers.handoff as h

H = {"Authorization": "Bearer dev-token"}


@pytest.fixture(autouse=True)
def relogio_da_cadencia(monkeypatch):
    """Congela o relógio da cadência de follow-up dentro da janela civilizada (08:00–20:00 em SP).

    `previa()` empurra o horário para dentro dessa janela: rodando a suíte de madrugada, os 30 min de
    um lead quente viram 476, e o teste falha pela hora em que alguém o rodou — não pelo código. Com
    o instante fixo, o que está sob teste é a POLÍTICA. (Mesmo tratamento do conftest do agente.)"""
    from datetime import datetime
    from sdr_shared import followup as fu
    referencia = datetime.now(fu.FUSO).replace(hour=10, minute=0, second=0, microsecond=0)
    previa_real, calcular_real = fu.previa, fu.calcular
    monkeypatch.setattr(fu, "previa",
                        lambda temperatura="morno", agora=None: previa_real(temperatura, agora or referencia))
    monkeypatch.setattr(fu, "calcular",
                        lambda feitas, temperatura="morno", agora=None: calcular_real(feitas, temperatura, agora or referencia))


class MemBroker:
    msgs = []
    def publish(self, topic, body, key): self.msgs.append((topic, json.loads(body)))


class MemSched:
    def cancel(self, lead_id): pass


def setup_module(m):
    from sdr_shared.db import ImovelRepository, LeadRepository, CanalRepository, get_pool
    from sdr_shared.models import Imovel, Lead
    import pathlib
    with get_pool().connection() as c:
        # `uso_llm`, `turnos`, `saude` e `batimentos` entram aqui porque os testes de comparação de
        # modelos e de saúde INSEREM nessas tabelas: sem limpar, a segunda execução da suíte começa
        # com o estado da primeira, e o teste que afirma "ainda não há uso gravado" falha. Vermelho
        # que depende de quantas vezes alguém rodou a suíte, não do código.
        for t in ("visitas", "mensagens", "canais", "followups_agendados", "eventos_navegacao", "leads",
                  "corretores", "configuracoes", "imoveis", "uso_llm", "turnos", "saude", "batimentos"):
            c.execute(f"DELETE FROM {t}")
    data = pathlib.Path(__file__).parents[2] / "agent/tests/fixtures/imoveis.json"
    for x in json.load(open(data, encoding="utf-8")):
        ImovelRepository().upsert(Imovel(**x))
    LeadRepository().upsert(Lead(id="l1", nome="Marcos", telefone="5511999990000"))
    CanalRepository().vincular("l1", "telegram", "5511999990000")
    h.get_broker, h.get_scheduler = lambda: MemBroker(), lambda: MemSched()


def test_publico():
    c = TestClient(app)
    assert c.get("/health").json()["agente"] == "Mora"
    assert len(c.get("/imoveis", params={"operacao": "venda", "regiao": "zona_sul"}).json()) == 2
    assert c.get("/imoveis/SP-0001").json()["bairro"] == "Brooklin"
    assert c.get("/imoveis/NAO-EXISTE").status_code == 404
    assert c.post("/eventos", json={"session_id": "sess-123", "tipo": "viewed_imovel", "dados": {"imovel_id": "SP-0001"}}).status_code == 202


def test_corretor_auth_e_handoff():
    c = TestClient(app)
    assert c.get("/leads").status_code == 401
    assert c.get("/leads", headers=H).json()[0]["id"] == "l1"
    assert c.get("/dashboard/funil", headers=H).json()["estagios"]["novo"] == 1
    r = c.post("/handoff/l1/assumir", headers=H).json()
    # Sem nenhum corretor no cadastro, o lead fica na fila da equipe. Antes gravava aqui o id do
    # usuário logado ("corretor-dev"), que não existe em `corretores` — lead atribuído a um fantasma.
    assert r["estagio"] == "handoff" and r["corretor_id"] is None
    r = c.post("/handoff/l1/responder", headers=H, json={"texto": "Oi Marcos, aqui é o corretor"})
    assert r.json()["canais"] == ["telegram"] and MemBroker.msgs[-1][0] == "outbound-telegram"
    assert c.get("/leads/l1/mensagens", headers=H).json()[-1]["direcao"] == "corretor"
    assert c.post("/handoff/l1/devolver", headers=H).json()["estagio"] == "qualificando"
    assert c.post("/leads/crm/sync", headers=H).json()["exportados"] == 0
    import api.routers.leads as lr
    lr.get_broker = lambda: MemBroker()
    assert c.post("/leads/l1/analisar", headers=H).status_code == 202 and MemBroker.msgs[-1][0] == "resumir"
    assert c.post("/leads/nao-existe/analisar", headers=H).status_code == 404


def test_painel_admin():
    c = TestClient(app)
    # métricas: estrutura completa e coerente com o seed (1 lead, 3 imóveis)
    m = c.get("/dashboard/metricas", headers=H, params={"dias": 7}).json()
    assert m["periodo_dias"] == 7 and set(m["kpis"]) >= {"leads", "qualificados", "visitas", "handoffs", "msgs_in", "msgs_out", "resposta_seg"}
    assert m["kpis"]["leads"]["atual"] == 1 and len(m["serie"]) == 7 and m["totais"]["imoveis"] == 3
    assert "por_canal" in m and m["por_canal"].get("telegram") == 1
    assert c.get("/dashboard/metricas", headers=H, params={"dias": 0}).status_code == 422

    # corretores: CRUD + carga
    assert c.get("/corretores").status_code == 401
    r = c.post("/corretores", headers=H, json={"nome": "Ana Souza", "email": "ana@verticeimoveis.com.br", "regioes": ["zona_sul"]})
    assert r.status_code == 201 and r.json()["id"] == "cor_ana-souza"
    assert c.post("/corretores", headers=H, json={"nome": "Ana Souza"}).status_code == 409
    assert c.post("/corretores", headers=H, json={"nome": "A"}).status_code == 422
    lista = c.get("/corretores", headers=H).json()
    assert [x["nome"] for x in lista] == ["Ana Souza"] and lista[0]["leads_handoff"] == 0
    foto = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    assert c.put("/corretores/cor_ana-souza", headers=H, json={"nome": "Ana Souza", "regioes": ["zona_sul", "centro"], "ativo": False, "foto": foto}).json()["ativo"] is False
    assert c.get("/corretores", headers=H).json()[0]["foto"] == foto
    assert c.put("/corretores/cor_ana-souza", headers=H, json={"nome": "Ana Souza", "foto": "data:text/plain;base64,QUJD"}).status_code == 422
    # DELETE desativa (204 virou 200 com corpo): o cadastro fica, marcado como inativo, porque
    # apagar levaria junto o histórico de quem atendeu quem. Sem carteira aberta, não pede destino.
    r = c.delete("/corretores/cor_ana-souza", headers=H)
    assert r.status_code == 200 and r.json()["acao"] == "desativado"
    inativa = next(x for x in c.get("/corretores", headers=H).json() if x["id"] == "cor_ana-souza")
    assert inativa["ativo"] is False
    # Desativar de novo é idempotente; 404 fica para id que nunca existiu.
    assert c.delete("/corretores/cor_ana-souza", headers=H).status_code == 200
    assert c.delete("/corretores/cor_nao-existe", headers=H).status_code == 404

    # config: defaults + override + restaurar
    cfg = c.get("/config", headers=H).json()
    assert cfg["config"]["followup"]["tempos_min"] == [120, 1440, 4320] and cfg["canais"]["web"]["configurado"] is True
    assert c.put("/config/followup", headers=H, json={"tempos_min": [30, 90]}).json()["valor"]["tempos_min"] == [30, 90]
    assert c.get("/config", headers=H).json()["config"]["followup"]["tempos_min"] == [30, 90]
    assert c.put("/config/followup", headers=H, json={"inexistente": 1}).status_code == 422
    assert c.put("/config/followup", headers=H, json={"tempos_min": [2]}).status_code == 422      # curto demais
    assert c.put("/config/nada", headers=H, json={}).status_code == 404
    assert c.delete("/config/followup", headers=H).status_code == 204
    assert c.get("/config", headers=H).json()["config"]["followup"]["tempos_min"] == [120, 1440, 4320]

    # configuração salva no formato antigo não pode virar erro nem sumir
    from sdr_shared.db import ConfigRepository
    ConfigRepository().salvar("followup", {"primeiro_min": 30, "segundo_h": 2, "terceiro_h": 8, "maximo": 2})
    assert c.get("/config", headers=H).json()["config"]["followup"]["tempos_min"] == [30, 120]
    assert c.put("/config/followup", headers=H, json={"primeiro_min": 45, "segundo_h": 3, "terceiro_h": 9}).status_code == 200
    assert c.get("/config", headers=H).json()["config"]["followup"]["tempos_min"] == [45, 180, 540]
    assert c.delete("/config/followup", headers=H).status_code == 204

    # prévia: o painel mostra quando cada tentativa cairia com o que está salvo
    previa = c.get("/config/followup/previa", headers=H, params={"temperatura": "quente"}).json()
    assert [p["tentativa"] for p in previa["previa"]] == [1, 2, 3]
    assert previa["previa"][0]["minutos"] == 30, "lead quente volta antes (120 × 0,25)"


def test_fotos_imovel(tmp_path, monkeypatch):
    from sdr_shared.config import get_settings
    monkeypatch.setattr(get_settings(), "fotos_dir", str(tmp_path))
    c = TestClient(app)
    png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    assert c.post("/imoveis/SP-0001/fotos", json={"imagem": png}).status_code == 401          # exige corretor
    r = c.post("/imoveis/SP-0001/fotos", headers=H, json={"imagem": png})
    assert r.status_code == 201
    fotos = r.json()["fotos"]
    assert fotos[-1].startswith("http://testserver/fotos/SP-0001/") and fotos[-1].endswith(".png")
    nome = fotos[-1].rsplit("/", 1)[1]
    assert (tmp_path / "SP-0001" / nome).exists()
    assert c.get(f"/fotos/SP-0001/{nome}").status_code == 200                                    # servida pela API
    assert c.get("/imoveis/SP-0001").json()["fotos"][-1] == fotos[-1]                             # URL absoluta na leitura pública
    assert c.post("/imoveis/SP-0001/fotos", headers=H, json={"imagem": "data:text/plain;base64,QUJD"}).status_code == 422
    assert c.post("/imoveis/NAO-EXISTE/fotos", headers=H, json={"imagem": png}).status_code == 404
    # reordenar: nova foto vira capa
    r = c.put("/imoveis/SP-0001/fotos", headers=H, json={"fotos": list(reversed(fotos))})
    assert r.status_code == 200 and r.json()["fotos"][0] == fotos[-1]
    assert c.put("/imoveis/SP-0001/fotos", headers=H, json={"fotos": fotos[:1]}).status_code == 422
    # remover
    assert c.delete(f"/imoveis/SP-0001/fotos/{nome}", headers=H).status_code == 200
    assert not (tmp_path / "SP-0001" / nome).exists()
    assert c.delete(f"/imoveis/SP-0001/fotos/{nome}", headers=H).status_code == 404


def test_lead_corretor():
    c = TestClient(app)
    # PUT em vez de confiar no POST: o cadastro pode ter sobrado inativo de outro teste, e desde que
    # DELETE desativa (não apaga), um POST repetido devolve 409 e deixaria Ana inativa aqui.
    c.post("/corretores", headers=H, json={"nome": "Ana Souza", "regioes": ["zona_sul"]})
    c.put("/corretores/cor_ana-souza", headers=H, json={"nome": "Ana Souza", "regioes": ["zona_sul"], "ativo": True})
    c.post("/corretores", headers=H, json={"nome": "Bia Reis", "regioes": [], "ativo": False})
    c.put("/corretores/cor_bia-reis", headers=H, json={"nome": "Bia Reis", "regioes": [], "ativo": False})
    # atribuição manual + nome na listagem/detalhe
    assert c.put("/leads/l1/corretor", headers=H, json={"corretor_id": "cor_ana-souza"}).json()["corretor_nome"] == "Ana Souza"
    assert c.get("/leads/l1", headers=H).json()["corretor_nome"] == "Ana Souza"
    assert [l["id"] for l in c.get("/leads", headers=H, params={"corretor_id": "cor_ana-souza"}).json()] == ["l1"]
    assert c.get("/corretores", headers=H).json()[0]["leads_handoff"] in (0, 1)
    assert c.put("/leads/l1/corretor", headers=H, json={"corretor_id": "cor_bia-reis"}).status_code == 422     # inativa
    assert c.put("/leads/l1/corretor", headers=H, json={"corretor_id": "nao-existe"}).status_code == 422
    assert c.put("/leads/nao-existe/corretor", headers=H, json={"corretor_id": None}).status_code == 404
    # assumir mantém o vinculado; desvincular e assumir de novo roteia pelo cadastro (Ana é a única ativa)
    assert c.post("/handoff/l1/assumir", headers=H).json()["corretor_nome"] == "Ana Souza"
    assert c.put("/leads/l1/corretor", headers=H, json={"corretor_id": None}).json()["corretor_id"] is None
    assert c.post("/handoff/l1/assumir", headers=H).json()["corretor_id"] == "cor_ana-souza"
    c.delete("/corretores/cor_ana-souza", headers=H); c.delete("/corretores/cor_bia-reis", headers=H)
    c.put("/leads/l1/corretor", headers=H, json={"corretor_id": None})


def test_callback_do_google_nao_reflete_html():
    """`/calendario/callback` é público e ecoa o parâmetro `error` do Google: sem escapar, virava
    XSS refletido num domínio nosso."""
    c = TestClient(app)
    r = c.get("/calendario/callback", params={"error": "<img src=x onerror=alert(1)>"})
    assert r.status_code == 200
    assert "<img src=x" not in r.text and "&lt;img" in r.text


def test_callback_recusa_state_nao_assinado():
    """Antes, `state` era o corretor_id cru: adivinhar o id bastava para plantar a credencial da
    própria conta Google na agenda do corretor."""
    c = TestClient(app)
    r = c.get("/calendario/callback", params={"code": "qualquer", "state": "cor_ana-souza"})
    assert r.status_code == 200 and "Link expirado" in r.text


def test_saude_diz_por_que_esta_lento_e_nao_so_que_esta():
    """As colunas que a tela descartava: canal, estágio e o caminho no grafo.

    Monta dois perfis no mesmo período — web rápida e telegram lento, com o agendador presente só
    nos lentos — e cobra que o recorte separe os dois e aponte o suspeito."""
    from sdr_shared.db import get_pool

    c = TestClient(app)
    with get_pool().connection() as conn:
        conn.execute("DELETE FROM turnos")
        for _ in range(20):
            conn.execute("""INSERT INTO turnos (lead_id, canal, resultado, duracao_ms, estagio, nos)
                            VALUES ('l1','web','ok',1200,'qualificando','{supervisor,qualificador}')""")
        for _ in range(4):
            conn.execute("""INSERT INTO turnos (lead_id, canal, resultado, duracao_ms, estagio, nos)
                            VALUES ('l1','telegram','ok',41000,'agendado','{supervisor,agendador}')""")

    d = c.get("/dashboard/saude", headers=H, params={"horas": 24}).json()

    canais = {x["chave"]: x for x in d["por_canal"]}
    assert canais["telegram"]["p95_ms"] > 30_000 and canais["web"]["p95_ms"] < 5_000, \
        "o p95 global misturaria os dois e esconderia qual canal está ruim"
    assert {x["chave"] for x in d["por_estagio"]} == {"qualificando", "agendado"}

    nos = {n["no"]: n for n in d["nos_lentos"]["nos"]}
    # O supervisor roda em TODO turno: aparece nos dois lados e não explica nada. O agendador só
    # aparece nos lentos — é o suspeito, e por isso encabeça a lista.
    assert d["nos_lentos"]["nos"][0]["no"] == "agendador"
    assert nos["agendador"]["pct_lentos"] == 100.0 and nos["agendador"]["pct_rapidos"] == 0.0
    assert nos["supervisor"]["pct_lentos"] == nos["supervisor"]["pct_rapidos"] == 100.0
    assert d["nos_lentos"]["corte_ms"] > 0, "o corte é o p95 do período, não um limiar fixo"


def test_saude_sem_turno_nenhum_nao_inventa_diagnostico():
    from sdr_shared.db import get_pool

    c = TestClient(app)
    with get_pool().connection() as conn:
        conn.execute("DELETE FROM turnos")
    d = c.get("/dashboard/saude", headers=H, params={"horas": 24}).json()
    assert d["nos_lentos"] == {"corte_ms": 0, "lentos": 0, "nos": []}
    assert d["por_canal"] == [] and d["por_estagio"] == []


def test_saude_serie_de_filas_mostra_o_pico_e_nao_a_media():
    """Fila estável em 40 e fila subindo até 40 têm a mesma cara num número só — e são opostas."""
    from sdr_shared.db import get_pool

    c = TestClient(app)
    with get_pool().connection() as conn:
        conn.execute("DELETE FROM saude")
        for filas, conexoes in (('{"agente": 0}', 4), ('{"agente": 60}', 9), ('{"agente": 2}', 5)):
            conn.execute("INSERT INTO saude (filas, conexoes_db) VALUES (%s, %s)", (filas, conexoes))

    serie = c.get("/dashboard/saude", headers=H, params={"horas": 24}).json()["serie_filas"]
    assert serie and max(p["filas"] for p in serie) == 60, "média apagaria o pico de 60"
    assert max(p["conexoes"] for p in serie) == 9


def test_modelos_recusa_modelo_sem_preco():
    """A trava principal: modelo sem preço zera o custo calculado, e com custo zero o teto mensal
    em dólar nunca é atingido — o guardrail de orçamento ficaria ligado só na aparência."""
    c = TestClient(app)
    r = c.put("/config/modelos", headers=H, json={"conversa": "modelo-que-nao-existe-v9"})
    assert r.status_code == 422 and "sem preço cadastrado" in r.json()["detail"]


def test_modelos_aceita_modelo_com_preco_e_muda_o_efetivo():
    c = TestClient(app)
    assert c.get("/config", headers=H).json()["canais"]["llm"]["efetivo"]["conversa"]["origem"] == "ambiente"
    r = c.put("/config/modelos", headers=H, json={"conversa": "claude-sonnet-5"})
    assert r.status_code == 200
    efetivo = c.get("/config", headers=H).json()["canais"]["llm"]["efetivo"]
    assert efetivo["conversa"] == {"modelo": "claude-sonnet-5", "provider": "anthropic", "origem": "painel"}
    # `analise` não configurado herda a conversa — não obriga preencher três níveis para mudar um
    assert efetivo["analise"]["modelo"] == "claude-sonnet-5"
    assert efetivo["roteamento"]["origem"] == "ambiente", "mexer num nível não mexe nos outros"
    assert c.delete("/config/modelos", headers=H).status_code == 204
    assert c.get("/config", headers=H).json()["canais"]["llm"]["efetivo"]["conversa"]["origem"] == "ambiente"


def test_config_expoe_catalogo_de_modelos_por_provedor():
    """A tela monta o combo com isto. Ter que manter uma lista no React ao lado da tabela de preços
    daria duas verdades: a que a tela oferece e a que o PUT aceita."""
    c = TestClient(app)
    catalogo = c.get("/config", headers=H).json()["canais"]["llm"]["catalogo"]
    assert "claude-sonnet-4-5" in catalogo["anthropic"]
    assert all(m.startswith("gpt-") or m[0] == "o" for m in catalogo["openai"])
    # o contrato que importa: tudo que a tela oferece passa no validador do PUT
    for provedor, modelos in catalogo.items():
        for m in modelos:
            r = c.put("/config/modelos", headers=H, json={"conversa": m, "conversa_provider": provedor})
            assert r.status_code == 200, f"{provedor}/{m} está no combo mas o PUT recusa: {r.text}"
    assert c.delete("/config/modelos", headers=H).status_code == 204


def test_comparacao_de_modelos_usa_o_consumo_real_e_a_latencia_medida():
    """A coluna que responde a pergunta de quem abre a tela: quanto o MEU uso teria custado com
    cada modelo, e qual deles respondeu rápido AQUI."""
    from sdr_shared.db import UsoRepository

    c = TestClient(app)
    sem_uso = c.get("/config/modelos/comparacao", headers=H).json()["papeis"]["roteamento"]
    assert [l["custo"]["usd"] for l in sem_uso] == sorted(l["custo"]["usd"] for l in sem_uso)
    assert all(l["custo"]["base"] == "referencia" for l in sem_uso)
    assert all(l["latencia"]["mediana_ms"] is None for l in sem_uso), "sem chamada, sem velocidade"

    repo = UsoRepository()
    for ms in (300, 400, 500, 600, 700, 800):
        repo.registrar(lead_id=None, no="supervisor", papel="roteamento", provider="anthropic",
                       modelo="claude-haiku-4-5", entrada=10_000, saida=1_000, cache_escrita=0,
                       cache_leitura=0, custo=0.015, latencia_ms=ms, erro=None)

    com_uso = c.get("/config/modelos/comparacao", headers=H).json()["papeis"]["roteamento"]
    haiku = next(l for l in com_uso if l["modelo"] == "claude-haiku-4-5")
    assert haiku["latencia"] == {"mediana_ms": 550, "amostras": 6, "escopo": "papel"}
    # 60k de entrada a US$1/1M + 6k de saída a US$5/1M = 0,09
    assert haiku["custo"] == {"usd": 0.09, "base": "uso", "dias": 30, "chamadas": 6}
    assert haiku["recomendado_para"] == "roteamento"
    # o contrafactual vale para TODOS os modelos, inclusive os que nunca rodaram
    opus = next(l for l in com_uso if l["modelo"] == "claude-opus-4-1")
    assert opus["custo"]["usd"] > haiku["custo"]["usd"] and opus["latencia"]["amostras"] == 0
    # e a conversa, que não teve uso, continua na referência — o mix é por papel
    assert all(l["custo"]["base"] == "referencia"
               for l in c.get("/config/modelos/comparacao", headers=H).json()["papeis"]["conversa"])


def test_modelos_recusa_provedor_e_id_invalidos():
    c = TestClient(app)
    # `openai` era recusado aqui até virar reserva de produção (ADR-0009). O caso continua valendo
    # com um provedor que de fato não existe — e `openrouter` é o exemplo certo: existe no código,
    # mas só como bancada de avaliação, e não pode ser escolhido pelo painel.
    assert c.put("/config/modelos", headers=H, json={"conversa_provider": "openrouter"}).status_code == 422
    assert c.put("/config/modelos", headers=H, json={"conversa_provider": "gpt"}).status_code == 422
    assert c.put("/config/modelos", headers=H, json={"conversa": "claude sonnet 5"}).status_code == 422
    assert c.put("/config/modelos", headers=H, json={"inventado": "x"}).status_code == 422


def test_modelos_ollama_dispensa_preco():
    """Ollama roda local: custo zero é a verdade, não uma falha de cadastro."""
    c = TestClient(app)
    r = c.put("/config/modelos", headers=H, json={"roteamento": "qwen2.5:7b", "roteamento_provider": "ollama"})
    assert r.status_code == 200
    c.delete("/config/modelos", headers=H)


def test_testar_modelo_reporta_falha_sem_derrubar():
    """O botão Testar existe para descobrir ID errado ANTES de salvar; ele reporta, não estoura."""
    c = TestClient(app)
    r = c.post("/config/modelos/testar", headers=H,
               json={"modelo": "claude-sonnet-5", "provider": "anthropic"})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["ok"] is False, "sem credencial válida no teste, a chamada real falha"
    assert corpo["tem_preco"] is True and "erro" in corpo
    assert c.post("/config/modelos/testar", headers=H, json={"modelo": ""}).status_code == 422


# ---------------------------------------------------------------- saúde (ADR-0011)

def test_health_devolve_503_quando_um_servico_para():
    """Um /health que responde 200 sempre é decoração. O compose e o target group leem isto."""
    from sdr_shared.db import get_pool, monitoramento as mon
    c = TestClient(app)
    with get_pool().connection() as x:
        x.execute("DELETE FROM batimentos")
    assert c.get("/health").status_code == 200

    mon.bater("agent")
    assert c.get("/health").status_code == 200, "batimento fresco: continua saudável"
    with get_pool().connection() as x:
        x.execute("UPDATE batimentos SET em = now() - make_interval(secs => %s)", (mon.PARADO_S + 30,))
    r = c.get("/health")
    assert r.status_code == 503 and r.json()["ok"] is False
    assert any("agent" in p for p in r.json()["problemas"])
    with get_pool().connection() as x:
        x.execute("DELETE FROM batimentos")


def test_saude_do_painel_exige_login_e_resume_os_turnos():
    from sdr_shared.db import get_pool, monitoramento as mon
    c = TestClient(app)
    assert c.get("/dashboard/saude").status_code in (401, 403), "dados de operação não são públicos"
    with get_pool().connection() as x:
        for t in ("turnos", "saude", "batimentos"):
            x.execute(f"DELETE FROM {t}")
    mon.registrar_turno(lead_id="l1", canal="web", resultado="ok", duracao_ms=900, estagio="novo", nos=["supervisor"])
    mon.amostrar({"inbound": 2})
    mon.bater("scheduler")

    d = c.get("/dashboard/saude", headers=H, params={"horas": 1}).json()
    assert d["turnos"]["total"] == 1 and d["turnos"]["por_resultado"] == {"ok": 1}
    assert d["amostra"]["filas"] == {"inbound": 2}
    assert [s["servico"] for s in d["servicos"]] == ["scheduler"] and d["servicos"][0]["vivo"] is True
    assert c.get("/dashboard/saude", headers=H, params={"horas": 999}).status_code == 422


# ------------------------------------------------------------- busca do site

def test_busca_pagina_conta_e_lista_bairros():
    c = TestClient(app)
    r = c.get("/imoveis/busca", params={"limite": 2}).json()
    assert len(r["itens"]) == 2 and r["total"] > 2, "total é do filtro inteiro, não da página"
    assert r["bairros"] and all(b["n"] >= 1 for b in r["bairros"])
    assert sum(b["n"] for b in r["bairros"]) == r["total"]
    pag2 = c.get("/imoveis/busca", params={"limite": 2, "offset": 2}).json()
    assert [i["id"] for i in pag2["itens"]] != [i["id"] for i in r["itens"]], "offset precisa andar"
    assert pag2["total"] == r["total"], "mudar de página não muda o total"


def test_busca_filtra_por_bairro_sem_acento_e_sem_caixa():
    c = TestClient(app)
    algum = c.get("/imoveis/busca", params={"limite": 1}).json()["itens"][0]["bairro"]
    r = c.get("/imoveis/busca", params={"bairro": algum.lower()}).json()
    assert r["total"] >= 1 and all(i["bairro"] == algum for i in r["itens"])


def test_lista_de_bairros_ignora_o_proprio_filtro_de_bairro():
    """A lista serve para TROCAR de bairro; se ela sumisse ao escolher um, não serviria para nada."""
    c = TestClient(app)
    todos = c.get("/imoveis/busca", params={"limite": 1}).json()["bairros"]
    algum = todos[0]["bairro"]
    filtrado = c.get("/imoveis/busca", params={"bairro": algum, "limite": 1}).json()
    assert len(filtrado["bairros"]) == len(todos)
    assert filtrado["total"] <= sum(b["n"] for b in todos)


def test_busca_combina_filtros_novos():
    c = TestClient(app)
    r = c.get("/imoveis/busca", params={"tipo": "apartamento", "quartos": 1,
                                        "preco_min": 1000, "ordenar": "preco_asc", "limite": 50}).json()
    precos = [i["preco"] for i in r["itens"]]
    assert precos == sorted(precos), "ordenar=preco_asc precisa ordenar de verdade"
    assert all(i["tipo"] == "apartamento" and i["quartos"] >= 1 and i["preco"] >= 1000 for i in r["itens"])
    caros = c.get("/imoveis/busca", params={"ordenar": "preco_desc", "limite": 50}).json()["itens"]
    assert [i["preco"] for i in caros] == sorted((i["preco"] for i in caros), reverse=True)


def test_busca_por_texto_acha_sem_acento():
    c = TestClient(app)
    algum = c.get("/imoveis/busca", params={"limite": 1}).json()["itens"][0]
    sem_acento = algum["bairro"].lower().replace("á", "a").replace("é", "e").replace("ó", "o")
    assert c.get("/imoveis/busca", params={"texto": sem_acento}).json()["total"] >= 1
    assert c.get("/imoveis/busca", params={"texto": "zzzznaoexiste"}).json()["total"] == 0


def test_busca_recusa_parametro_invalido():
    c = TestClient(app)
    assert c.get("/imoveis/busca", params={"ordenar": "por_simpatia"}).status_code == 422
    assert c.get("/imoveis/busca", params={"limite": 500}).status_code == 422
    assert c.get("/imoveis/busca", params={"preco_max": -1}).status_code == 422


# ------------------------------------------------------------------ OpenAPI

def test_openapi_marca_o_que_e_publico_e_o_que_exige_credencial():
    """O Swagger é a porta de entrada de quem integra: se ele mostra tudo como público, a primeira
    chamada de quem lê a documentação toma 401 sem explicação."""
    spec = app.openapi()
    assert "Token do painel" in spec["components"]["securitySchemes"]

    publicas = {c for c, ops in spec["paths"].items()
                for op in ops.values() if not op.get("security")}
    assert publicas == {"/health", "/imoveis", "/imoveis/busca", "/imoveis/{imovel_id}",
                        "/eventos", "/calendario/callback"}, (
        "mudou o conjunto de rotas sem autenticação — confira se é intencional antes de ajustar o teste")

    # amostra do outro lado: rotas que mexem em dado de lead têm de estar protegidas
    for caminho in ("/leads", "/governanca/uso", "/auditoria", "/config"):
        assert spec["paths"][caminho]["get"].get("security"), f"{caminho} deveria exigir credencial"


def test_openapi_descreve_as_etiquetas():
    spec = app.openapi()
    etiquetas = {t["name"]: t.get("description", "") for t in spec.get("tags", [])}
    assert {"público", "corretor", "operacao", "admin"} <= set(etiquetas)
    assert all(len(d) > 30 for d in etiquetas.values()), "etiqueta sem descrição não ajuda ninguém"


def test_rota_protegida_sem_token_responde_401_e_nao_500():
    c = TestClient(app)
    r = c.get("/leads")
    assert r.status_code == 401
    assert c.get("/leads", headers={"Authorization": "Bearer errado"}).status_code == 401


# ---------------------------------------------- desativação de corretor (carteira não fica órfã)

def _novo_corretor(c, nome, regioes=None):
    return c.post("/corretores", headers=H, json={"nome": nome, "regioes": regioes or []}).json()["id"]


def test_desativar_corretor_com_carteira_exige_destino():
    """O bug antigo: DELETE apagava a linha e o lead ficava apontando para um id inexistente."""
    from sdr_shared.db import LeadRepository
    c = TestClient(app)
    cid = _novo_corretor(c, "Bruno Teste")
    LeadRepository().atribuir_corretor("l1", cid)

    r = c.delete(f"/corretores/{cid}", headers=H)
    assert r.status_code == 409, "com carteira aberta e sem destino, precisa recusar e explicar"
    assert r.json()["detail"]["leads"] == 1

    assert c.delete(f"/corretores/{cid}", headers=H, params={"remover_cadastro": True}).status_code == 409


def test_desativar_move_a_carteira_e_avisa_quem_recebeu():
    from sdr_shared.db import LeadRepository, NotificacaoRepository
    c = TestClient(app)
    sai, entra = _novo_corretor(c, "Carla Sai"), _novo_corretor(c, "Diego Entra")
    LeadRepository().atribuir_corretor("l1", sai)

    r = c.delete(f"/corretores/{sai}", headers=H, params={"destino": entra})
    assert r.status_code == 200 and r.json()["movido"]["leads"] == 1

    assert LeadRepository().get("l1").corretor_id == entra, "o lead trocou de dono"
    inativo = next(x for x in c.get("/corretores", headers=H).json() if x["id"] == sai)
    assert inativo["ativo"] is False, "desativado, não apagado — o histórico continua"

    avisos = NotificacaoRepository().listar(corretor_id=entra)
    assert any(a["tipo"] == "lead.transferido" for a in avisos), "receber lead em silêncio é esquecê-lo"


def test_destino_equipe_devolve_para_a_fila_sem_dono():
    from sdr_shared.db import LeadRepository
    c = TestClient(app)
    cid = _novo_corretor(c, "Elisa Fila")
    LeadRepository().atribuir_corretor("l1", cid)
    assert c.delete(f"/corretores/{cid}", headers=H, params={"destino": "equipe"}).status_code == 200
    assert LeadRepository().get("l1").corretor_id is None


def test_destino_invalido_e_recusado_antes_de_mexer_em_qualquer_coisa():
    from sdr_shared.db import LeadRepository
    c = TestClient(app)
    cid = _novo_corretor(c, "Fabio Erro")
    LeadRepository().atribuir_corretor("l1", cid)
    for destino, esperado in (("nao-existe", 422), (cid, 422)):
        assert c.delete(f"/corretores/{cid}", headers=H, params={"destino": destino}).status_code == esperado
    assert LeadRepository().get("l1").corretor_id == cid, "recusa não pode ter movido nada"
    c.delete(f"/corretores/{cid}", headers=H, params={"destino": "equipe"})


def test_cadastro_sem_carteira_pode_ser_apagado():
    c = TestClient(app)
    cid = _novo_corretor(c, "Gustavo Engano")
    assert c.delete(f"/corretores/{cid}", headers=H, params={"remover_cadastro": True}).status_code == 200
    assert all(x["id"] != cid for x in c.get("/corretores", headers=H).json())


def test_apagar_corretor_no_banco_nao_deixa_lead_fantasma():
    """Rede de segurança do schema: mesmo um DELETE manual devolve o lead à fila da equipe."""
    from sdr_shared.db import LeadRepository, CorretorRepository, get_pool
    c = TestClient(app)
    cid = _novo_corretor(c, "Helena Manual")
    LeadRepository().atribuir_corretor("l1", cid)
    with get_pool().connection() as x:
        x.execute("DELETE FROM corretores WHERE id = %s", (cid,))
    assert LeadRepository().get("l1").corretor_id is None
    assert CorretorRepository().get(cid) is None


# ---------------------------------------------------------------------- interesses

def test_interesses_do_lead_e_do_imovel():
    from sdr_shared.db import InteresseRepository
    c = TestClient(app)
    repo = InteresseRepository()
    repo.registrar("l1", "SP-0001", situacao="interessado", origem="site")
    repo.registrar("l1", "SP-0002", situacao="sugerido", motivo="2 quartos na faixa pedida")

    assert c.get("/interesses/lead/l1").status_code in (401, 403), "carteira de lead não é pública"

    do_lead = c.get("/interesses/lead/l1", headers=H).json()
    assert {i["imovel_id"] for i in do_lead} == {"SP-0001", "SP-0002"}
    assert next(i for i in do_lead if i["imovel_id"] == "SP-0002")["motivo"] == "2 quartos na faixa pedida"
    assert all(i["bairro"] and i["preco"] for i in do_lead), "a lista serve ao corretor: precisa do imóvel junto"

    do_imovel = c.get("/interesses/imovel/SP-0001", headers=H).json()
    assert [i["lead_id"] for i in do_imovel] == ["l1"]

    assert c.get("/interesses/lead/nao-existe", headers=H).status_code == 404
    assert c.get("/interesses/imovel/nao-existe", headers=H).status_code == 404


def test_corretor_marca_descartado_e_o_imovel_some_da_lista_de_interessados():
    c = TestClient(app)
    r = c.put("/interesses/l1/SP-0001", headers=H, json={"situacao": "descartado"})
    assert r.status_code == 200 and r.json()["situacao"] == "descartado"
    assert [i["lead_id"] for i in c.get("/interesses/imovel/SP-0001", headers=H).json()] == []

    # desfazer o descarte é possível; rebaixar para "sugerido" não
    assert c.put("/interesses/l1/SP-0001", headers=H, json={"situacao": "interessado"}).status_code == 200
    assert c.put("/interesses/l1/SP-0001", headers=H, json={"situacao": "sugerido"}).status_code == 422
    assert c.put("/interesses/l1/SP-0001", headers=H, json={"situacao": "inventada"}).status_code == 422


# --------------------------------------------------- simulação da reativação (modo seco)

def test_simulacao_de_reativacao_lista_quem_seria_avisado_e_quem_nao():
    """Modo seco: a rota responde quem a Mora avisaria sobre um imóvel — sem enviar nada."""
    from datetime import datetime, timedelta, timezone
    from sdr_shared.db import InteresseRepository, LeadRepository, get_pool
    from sdr_shared.models import CartaoQualificacao, Intencao, Lead

    c = TestClient(app)
    im = c.get("/imoveis/busca", params={"operacao": "venda", "limite": 1}).json()["itens"][0]
    antigo = datetime.now(timezone.utc) - timedelta(days=30)
    cartao = CartaoQualificacao(intencao=Intencao.COMPRA, regiao=im["regiao"], bairros=[im["bairro"]],
                                preco_max=im["preco"] * 1.2, quartos=im["quartos"],
                                telefone_informado="11999990000")
    with get_pool().connection() as x:
        x.execute("DELETE FROM interesses")
    for lid, aceita in (("l_reat_ok", True), ("l_reat_optout", False)):
        LeadRepository().upsert(Lead(id=lid, nome=lid, telefone="11999990000", cartao=cartao,
                                     aceita_reativacao=aceita, ultima_mensagem_em=antigo))

    assert c.get(f"/reativacao/imovel/{im['id']}").status_code in (401, 403)
    r = c.get(f"/reativacao/imovel/{im['id']}", headers=H).json()

    candidatos = {x["lead_id"] for x in r["candidatos"]}
    assert "l_reat_ok" in candidatos, "lead antigo, no bairro e dentro do teto deveria ser avisado"
    assert "l_reat_optout" not in candidatos
    fora = {e["lead_id"]: e["motivo"] for e in r["excluidos"]}
    assert "não receber" in fora["l_reat_optout"]
    assert all(x["motivos"] for x in r["candidatos"]), "candidato sem motivo não vira mensagem"

    # quem já viu o imóvel sai da lista na próxima simulação
    InteresseRepository().registrar("l_reat_ok", im["id"], situacao="sugerido")
    r2 = c.get(f"/reativacao/imovel/{im['id']}", headers=H).json()
    assert "l_reat_ok" not in {x["lead_id"] for x in r2["candidatos"]}
    assert "já foi apresentado" in {e["lead_id"]: e["motivo"] for e in r2["excluidos"]}["l_reat_ok"]

    assert c.get("/reativacao/imovel/nao-existe", headers=H).status_code == 404


def test_corretor_liga_e_desliga_o_aviso_de_imovel_novo():
    """O opt-out chega por telefone, por e-mail e no meio de uma visita. Sem esta rota, honrá-lo
    exigiria um UPDATE no banco — que é o mesmo que não honrar."""
    c = TestClient(app)
    assert c.put("/leads/l1/reativacao", json={"aceita": False}).status_code in (401, 403)

    assert c.put("/leads/l1/reativacao", headers=H, json={"aceita": False}).json()["aceita_reativacao"] is False
    assert c.get("/leads/l1", headers=H).json()["aceita_reativacao"] is False
    assert c.put("/leads/l1/reativacao", headers=H, json={"aceita": True}).json()["aceita_reativacao"] is True
    assert c.get("/leads/l1", headers=H).json()["aceita_reativacao"] is True

    assert c.put("/leads/nao-existe/reativacao", headers=H, json={"aceita": False}).status_code == 404


def test_funil_de_reativacao_conta_o_que_o_aviso_produziu():
    """Fase 4 do ADR-0013. O teste monta a história inteira na auditoria — aviso, resposta, visita e
    saída — porque é a ORDEM que o funil precisa acertar: uma mensagem do cliente ANTES do aviso não
    é reação a ele, e uma resposta cinco dias depois é conversa nova."""
    from datetime import datetime, timedelta, timezone
    from sdr_shared.db import LeadRepository, get_pool
    from sdr_shared.models import Lead
    agora = datetime.now(timezone.utc)
    c = TestClient(app)

    for lid in ("r_respondeu", "r_calado", "r_antes"):
        LeadRepository().upsert(Lead(id=lid, nome=lid))
    with get_pool().connection() as cx:
        cx.execute("DELETE FROM auditoria WHERE acao LIKE '%reativa%' OR acao = 'visita.agendada'")
        cx.execute("DELETE FROM mensagens WHERE lead_id LIKE 'r_%'")
        for lid in ("r_respondeu", "r_calado", "r_antes"):
            cx.execute("""INSERT INTO auditoria (em, ator_tipo, ator_nome, acao, entidade, entidade_id, dados)
                          VALUES (%s, 'agente', 'Mora', 'lead.reativado', 'lead', %s, %s)""",
                       (agora - timedelta(days=2), lid, json.dumps({"imovel_id": "SP-0001", "motivos": ["bairro exato"]})))
        # respondeu dentro da janela
        cx.execute("INSERT INTO mensagens (lead_id, canal, direcao, conteudo, em) VALUES (%s,'telegram','in','tenho interesse',%s)",
                   ("r_respondeu", agora - timedelta(days=1)))
        # falou ANTES do aviso: não conta como reação a ele
        cx.execute("INSERT INTO mensagens (lead_id, canal, direcao, conteudo, em) VALUES (%s,'telegram','in','oi',%s)",
                   ("r_antes", agora - timedelta(days=3)))
        cx.execute("""INSERT INTO auditoria (em, ator_tipo, ator_nome, acao, entidade, entidade_id, dados)
                      VALUES (%s, 'agente', 'Mora', 'visita.agendada', 'visita', 'v1', %s)""",
                   (agora - timedelta(days=1), json.dumps({"lead_id": "r_respondeu", "imovel_id": "SP-0001"})))
        cx.execute("""INSERT INTO auditoria (em, ator_tipo, ator_nome, acao, entidade, entidade_id, dados)
                      VALUES (%s, 'cliente', 'r_calado', 'lead.optout_reativacao', 'lead', 'r_calado', '{}')""",
                   (agora - timedelta(days=1),))

    assert c.get("/dashboard/reativacao").status_code in (401, 403)
    r = c.get("/dashboard/reativacao", headers=H).json()

    assert r["avisos"] == 3 and r["leads"] == 3
    assert r["responderam"] == 1, "só quem falou DEPOIS do aviso conta"
    assert r["visitas"] == 1 and r["saidas"] == 1
    assert r["taxa_resposta"] == 33.3 and r["taxa_saida"] == 33.3
    ultimo = r["ultimos"][0]
    assert ultimo["bairro"] == "Brooklin" and ultimo["motivos"] == ["bairro exato"]
    assert {u["lead_id"]: u["respondeu"] for u in r["ultimos"]}["r_antes"] is False

    # Sem aviso nenhum no período, as taxas somem em vez de virar zero — 0% de resposta em cima de
    # zero aviso é uma afirmação falsa sobre a campanha.
    vazio = c.get("/dashboard/reativacao", headers=H, params={"dias": 1}).json()
    assert vazio["avisos"] == 0 and vazio["taxa_resposta"] is None


# --------------------------------------------------- provedor de reserva pelo painel

def test_reserva_pode_ser_escolhida_no_painel():
    """Estava só no `.env`: dava para apontar a conversa para outro provedor pela tela, mas não
    para dizer quem assume quando ele cai — justamente a decisão que alguém toma com o sistema no
    ar, e não num arquivo que exige recriar container."""
    c = TestClient(app)
    assert c.put("/config/modelos", headers=H, json={"fallback_provider": "openai"}).status_code == 200
    assert c.get("/config", headers=H).json()["config"]["modelos"]["fallback_provider"] == "openai"
    c.delete("/config/modelos", headers=H)


def test_reserva_igual_ao_primario_e_recusada():
    """Não é erro de digitação inofensivo: seriam duas chamadas ao mesmo provedor caído, e o cliente
    esperaria o dobro para receber a mesma falha."""
    c = TestClient(app)
    r = c.put("/config/modelos", headers=H,
              json={"conversa_provider": "openai", "fallback_provider": "openai"})
    assert r.status_code == 422 and "mesmo provedor" in r.json()["detail"]


def test_reserva_desconhecida_e_recusada():
    c = TestClient(app)
    assert c.put("/config/modelos", headers=H, json={"fallback_provider": "bedrock"}).status_code == 422


# --------------------------------------------------- ajustes de operação

def test_operacao_aceita_valores_na_faixa():
    c = TestClient(app)
    r = c.put("/config/operacao", headers=H,
              json={"llm_timeout_s": 30, "transcricao": "off", "acervo_refresh_s": 0})
    assert r.status_code == 200
    salvo = c.get("/config", headers=H).json()["config"]["operacao"]
    assert salvo["llm_timeout_s"] == 30 and salvo["transcricao"] == "off"
    assert salvo["acervo_refresh_s"] == 0, "0 é 'desligado', não 'vazio'"
    c.delete("/config/operacao", headers=H)


def test_operacao_recusa_timeout_fora_da_faixa():
    """Abaixo de 5s o modelo não termina de responder; acima de 180 o cliente já desistiu."""
    c = TestClient(app)
    assert c.put("/config/operacao", headers=H, json={"llm_timeout_s": 2}).status_code == 422
    assert c.put("/config/operacao", headers=H, json={"llm_timeout_s": 600}).status_code == 422


def test_operacao_recusa_refresh_curto_demais():
    """Abaixo de 60s a reindexação pega o worker ainda ocupado com o follow-up."""
    c = TestClient(app)
    r = c.put("/config/operacao", headers=H, json={"acervo_refresh_s": 10})
    assert r.status_code == 422 and "60s" in r.json()["detail"]


def test_operacao_recusa_motor_desconhecido():
    c = TestClient(app)
    assert c.put("/config/operacao", headers=H, json={"transcricao": "transcribe"}).status_code == 422
