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
        with c.websocket_connect(f"/ws?papel=lead&id={sid}&token={sessao['token']}") as ws:
            ws.send_text("{isto não é json")
            ws.receive_text()
    assert not local_app.conexoes.get(sid), "socket morto não pode ficar registrado"
