"""A trilha de auditoria precisa registrar o que muda o sistema — e nunca guardar segredo nem derrubar a ação."""
import os
os.environ.setdefault("SDR_DATABASE_DSN", "postgresql://sdr:sdr@localhost:5433/sdr_test")
from sdr_shared.db.guarda_teste import exigir_banco_de_teste; exigir_banco_de_teste()
os.environ["SDR_PROFILE"] = "local"
from fastapi.testclient import TestClient
from sdr_shared.db import AuditoriaRepository, auditar, get_pool
from sdr_shared.db.auditoria import _limpar
from api.main import app

H = {"Authorization": "Bearer dev-token"}
cliente = TestClient(app)


def setup_function(_):
    with get_pool().connection() as c:
        c.execute("DELETE FROM auditoria")
        c.execute("DELETE FROM corretores WHERE id = 'cor_teste-auditoria'")   # o teste cria este
    import api.routers.leads as leads
    leads._ultimo_acesso.clear()


def test_mutacao_pela_api_vira_registro():
    r = cliente.post("/corretores", headers=H, json={"nome": "Teste Auditoria", "email": "t@a.dev",
                                                     "telefone": "11999998888", "regioes": ["zona_sul"], "ativo": True})
    assert r.status_code == 201
    regs = AuditoriaRepository().listar(dias=1, acao="corretor.criado")
    assert len(regs) == 1
    assert regs[0]["ator_tipo"] == "corretor" and regs[0]["ator_nome"] == "corretor@local"
    assert regs[0]["dados"]["enviado"]["nome"] == "Teste Auditoria"


def test_leitura_de_rotina_nao_polui_a_trilha():
    cliente.get("/dashboard/funil", headers=H)
    cliente.get("/imoveis", headers=H)
    assert AuditoriaRepository().listar(dias=1) == []


def test_primeiro_acesso_do_processo_e_registrado():
    """O relógio monotônico começa perto de zero: num container recém-subido, tratar 0 como
    'já registrado agora há pouco' silenciava os primeiros minutos de acesso a dados de cliente."""
    import api.routers.leads as leads
    leads._ultimo_acesso.clear()
    cliente.get("/leads", headers=H)
    assert len(AuditoriaRepository().listar(dias=1, acao="lead.listado")) == 1


def test_listagem_de_leads_registra_uma_vez_por_janela():
    for _ in range(3):
        cliente.get("/leads", headers=H)
    regs = AuditoriaRepository().listar(dias=1, acao="lead.listado")
    assert len(regs) == 1, "o painel recarrega sozinho: um registro por janela, não por requisição"
    assert regs[0]["dados"]["janela_min"] == 10


def test_falha_da_api_fica_marcada_como_erro():
    assert cliente.delete("/corretores/inexistente", headers=H).status_code == 404
    regs = AuditoriaRepository().listar(dias=1, acao="corretor.removido")
    assert regs[0]["resultado"] == "erro" and "404" in regs[0]["detalhe"]


def test_segredo_e_payload_gigante_nunca_entram_na_trilha():
    limpo = _limpar({"senha": "x", "api_key": "sk-1", "foto": "data:image/png;base64,AAA",
                     "nome": "Ana", "vazio": None, "texto": "y" * 900, "itens": list(range(50)),
                     "dentro": {"authorization": "Bearer z", "ok": 1}})
    assert limpo["senha"] == limpo["api_key"] == limpo["foto"] == "[omitido]"
    assert limpo["dentro"]["authorization"] == "[omitido]" and limpo["dentro"]["ok"] == 1
    assert limpo["nome"] == "Ana" and "vazio" not in limpo
    assert len(limpo["texto"]) == 501 and len(limpo["itens"]) == 20


def test_auditoria_nunca_derruba_a_acao_auditada(monkeypatch):
    import sdr_shared.db.auditoria as mod
    def explode(*a, **k):
        raise RuntimeError("banco fora do ar")
    monkeypatch.setattr(mod, "_conn", explode)
    auditar(acao="corretor.criado", entidade="corretor")        # não deve levantar


def test_exportacao_csv_se_autoregistra():
    r = cliente.get("/auditoria/exportar?dias=1", headers=H)
    assert r.status_code == 200 and r.text.startswith("quando;ator_tipo")
    regs = AuditoriaRepository().listar(dias=1, acao="auditoria.exportada")
    assert len(regs) == 1 and regs[0]["dados"]["dias"] == 1


def test_filtros_e_resumo():
    auditar(acao="lead.exportado_crm", entidade="lead", ator_tipo="corretor", ator_nome="corretor@local",
            dados={"exportados": 3})
    auditar(acao="lead.followup_enviado", entidade="lead", entidade_id="lead-1", ator_tipo="agente", ator_nome="Mora")
    repo = AuditoriaRepository()
    assert [r["acao"] for r in repo.listar(dias=1, so_sensiveis=True)] == ["lead.exportado_crm"]
    assert len(repo.listar(dias=1, ator="agente")) == 1
    assert len(repo.listar(dias=1, entidade_id="lead-1")) == 1
    assert len(repo.listar(dias=1, busca="exportados")) == 1
    resumo = repo.resumo(1)
    assert resumo["total"] == 2 and resumo["sensiveis"] == 1
