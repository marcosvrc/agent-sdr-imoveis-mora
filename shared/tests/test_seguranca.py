"""Credencial do painel e `state` do OAuth — os dois portões fora do authorizer do API Gateway."""
import os

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
    """Sem SDR_PAINEL_TOKEN configurado, o perfil aws não aceita nada — nem o token de dev."""
    _com_ambiente(SDR_PROFILE="aws", SDR_PAINEL_TOKEN=None)
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
