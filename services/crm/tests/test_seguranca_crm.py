"""Itens da revisão de segurança que vivem no CRM: teto de corpo contado em bytes e login que não
revela, pelo tempo de resposta, quais e-mails existem."""
from sdr_crm.api import auth as autenticacao


# ---------------------------------------------------------------- S7: corpo chunked

def _em_pedacos(tamanho: int):
    yield b'{"email": "a@example.com", "password": "'
    enviado = 0
    while enviado < tamanho:
        yield b"a" * 8192
        enviado += 8192
    yield b'"}'


def test_corpo_chunked_acima_do_teto_recebe_413(cliente):
    """O teto de 256 KB só olhava o Content-Length; com `Transfer-Encoding: chunked` não há
    cabeçalho e o corpo inteiro era lido."""
    r = cliente.post("/v1/auth/login", headers={"Content-Type": "application/json"},
                     content=_em_pedacos(400 * 1024))
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_corpo_chunked_pequeno_segue_normal(cliente):
    def corpo():
        yield b'{"email": "ninguem@example.com",'
        yield b' "password": "x"}'
    r = cliente.post("/v1/auth/login", headers={"Content-Type": "application/json"}, content=corpo())
    assert r.status_code == 401


def test_content_length_acima_do_teto_continua_recusado_antes_de_ler(cliente):
    r = cliente.post("/v1/auth/login", headers={"Content-Type": "application/json"},
                     content=b"x" * (300 * 1024))
    assert r.status_code == 413 and r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


# ---------------------------------------------------------------- S11: tempo do login

def test_email_inexistente_tambem_paga_o_argon2(monkeypatch):
    """Para e-mail inexistente a verificação voltava na hora, sem Argon2 (~dezenas de ms a menos):
    medindo o tempo de resposta dava para saber quais e-mails existem na base. Contar chamadas é
    determinístico; medir tempo num teste não seria."""
    chamadas = []
    real = autenticacao._hasher

    class Espiao:
        def hash(self, senha):
            return real.hash(senha)

        def verify(self, h, s):
            chamadas.append(h)
            return real.verify(h, s)

    monkeypatch.setattr(autenticacao, "_hasher", Espiao())
    assert autenticacao.conferir_senha(None, "qualquer") is False
    assert autenticacao.conferir_senha("", "qualquer") is False
    assert len(chamadas) == 2, "sem usuário, o Argon2 tem de rodar do mesmo jeito"
    hash_real = autenticacao.hash_senha("certa")
    assert autenticacao.conferir_senha(hash_real, "certa") is True
