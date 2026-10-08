import os
import json
import pytest
from contextlib import contextmanager
os.environ.setdefault("SDR_DATABASE_DSN", "postgresql://sdr:sdr@localhost:5433/sdr_test")
from sdr_shared.db.guarda_teste import exigir_banco_de_teste; exigir_banco_de_teste()   # nunca rodar contra o banco de dev
os.environ["SDR_PROFILE"] = "local"
from fastapi.testclient import TestClient
import app as local_app


class MemBroker:
    msgs = []
    def publish(self, topic, body, key): self.msgs.append((topic, json.loads(body), key))
    def consume(self, *a, **k): import time; time.sleep(3600)


@pytest.fixture(autouse=True)
def _limites_zerados():
    """Os limites por IP são do processo: sem zerar, a 21ª sessão aberta pela suíte inteira
    (sempre do mesmo IP do TestClient) seria recusada num teste que nada tem a ver com isso."""
    local_app.zerar_limites()
    yield
    local_app.zerar_limites()


@contextmanager
def lead_conectado(c, sessao):
    """Abre o WebSocket do widget como o site abre: credencial no primeiro quadro, nunca na URL."""
    with c.websocket_connect("/ws?papel=lead") as ws:
        ws.send_text(json.dumps({"session_id": sessao["session_id"], "token": sessao["token"]}))
        assert json.loads(ws.receive_text()) == {"evento": "pronto"}
        yield ws


def setup_module(m):
    local_app.get_broker = lambda: MemBroker()
    from sdr_shared.db import get_pool
    with get_pool().connection() as c:
        for t in ("mensagens", "canais", "leads"):
            c.execute(f"DELETE FROM {t}")


def test_websocket_widget():
    c = TestClient(local_app.app)
    sessao = c.post("/sessao").json()                     # o id do chat é emitido pelo servidor
    sid = sessao["session_id"]
    with lead_conectado(c, sessao) as ws:
        ws.send_text(json.dumps({"session_id": sid, "texto": "quero alugar", "meta": {"imovel_origem": "SP-0002"}}))
        import time; time.sleep(0.2)
    t, m, _ = MemBroker.msgs[-1]
    assert t == "inbound" and m["canal"] == "web" and m["lead_id"] == f"web_{sid}" and m["meta"]["imovel_origem"] == "SP-0002"


def test_sessao_inventada_pelo_navegador_nao_conecta():
    """Sem isto, saber o id de outro visitante bastava para ler e escrever na conversa dele."""
    from starlette.websockets import WebSocketDisconnect
    c = TestClient(local_app.app)
    with pytest.raises(WebSocketDisconnect) as exc:
        with c.websocket_connect("/ws?papel=lead") as ws:
            ws.send_text(json.dumps({"session_id": "sess-de-outra-pessoa", "token": "inventado"}))
            ws.receive_text()
    # 4401 chega ao navegador porque a recusa é DEPOIS do aceite; fechar antes do aceite vira 1006
    # no navegador, e o widget não teria como saber que precisa pedir outra sessão.
    assert exc.value.code == 4401


def test_conexao_nao_fala_pela_sessao_de_outro():
    c = TestClient(local_app.app)
    minha, alheia = c.post("/sessao").json(), c.post("/sessao").json()
    antes = len(MemBroker.msgs)
    with lead_conectado(c, minha) as ws:
        ws.send_text(json.dumps({"session_id": alheia["session_id"], "texto": "mensagem no lugar de outro", "ref": "r1"}))
        # Recusa com aviso, e não em silêncio: o widget mostra "Tentar de novo" em vez de "digitando" eterno.
        assert json.loads(ws.receive_text())["evento"] == "falha_envio"
    assert len(MemBroker.msgs) == antes, "a conexão só publica pela sessão que ela autenticou"


def test_painel_sem_credencial_nao_conecta():
    """O canal `papel=dashboard` recebe o espelho de TODAS as conversas. Sem credencial da equipe,
    qualquer um na rede abriria isto e leria os leads inteiros (nome, telefone, orçamento)."""
    from starlette.websockets import WebSocketDisconnect
    c = TestClient(local_app.app)
    for primeiro_quadro in ('{"token": "chute"}',        # token errado
                            '{"token": 42}',             # tipo errado não vira 500
                            'isto não é json',
                            '{"texto": "oi"}'):          # quadro comum antes da credencial
        with pytest.raises(WebSocketDisconnect) as exc:
            with c.websocket_connect("/ws?papel=dashboard&id=painel") as ws:
                ws.send_text(primeiro_quadro)
                ws.receive_text()
        assert exc.value.code == 4403, primeiro_quadro


def test_credencial_do_painel_na_url_nao_vale_mais():
    """Foi assim até setembro/2026: `?token=` na URL. Query string vai para log de proxy, histórico
    e Referer — e este é o token da equipe inteira. O servidor agora ignora o parâmetro para o
    painel: quem mandar só por ali e ficar em silêncio cai no prazo."""
    from starlette.websockets import WebSocketDisconnect
    local_app.PRAZO_CREDENCIAL_S = 0.3
    try:
        c = TestClient(local_app.app)
        with pytest.raises(WebSocketDisconnect) as exc:
            with c.websocket_connect("/ws?papel=dashboard&id=painel&token=dev-token") as ws:
                ws.receive_text()
        assert exc.value.code == 4403
    finally:
        local_app.PRAZO_CREDENCIAL_S = 5


def test_painel_recebe_pronto_depois_da_credencial():
    c = TestClient(local_app.app)
    with painel_conectado(c):
        pass                                             # o `pronto` já foi conferido ao abrir


@contextmanager
def painel_conectado(c):
    with c.websocket_connect("/ws?papel=dashboard&id=painel") as ws:
        ws.send_text(json.dumps({"token": "dev-token"}))
        assert json.loads(ws.receive_text()) == {"evento": "pronto"}
        yield ws


def test_papel_desconhecido_nao_vira_painel():
    """Antes, qualquer valor diferente de "lead" caía no ramo do painel — inclusive um typo."""
    from starlette.websockets import WebSocketDisconnect
    c = TestClient(local_app.app)
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/ws?papel=qualquer-coisa&id=x"):
            pass


def test_painel_com_credencial_conecta_mas_nao_fala_por_ninguem():
    """Com o token da equipe entra; ainda assim não publica em nome de lead nenhum — quem responde
    ao cliente é o /handoff da API, que é auditado."""
    c = TestClient(local_app.app)
    vitima = c.post("/sessao").json()
    antes = len(MemBroker.msgs)
    with painel_conectado(c) as ws:
        ws.send_text(json.dumps({"session_id": vitima["session_id"], "texto": "me passando por um lead"}))
        import time; time.sleep(0.2)
    assert len(MemBroker.msgs) == antes, "conexão de painel é somente leitura"


def test_health_reprova_quando_o_barramento_cai():
    """Canal sem Redis aceita WebSocket e some com a mensagem — 200 aqui seria pior que erro."""
    c = TestClient(local_app.app)
    original = local_app.get_broker

    class Vivo(MemBroker):
        def ping(self): pass

    class Morto(MemBroker):
        def ping(self): raise ConnectionError("redis fora do ar")

    try:
        local_app.get_broker = lambda: Vivo()
        r = c.get("/health")
        assert r.status_code == 200 and r.json()["ok"] is True

        local_app.get_broker = lambda: Morto()
        r = c.get("/health")
        assert r.status_code == 503 and r.json()["ok"] is False
        assert "barramento" in r.json()["problemas"][0]
    finally:
        local_app.get_broker = original


def test_quadro_invalido_derruba_so_a_conexao_e_a_tira_do_registro():
    """Antes, JSON inválido escapava do laço e o socket ficava em `conexoes` para sempre — cada
    resposta seguinte da Mora tentava escrever num socket morto."""
    from starlette.websockets import WebSocketDisconnect
    c = TestClient(local_app.app)
    sessao = c.post("/sessao").json()
    sid = sessao["session_id"]
    with pytest.raises(WebSocketDisconnect):
        with lead_conectado(c, sessao) as ws:
            ws.send_text("{isto não é json")
            ws.receive_text()
    assert not local_app.conexoes.get(sid), "socket morto não pode ficar registrado"


def test_historico_devolve_a_conversa_da_propria_sessao():
    """Recarregar a página apagava as bolhas, mas a Mora seguia a conversa de onde parou."""
    from sdr_shared.db import LeadRepository, MensagemRepository
    from sdr_shared.models import Lead
    c = TestClient(local_app.app)
    s = c.post("/sessao").json()
    lead = f"web_{s['session_id']}"
    LeadRepository().upsert(Lead(id=lead))
    MensagemRepository().registrar(lead, "web", "in", "quero alugar em Moema")
    MensagemRepository().registrar(lead, "web", "out", "Até quanto?", {"opcoes": ["A|B"], "imoveis": ["SP-1"]})
    r = c.post("/historico", json={"session_id": s["session_id"], "token": s["token"]}).json()["mensagens"]
    assert [(m["de"], m["texto"]) for m in r] == [("lead", "quero alugar em Moema"), ("Mora", "Até quanto?")]
    assert r[1]["opcoes"] == ["A|B"] and r[1]["imoveis"] == ["SP-1"]


def test_historico_de_sessao_inventada_nao_le_nada():
    c = TestClient(local_app.app)
    r = c.post("/historico", json={"session_id": "sess-de-outra-pessoa", "token": "inventado"})
    assert r.status_code == 401 and r.json()["mensagens"] == []


# ---------------------------------------------------------------------------------------------
# Credencial do widget no primeiro quadro (S12)


def test_token_do_lead_na_url_nao_vale_mais():
    """O token da sessão do chat ia na URL do WebSocket — e URL vai para log de proxy e de acesso.
    Agora vale só no primeiro quadro: quem manda só pela URL e fica calado cai no prazo."""
    from starlette.websockets import WebSocketDisconnect
    local_app.PRAZO_CREDENCIAL_S = 0.3
    try:
        c = TestClient(local_app.app)
        s = c.post("/sessao").json()
        with pytest.raises(WebSocketDisconnect) as exc:
            with c.websocket_connect(f"/ws?papel=lead&id={s['session_id']}&token={s['token']}") as ws:
                ws.receive_text()
        assert exc.value.code == 4401
    finally:
        local_app.PRAZO_CREDENCIAL_S = 5


def test_sessao_expirada_fecha_com_4401():
    """Sessão vencida: o widget recebe 4401, descarta a sessão e pede outra (não fica
    "reconectando…" para sempre com o mesmo token)."""
    from starlette.websockets import WebSocketDisconnect
    from sdr_shared.seguranca import sessao as mod
    c = TestClient(local_app.app)
    original = mod.VALIDADE_S
    mod.VALIDADE_S = -10
    try:
        vencida = c.post("/sessao").json()
    finally:
        mod.VALIDADE_S = original
    with pytest.raises(WebSocketDisconnect) as exc:
        with c.websocket_connect("/ws?papel=lead") as ws:
            ws.send_text(json.dumps({"session_id": vencida["session_id"], "token": vencida["token"]}))
            ws.receive_text()
    assert exc.value.code == 4401


def test_pendentes_entregues_depois_da_credencial():
    """Resposta que chegou com o widget fechado sai na reconexão, mas só depois do `pronto`."""
    c = TestClient(local_app.app)
    s = c.post("/sessao").json()
    import time
    local_app.pendentes[s["session_id"]].append((time.time(), {"texto": "resposta guardada"}))
    with lead_conectado(c, s) as ws:
        assert json.loads(ws.receive_text()) == {"texto": "resposta guardada"}


# ---------------------------------------------------------------------------------------------
# meta do navegador: lista fechada (S3)


def _publicado_com_meta(meta, texto="oi"):
    c = TestClient(local_app.app)
    s = c.post("/sessao").json()
    antes = len(MemBroker.msgs)
    with lead_conectado(c, s) as ws:
        ws.send_text(json.dumps({"session_id": s["session_id"], "texto": texto, "meta": meta, "ref": "r"}))
        assert json.loads(ws.receive_text()) == {"evento": "recebido", "ref": "r"}
    assert len(MemBroker.msgs) == antes + 1
    return MemBroker.msgs[-1][1]


def test_meta_aceita_so_as_chaves_que_o_site_manda():
    """O `meta` ia inteiro ao agente: `nome`/`telefone` forjados no navegador viravam dado do lead
    (handler.py faz upsert com eles), e qualquer chave nova do agente ficava exposta ao site."""
    m = _publicado_com_meta({"imovel_origem": "SP-0002", "saudacao_exibida": True,
                             "nome": "Fulano", "telefone": "11999990000", "telegram_file_id": "x",
                             "motivos": ["a"], "qualquer": {"coisa": 1}})
    assert m["meta"] == {"imovel_origem": "SP-0002", "saudacao_exibida": True}
    assert m["tipo"] == "texto"


def test_botao_vira_tipo_e_nao_vai_no_meta():
    m = _publicado_com_meta({"botao": True}, texto="Comprar")
    assert m["tipo"] == "botao" and m["meta"] == {}


@pytest.mark.parametrize("origem", ["../../etc", "SP 0002", "x" * 65, 42, ["SP-1"], "", "SP-1\n"])
def test_imovel_origem_fora_do_formato_e_descartado(origem):
    """Mesmo formato de `eventos.py` (ID_IMOVEL): texto livre aqui viraria instrução no prompt."""
    assert _publicado_com_meta({"imovel_origem": origem})["meta"] == {}


def test_meta_que_nao_e_objeto_vira_vazio():
    assert _publicado_com_meta(["isto", "não", "é", "dict"])["meta"] == {}
    assert _publicado_com_meta("texto")["meta"] == {}


# ---------------------------------------------------------------------------------------------
# Tamanho e limites (S3/S8)


def test_texto_longo_demais_e_recusado_com_aviso():
    """O campo do site corta em 1000 caracteres; acima disso é script — e é LLM pago por token."""
    c = TestClient(local_app.app)
    s = c.post("/sessao").json()
    antes = len(MemBroker.msgs)
    with lead_conectado(c, s) as ws:
        ws.send_text(json.dumps({"session_id": s["session_id"], "texto": "a" * 1001, "ref": "r"}))
        resp = json.loads(ws.receive_text())
    assert resp["evento"] == "falha_envio" and resp["ref"] == "r"
    assert len(MemBroker.msgs) == antes


def test_quadro_grande_demais_derruba_a_conexao():
    from starlette.websockets import WebSocketDisconnect
    c = TestClient(local_app.app)
    s = c.post("/sessao").json()
    antes = len(MemBroker.msgs)
    with pytest.raises(WebSocketDisconnect) as exc:
        with lead_conectado(c, s) as ws:
            ws.send_text(json.dumps({"session_id": s["session_id"], "texto": "oi",
                                     "meta": {"lixo": "x" * local_app.MAX_QUADRO_BYTES}}))
            ws.receive_text()
    assert exc.value.code == 1009                      # 1009 = "mensagem grande demais"
    assert len(MemBroker.msgs) == antes


def test_primeiro_quadro_grande_demais_nao_autentica():
    from starlette.websockets import WebSocketDisconnect
    c = TestClient(local_app.app)
    with pytest.raises(WebSocketDisconnect) as exc:
        with c.websocket_connect("/ws?papel=lead") as ws:
            ws.send_text("x" * (local_app.MAX_QUADRO_BYTES + 1))
            ws.receive_text()
    assert exc.value.code == 4401


def test_sessoes_por_ip_tem_limite():
    """Um script abria sessão nova a cada 5 mensagens: cada sessão é um lead novo, sem teto de LLM."""
    c = TestClient(local_app.app)
    for _ in range(local_app.LIMITE_SESSOES.maximo):
        assert c.post("/sessao").status_code == 200
    r = c.post("/sessao")
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_mensagens_por_sessao_tem_limite_e_avisam():
    c = TestClient(local_app.app)
    s = c.post("/sessao").json()
    antes = len(MemBroker.msgs)
    n = local_app.LIMITE_MSG_SESSAO.maximo
    with lead_conectado(c, s) as ws:
        for i in range(n + 1):
            ws.send_text(json.dumps({"session_id": s["session_id"], "texto": f"msg {i}", "ref": str(i)}))
            resp = json.loads(ws.receive_text())
        assert resp["evento"] == "falha_envio" and resp["ref"] == str(n)
    assert len(MemBroker.msgs) == antes + n


def test_mensagens_por_ip_tem_limite_mesmo_trocando_de_sessao():
    """Trocar de sessão não zera a conta: o teto por IP pega o script que gira sessões."""
    c = TestClient(local_app.app)
    original = local_app.LIMITE_MSG_IP
    local_app.LIMITE_MSG_IP = local_app.JanelaDeslizante(3, 3600)
    try:
        enviados = 0
        for _ in range(2):
            s = c.post("/sessao").json()
            with lead_conectado(c, s) as ws:
                for i in range(2):
                    ws.send_text(json.dumps({"session_id": s["session_id"], "texto": "oi", "ref": str(i)}))
                    enviados += json.loads(ws.receive_text())["evento"] == "recebido"
        assert enviados == 3
    finally:
        local_app.LIMITE_MSG_IP = original
