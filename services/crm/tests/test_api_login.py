"""Login: a única rota que se atinge sem credencial, e por isso a única que precisava de teto próprio."""
import uuid

from sdr_crm.api import auth as autenticacao
from sdr_crm.api.contexto import limpar_limites
from sdr_crm.config import get_settings
from sdr_crm.db.connection import transacao

SENHA = "Senha-de-teste-123"


def _usuario_com_email() -> str:
    email = f"{uuid.uuid4().hex[:8]}@example.com"
    with transacao() as conn:
        conn.execute("INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, 'broker')",
                     ("Corretora", email, autenticacao.hash_senha(SENHA)))
    return email


def test_login_certo_entra_e_errado_recebe_a_mesma_mensagem(cliente):
    email = _usuario_com_email()
    ok = cliente.post("/v1/auth/login", json={"email": email, "password": SENHA})
    assert ok.status_code == 200 and "crm_session" in ok.cookies
    errada = cliente.post("/v1/auth/login", json={"email": email, "password": "outra"})
    inexistente = cliente.post("/v1/auth/login", json={"email": "ninguem@example.com", "password": SENHA})
    assert errada.status_code == inexistente.status_code == 401
    assert errada.json()["error"]["message"] == inexistente.json()["error"]["message"]


def test_login_tem_teto_por_ip(cliente):
    """Antes deste teste, o login não passava pelo `Ctx` e o limite geral nunca o via: dava para
    testar senha sem parar. O teto vale mesmo com e-mails diferentes a cada tentativa."""
    teto = get_settings().login_tentativas_por_minuto
    for i in range(teto):
        r = cliente.post("/v1/auth/login", json={"email": f"{i}@example.com", "password": "x"})
        assert r.status_code == 401, i
    r = cliente.post("/v1/auth/login", json={"email": "mais-um@example.com", "password": "x"})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED" and "Retry-After" in r.headers


def test_teto_por_email_vale_mesmo_de_ips_diferentes(cliente, monkeypatch):
    """Quem varre senhas de UMA conta a partir de vários lugares esbarra na chave por e-mail."""
    from sdr_crm.api import contexto
    teto = get_settings().login_tentativas_por_minuto
    original = contexto.conferir_limite
    # Cada tentativa vem de um IP "novo": só a chave do e-mail pode barrar.
    chamadas = {"n": 0}

    def com_ip_diferente(chave, limite=None):
        if chave.startswith("login:ip:"):
            chamadas["n"] += 1
            chave = f"login:ip:10.0.0.{chamadas['n']}"
        return original(chave, limite)

    monkeypatch.setattr(contexto, "conferir_limite", com_ip_diferente)
    for _ in range(teto):
        assert cliente.post("/v1/auth/login", json={"email": "Alvo@Example.com", "password": "x"}).status_code == 401
    # Caixa e espaços não abrem uma chave nova.
    r = cliente.post("/v1/auth/login", json={"email": "  alvo@example.com ", "password": "x"})
    assert r.status_code == 429


def test_senha_gigante_e_recusada_antes_do_argon2(cliente):
    r = cliente.post("/v1/auth/login", json={"email": "a@example.com", "password": "x" * 257})
    assert r.status_code == 422


def test_login_valido_tambem_conta_no_teto(cliente):
    """Login certo conta igual: senão bastaria acertar uma vez para zerar a janela."""
    email = _usuario_com_email()
    teto = get_settings().login_tentativas_por_minuto
    limpar_limites()
    for _ in range(teto):
        assert cliente.post("/v1/auth/login", json={"email": email, "password": SENHA}).status_code == 200
    assert cliente.post("/v1/auth/login", json={"email": email, "password": SENHA}).status_code == 429
