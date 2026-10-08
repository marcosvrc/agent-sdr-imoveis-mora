"""Itens da revisão de segurança que vivem na API: trilha de auditoria sem lixo anônimo, CSV sem
fórmula, teto de corpo contando bytes e upload de foto conferido pelos bytes."""
import base64
import os
os.environ.setdefault("SDR_DATABASE_DSN", "postgresql://sdr:sdr@localhost:5433/sdr_test")
from sdr_shared.db.guarda_teste import exigir_banco_de_teste; exigir_banco_de_teste()   # noqa: E702
os.environ["SDR_PROFILE"] = "local"
from fastapi.testclient import TestClient   # noqa: E402
from sdr_shared.db import AuditoriaRepository, auditar, get_pool   # noqa: E402
from api.main import app   # noqa: E402

H = {"Authorization": "Bearer dev-token"}
cliente = TestClient(app)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def setup_function(_):
    with get_pool().connection() as c:
        c.execute("DELETE FROM auditoria")


# ---------------------------------------------------------------- S6: trilha sem ruído anônimo

def test_requisicao_anonima_recusada_nao_entra_na_trilha():
    """Antes, qualquer um na rede enchia a auditoria com POST/DELETE sem credencial (401) ou em
    rota inexistente (404) — e a ação de verdade sumia no meio."""
    assert cliente.post("/corretores", json={"nome": "x"}).status_code == 401
    assert cliente.delete("/corretores/qualquer").status_code == 401
    assert cliente.post("/rota-que-nao-existe", json={}).status_code == 404
    assert cliente.post("/corretores", headers={"Authorization": "Bearer errado"}, json={}).status_code == 401
    assert AuditoriaRepository().listar(dias=1) == []


def test_evento_de_navegacao_publico_nao_entra_na_trilha():
    """O /eventos é telemetria do site, um POST por clique. Na trilha, era uma linha por clique."""
    cliente.post("/eventos", json={"session_id": "sessao-abc", "tipo": "viewed_imovel",
                                   "dados": {"imovel_id": "SP-0001"}})
    assert AuditoriaRepository().listar(dias=1) == []


def test_erro_de_quem_esta_autenticado_continua_na_trilha():
    assert cliente.delete("/corretores/inexistente", headers=H).status_code == 404
    regs = AuditoriaRepository().listar(dias=1, acao="corretor.removido")
    assert regs and regs[0]["resultado"] == "erro"


def test_exportacao_csv_neutraliza_formula():
    """Uma célula que começa com = + - @ vira fórmula ao abrir o CSV na planilha. O id da entidade
    vem do caminho da URL — quem escolhe é quem fez a requisição."""
    auditar(acao="teste.formula", entidade="lead", entidade_id="=HYPERLINK(\"http://x\",\"clique\")",
            ator_nome="+cmd|' /C calc'!A0", origem="@SOMA(1)", dados={})
    csv = cliente.get("/auditoria/exportar", headers=H, params={"dias": 1}).text
    linha = next(x for x in csv.splitlines() if "teste.formula" in x)
    celulas = linha.split(";")
    assert not any(c.lstrip('"').startswith(("=", "+", "-", "@")) for c in celulas), linha
    assert "'=HYPERLINK" in linha and "'+cmd" in linha and "'@SOMA" in linha


# ---------------------------------------------------------------- S7: teto de corpo sem Content-Length

def _em_pedacos(tamanho: int):
    pedaco = b'{"nome": "' + b"a" * 1024
    yield pedaco
    enviado = len(pedaco)
    while enviado < tamanho:
        yield b"a" * 8192
        enviado += 8192
    yield b'"}'


def test_corpo_chunked_acima_do_teto_e_recusado():
    """Com `Transfer-Encoding: chunked` não há Content-Length, e o teto antigo só olhava ele: o
    corpo inteiro era lido para a memória (pela auditoria) antes de a rota rodar."""
    r = cliente.post("/corretores", headers={**H, "Content-Type": "application/json"},
                     content=_em_pedacos(400 * 1024))
    assert r.status_code == 413
    assert AuditoriaRepository().listar(dias=1, acao="corretor.criado") == []


def test_corpo_chunked_pequeno_passa():
    def corpo():
        yield b'{"session_id": "sessao-abc", "tipo": "opened_chat",'
        yield b' "dados": {}}'
    r = cliente.post("/eventos", headers={"Content-Type": "application/json"}, content=corpo())
    assert r.status_code == 202


# ---------------------------------------------------------------- S14: foto conferida pelos bytes

def _data_url(tipo: str, dados: bytes) -> str:
    return f"data:image/{tipo};base64,{base64.b64encode(dados).decode()}"


def test_foto_com_bytes_que_nao_batem_com_o_tipo_e_recusada(tmp_path, monkeypatch):
    """O prefixo `data:image/png` é escolha de quem envia. HTML com prefixo de imagem ia para o
    disco e era servido pela API — sem nosniff, um navegador podia interpretá-lo como página."""
    from sdr_shared.config import get_settings
    monkeypatch.setattr(get_settings(), "fotos_dir", str(tmp_path))
    html = b"<html><script>alert(document.cookie)</script></html>"
    for tipo, dados in (("png", html), ("jpeg", PNG), ("webp", b"RIFF\x00\x00\x00\x00WAVEfmt ")):
        r = cliente.post("/imoveis/SP-0001/fotos", headers=H, json={"imagem": _data_url(tipo, dados)})
        assert r.status_code == 422, tipo
    assert not any(tmp_path.rglob("*.*"))
    r = cliente.post("/imoveis/SP-0001/fotos", headers=H, json={"imagem": _data_url("png", PNG)})
    assert r.status_code == 201
    nome = r.json()["fotos"][-1].rsplit("/", 1)[1]
    servida = cliente.get(f"/fotos/SP-0001/{nome}")
    assert servida.headers.get("x-content-type-options") == "nosniff"
    cliente.delete(f"/imoveis/SP-0001/fotos/{nome}", headers=H)


def test_foto_do_acervo_tambem_vai_com_nosniff(tmp_path, monkeypatch):
    from sdr_shared.config import get_settings
    (tmp_path / "sala").mkdir()
    (tmp_path / "sala" / "sala-01.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 32)
    monkeypatch.setattr(get_settings(), "fotos_acervo_dir", str(tmp_path))
    r = cliente.get("/acervo/sala/sala-01.jpg")
    assert r.status_code == 200 and r.headers.get("x-content-type-options") == "nosniff"
