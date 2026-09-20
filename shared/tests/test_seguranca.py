"""Credencial do painel e `state` do OAuth — os dois portões fora do authorizer do API Gateway."""
import os

import pytest

os.environ["SDR_PROFILE"] = "local"
os.environ["SDR_SESSAO_SECRET"] = "segredo-de-teste"

from sdr_shared.config import get_settings          # noqa: E402
from sdr_shared.seguranca import oauth, painel      # noqa: E402


def _com_ambiente(**env):
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    get_settings.cache_clear()


def test_painel_local_aceita_token_de_dev():
    _com_ambiente(SDR_PROFILE="local", SDR_PAINEL_TOKEN=None)
    assert painel.valido("dev-token")
    assert not painel.valido("outro") and not painel.valido("") and not painel.valido(None)


def test_painel_fora_do_local_e_fail_closed():
    """Sem SDR_PAINEL_TOKEN configurado, fora do perfil local nada é aceito — nem o token de dev."""
    _com_ambiente(SDR_PROFILE="producao", SDR_PAINEL_TOKEN=None)
    assert not painel.valido("dev-token")
    _com_ambiente(SDR_PAINEL_TOKEN="token-de-producao")
    assert painel.valido("token-de-producao") and not painel.valido("dev-token")
    _com_ambiente(SDR_PROFILE="local", SDR_PAINEL_TOKEN=None)


def test_oauth_state_precisa_ser_emitido_por_nos():
    """O id do corretor é derivado do nome (cor_ana-souza): se o `state` fosse ele cru, bastava
    adivinhar para ligar a própria conta Google à agenda de outra pessoa."""
    assert oauth.validar("cor_ana-souza") is None
    assert oauth.validar("cor_ana-souza.9999999999.assinatura-falsa") is None
    assert oauth.validar(None) is None and oauth.validar("") is None


def test_oauth_state_legitimo_volta_com_o_corretor():
    state = oauth.assinar("cor_ana-souza")
    assert oauth.validar(state) == "cor_ana-souza"
    _corpo, expira, assinatura = state.split(".")
    assert oauth.validar(f"cor_outro.{expira}.{assinatura}") is None, "assinatura é presa ao corretor"


def test_oauth_state_expira():
    assert oauth.validar("cor_ana-souza.1.qualquer") is None


# ---------------------------------------------------------------- cofre

def test_refresh_token_fica_cifrado_no_banco_e_volta_legivel(monkeypatch):
    """Estava em texto puro: um dump do banco carregava a agenda de todos os corretores."""
    import uuid
    from sdr_shared.config import get_settings
    from sdr_shared.db import CorretorRepository
    from sdr_shared.db.connection import get_pool
    from sdr_shared.seguranca import cofre
    monkeypatch.setattr(get_settings(), "sessao_secret", "segredo-de-teste")
    from sdr_shared.models import Corretor
    repo = CorretorRepository()
    cid = f"cofre-{uuid.uuid4().hex[:8]}"
    repo.upsert(Corretor(id=cid, nome="Corretora do Cofre"))
    repo.salvar_credencial_calendario(cid, "1//refresh-super-secreto")
    with get_pool().connection() as conn:
        cru = conn.execute("SELECT calendario_refresh_token FROM corretores WHERE id = %s", (cid,)).fetchone()["calendario_refresh_token"]
    assert cru.startswith(cofre.PREFIXO) and "refresh-super-secreto" not in cru
    assert repo.credencial_calendario(cid) == "1//refresh-super-secreto"
    # valor legado (gravado antes da cifra) continua legível
    with get_pool().connection() as conn:
        conn.execute("UPDATE corretores SET calendario_refresh_token = 'legado-em-claro' WHERE id = %s", (cid,))
    assert repo.credencial_calendario(cid) == "legado-em-claro"
    repo.salvar_credencial_calendario(cid, None)
    assert repo.credencial_calendario(cid) is None


def test_segredo_trocado_nao_vira_token_vazio_em_silencio(monkeypatch):
    from sdr_shared.config import get_settings
    from sdr_shared.seguranca import cofre
    monkeypatch.setattr(get_settings(), "sessao_secret", "chave-a")
    cifrado = cofre.cifrar("x")
    monkeypatch.setattr(get_settings(), "sessao_secret", "chave-b")
    with pytest.raises(Exception):
        cofre.decifrar(cifrado)


def test_sem_segredo_guarda_em_claro_e_avisa(monkeypatch, caplog):
    """Sem SDR_SESSAO_SECRET cada processo teria chave própria: a API cifraria o que o worker
    não lê. Guardar em claro é o comportamento antigo — e o aviso é o que impede o silêncio."""
    from sdr_shared.config import get_settings
    from sdr_shared.seguranca import cofre
    monkeypatch.setattr(get_settings(), "sessao_secret", None)
    monkeypatch.setattr(cofre, "_AVISOU", False)
    with caplog.at_level("WARNING", logger="seguranca"):
        assert cofre.cifrar("x") == "x"
    assert any("sem cifra" in r.message for r in caplog.records)
