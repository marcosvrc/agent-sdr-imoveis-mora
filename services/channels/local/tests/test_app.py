import os
import json
import pytest
os.environ.setdefault("SDR_DATABASE_DSN", "postgresql://sdr:sdr@localhost:5433/sdr_test")
from sdr_shared.db.guarda_teste import exigir_banco_de_teste; exigir_banco_de_teste()   # nunca rodar contra o banco de dev
os.environ["SDR_PROFILE"] = "local"
from fastapi.testclient import TestClient
import app as local_app


class MemBroker:
    msgs = []
    def publish(self, topic, body, key): self.msgs.append((topic, json.loads(body), key))
    def consume(self, *a, **k): import time; time.sleep(3600)


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
    with c.websocket_connect(f"/ws?papel=lead&id={sid}&token={sessao['token']}") as ws:
        ws.send_text(json.dumps({"session_id": sid, "texto": "quero alugar", "meta": {"imovel_origem": "SP-0002"}}))
        import time; time.sleep(0.2)
    t, m, _ = MemBroker.msgs[-1]
    assert t == "inbound" and m["canal"] == "web" and m["lead_id"] == f"web_{sid}" and m["meta"]["imovel_origem"] == "SP-0002"


def test_sessao_inventada_pelo_navegador_nao_conecta():
    """Sem isto, saber o id de outro visitante bastava para ler e escrever na conversa dele."""
    from starlette.websockets import WebSocketDisconnect
    c = TestClient(local_app.app)
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/ws?papel=lead&id=sess-de-outra-pessoa&token=inventado"):
            pass


def test_conexao_nao_fala_pela_sessao_de_outro():
    c = TestClient(local_app.app)
    minha, alheia = c.post("/sessao").json(), c.post("/sessao").json()
    antes = len(MemBroker.msgs)
    with c.websocket_connect(f"/ws?papel=lead&id={minha['session_id']}&token={minha['token']}") as ws:
        ws.send_text(json.dumps({"session_id": alheia["session_id"], "texto": "mensagem no lugar de outro"}))
        import time; time.sleep(0.2)
    assert len(MemBroker.msgs) == antes, "a conexão só publica pela sessão que ela autenticou"


def test_painel_sem_credencial_nao_conecta():
    """O canal `papel=dashboard` recebe o espelho de TODAS as conversas. Sem credencial da equipe,
    qualquer um na rede abriria isto e leria os leads inteiros (nome, telefone, orçamento)."""
    from starlette.websockets import WebSocketDisconnect
    c = TestClient(local_app.app)
    for query in ("/ws?papel=dashboard&id=painel",                    # sem token
                  "/ws?papel=dashboard&id=painel&token=chute"):       # token errado
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect(query):
                pass


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
    with c.websocket_connect("/ws?papel=dashboard&id=painel&token=dev-token") as ws:
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
