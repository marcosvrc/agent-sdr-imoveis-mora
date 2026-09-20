"""Ajustes de operação vindos do painel — e a distinção que decide se a tela obedece.

"Vazio" e "desligado" precisam ser valores DIFERENTES. Se zero significasse as duas coisas, apagar
o campo no painel nunca desfaria algo herdado do `.env`, e o operador ficaria mexendo numa tela que
não responde. A lição veio do provedor de reserva e está aplicada aqui desde o começo.
"""
import pytest

from sdr_shared.config import get_settings
from sdr_shared.db import operacao
from sdr_shared.ports import factory


@pytest.fixture(autouse=True)
def cache_limpo():
    yield
    operacao.invalidar_cache_operacao()
    get_settings.cache_clear()


def _painel(valor: dict):
    operacao._cache.update(em=9e18, valor=valor)


def test_vazio_delega_ao_ambiente():
    _painel({"llm_timeout_s": ""})
    assert operacao.numero("llm_timeout_s") is None
    _painel({})
    assert operacao.numero("llm_timeout_s") is None


def test_zero_e_resposta_nao_ausencia():
    """É a diferença entre 'não opinei' e 'desligue'. Sem ela, a tela não consegue desligar o que
    veio do ambiente."""
    _painel({"acervo_refresh_s": 0})
    assert operacao.numero("acervo_refresh_s") == 0.0


def test_timeout_do_painel_vence_o_ambiente(monkeypatch):
    monkeypatch.setenv("SDR_LLM_TIMEOUT_S", "45")
    get_settings.cache_clear()
    _painel({"llm_timeout_s": 12})
    assert factory._timeout_do_painel() == 12.0


def test_timeout_zero_nao_desliga_a_espera():
    """Aqui zero seria 'sem espera nenhuma', que não é uma configuração sensata — cai no ambiente."""
    _painel({"llm_timeout_s": 0})
    assert factory._timeout_do_painel() is None


def test_valor_ilegivel_nao_derruba_o_turno():
    """Alguém gravou texto onde era número: melhor cair no ambiente que estourar no meio da conversa."""
    _painel({"llm_timeout_s": "quarenta"})
    assert operacao.numero("llm_timeout_s") is None
