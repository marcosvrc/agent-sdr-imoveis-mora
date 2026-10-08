"""Validação de tipos da configuração, travas do handoff e destino `auto` da desativação."""
import json
import os

os.environ.setdefault("SDR_DATABASE_DSN", "postgresql://sdr:sdr@localhost:5433/sdr_test")
from sdr_shared.db.guarda_teste import exigir_banco_de_teste; exigir_banco_de_teste()   # noqa: E702
os.environ["SDR_PROFILE"] = "local"

import pytest
from fastapi.testclient import TestClient

import api.routers.handoff as h
from api.main import app
from sdr_shared.db import CanalRepository, CorretorRepository, LeadRepository, get_pool
from sdr_shared.models import Corretor, Lead

H = {"Authorization": "Bearer dev-token"}


class Broker:
    msgs: list = []

    def publish(self, topic, body, key):
        self.msgs.append((topic, json.loads(body)))


class Sched:
    def cancel(self, lead_id):
        pass


@pytest.fixture
def c(monkeypatch):
    monkeypatch.setattr(h, "get_broker", lambda: Broker())
    monkeypatch.setattr(h, "get_scheduler", lambda: Sched())
    with get_pool().connection() as conn:
        for t in ("visitas", "mensagens", "canais", "notificacoes", "leads", "corretores", "configuracoes"):
            conn.execute(f"DELETE FROM {t}")
    return TestClient(app)


# ------------------------------------------------------------------ B12: tipos na configuração

@pytest.mark.parametrize("chave,corpo", [
    ("modelos", {"conversa": 123}),
    ("modelos", {"conversa_provider": ["anthropic"]}),
    ("operacao", {"transcricao": 5}),
    ("operacao", {"llm_timeout_s": True}),
    ("operacao", {"acervo_refresh_s": False}),
    ("agente", {"max_frases": "três"}),
    ("agente", {"apresentar_como_assistente": "sim"}),
    ("agenda", {"slots": ["10h"]}),
    ("followup", {"ativo": "true"}),
    ("followup", {"janela_inicio": 9}),
])
def test_tipo_errado_e_422_com_o_campo_na_mensagem(c, chave, corpo):
    """`{"conversa": 123}` em /config/modelos dava 500 (`int.strip`), e `"transcricao": 5` também."""
    r = c.put(f"/config/{chave}", headers=H, json=corpo)
    assert r.status_code == 422, r.text
    assert next(iter(corpo)) in r.json()["detail"]


def test_janela_compara_horas_e_nao_texto(c):
    """"9:00" < "18:00" como TEXTO é falso ("9" > "1"): a janela válida era recusada."""
    r = c.put("/config/followup", headers=H, json={"janela_inicio": "9:00", "janela_fim": "18:00"})
    assert r.status_code == 200, r.text
    assert c.put("/config/followup", headers=H,
                 json={"janela_inicio": "18:00", "janela_fim": "9:00"}).status_code == 422


def test_corpos_que_o_painel_envia_continuam_aceitos(c):
    """O formato de hoje (o que apps/dashboard manda) não muda: seção inteira, vazio = herda."""
    padrao = c.get("/config", headers=H).json()["defaults"]
    for chave, valor in padrao.items():
        assert c.put(f"/config/{chave}", headers=H, json=valor).status_code == 200, chave
    assert c.put("/config/operacao", headers=H,
                 json={"llm_timeout_s": 30, "transcricao": "off", "acervo_refresh_s": 0}).status_code == 200
    assert c.put("/config/agenda", headers=H,
                 json={"slots": [9, 14], "duracao_min": 45, "dias_uteis": False, "antecedencia_dias": 3}).status_code == 200


# ------------------------------------------------------------------ B16: handoff

def _lead_com_canal(lead_id="l_h", **kw):
    LeadRepository().upsert(Lead(id=lead_id, nome="Marcos", **kw))
    CanalRepository().vincular(lead_id, "telegram", f"chat_{lead_id}")


def test_responder_fora_de_handoff_e_409(c):
    """Sem handoff, a Mora também responde: corretor e agente falando ao mesmo tempo com o cliente."""
    _lead_com_canal()
    r = c.post("/handoff/l_h/responder", headers=H, json={"texto": "oi"})
    assert r.status_code == 409 and "assum" in r.json()["detail"]
    assert c.post("/handoff/l_h/assumir", headers=H).status_code == 200
    r = c.post("/handoff/l_h/responder", headers=H, json={"texto": "oi"})
    assert r.status_code == 200 and r.json()["canais"] == ["telegram"]


def test_assumir_lead_ja_assumido_por_outro_e_409(c):
    CorretorRepository().upsert(Corretor(id="cor_a", nome="Ana", ativo=True))
    CorretorRepository().upsert(Corretor(id="cor_b", nome="Bruno", ativo=True))
    _lead_com_canal()
    assert c.post("/handoff/l_h/assumir", headers=H, json={"corretor_id": "cor_a"}).json()["corretor_id"] == "cor_a"

    r = c.post("/handoff/l_h/assumir", headers=H, json={"corretor_id": "cor_b"})
    assert r.status_code == 409 and "Ana" in r.json()["detail"]
    assert LeadRepository().get("l_h").corretor_id == "cor_a"

    # assumir o que já é seu continua ok — é o que o painel manda (o corretor atual no corpo)
    r = c.post("/handoff/l_h/assumir", headers=H, json={"corretor_id": "cor_a"})
    assert r.status_code == 200 and r.json() == {"lead_id": "l_h", "corretor_id": "cor_a",
                                                  "corretor_nome": "Ana", "estagio": "handoff"}
    assert c.post("/handoff/l_h/assumir", headers=H).status_code == 200


def test_lead_devolvido_pode_ser_assumido_por_outro(c):
    CorretorRepository().upsert(Corretor(id="cor_a", nome="Ana", ativo=True))
    CorretorRepository().upsert(Corretor(id="cor_b", nome="Bruno", ativo=True))
    _lead_com_canal()
    c.post("/handoff/l_h/assumir", headers=H, json={"corretor_id": "cor_a"})
    c.post("/handoff/l_h/devolver", headers=H)
    assert c.post("/handoff/l_h/assumir", headers=H, json={"corretor_id": "cor_b"}).json()["corretor_id"] == "cor_b"


# ------------------------------------------------------------------ destino `auto`

def test_desativar_com_auto_nao_escolhe_quem_esta_saindo(c):
    """Quem sai ainda está ativo e, sem carga, ganhava o roteamento: a carteira ia para a fila da
    equipe mesmo havendo outro corretor apto."""
    CorretorRepository().upsert(Corretor(id="cor_a", nome="Ana", regioes=["zona_sul"], ativo=True))
    CorretorRepository().upsert(Corretor(id="cor_b", nome="Bruno", regioes=["zona_sul"], ativo=True))
    LeadRepository().upsert(Lead(id="l_b", corretor_id="cor_b", estagio="handoff"))   # Bruno tem carga
    LeadRepository().upsert(Lead(id="l_a", corretor_id="cor_a"))
    r = c.delete("/corretores/cor_a", headers=H, params={"destino": "auto"})
    assert r.status_code == 200, r.text
    assert r.json()["destino"] == "cor_b"
    assert LeadRepository().get("l_a").corretor_id == "cor_b"
