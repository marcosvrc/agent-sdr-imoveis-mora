"""A porta de CRM: o que ela garante quando o CRM não está lá.

O caminho feliz é provado em `test_crm_ponte.py`, contra um CRM de verdade atrás de MCP. Aqui fica
a outra metade, que é a que decide se dá para colocar isso no caminho de uma conversa: **a Mora tem
de atender igual com o CRM ausente, mal configurado ou fora do ar**. Um agente que para de
responder porque o sistema comercial caiu transformou um problema interno num problema do cliente.
"""
import pytest

from sdr_shared.adapters.crm.ausente import CRMAusente
from sdr_shared.adapters.crm.via_mcp import CRMviaMCP, _versao

OPERACOES = ("garantir_lead", "garantir_oportunidade", "registrar_interacao",
             "atualizar_preferencias", "mover_estagio", "encaminhar", "consultar_historico")


@pytest.fixture(autouse=True)
def _porta_limpa():
    from sdr_shared.ports import get_crm
    get_crm.cache_clear()
    yield
    get_crm.cache_clear()


# --------------------------------------------------------------------------- escolha do adaptador

def test_sem_configuracao_o_padrao_e_nao_ter_crm(monkeypatch):
    """Rodar a Mora sozinha é o caso normal, não a exceção."""
    from sdr_shared.ports import get_crm
    monkeypatch.delenv("SDR_CRM_URL", raising=False)
    monkeypatch.delenv("SDR_CRM_TOKEN", raising=False)
    assert isinstance(get_crm(), CRMAusente)


def test_url_sem_token_nao_habilita(monkeypatch):
    """No compose a URL tem padrão. Sem token o servidor recusa, e cada turno viraria um 401 no log
    de quem nunca pediu a integração — então "configurado" é ter os dois."""
    monkeypatch.setenv("SDR_CRM_URL", "http://crm-mcp:8200/mcp")
    monkeypatch.delenv("SDR_CRM_TOKEN", raising=False)
    assert CRMviaMCP().habilitado() is False
    assert CRMviaMCP(url="http://x/mcp", token="t").habilitado() is True


# --------------------------------------------------------------------------- degradar, não quebrar

def test_adaptador_ausente_aceita_todas_as_operacoes():
    """Se faltar um método aqui, o nó que o chamar quebra só quando não houver CRM — ou seja, na
    demonstração e em mais nada. Este teste percorre a porta inteira."""
    with CRMAusente().sessao() as s:
        for nome in OPERACOES:
            assert hasattr(s, nome), f"{nome} falta no adaptador sem CRM"
        assert s.garantir_lead(object()) is None
        assert s.consultar_historico("x") == []
        assert s.encaminhar("a", "b", motivo="m", resumo="r") is False


def test_crm_fora_do_ar_entrega_sessao_inerte(caplog):
    """Porta fechada não pode virar exceção na conversa. A sessão vem inerte e quem chama segue o
    mesmo caminho dos outros casos, sem `try` em volta de cada publicação."""
    crm = CRMviaMCP(url="http://127.0.0.1:9/mcp", token="qualquer")   # porta 9: descarte
    with crm.sessao() as s:
        for nome in OPERACOES:
            assert hasattr(s, nome)
        assert s.garantir_lead(object()) is None
        assert s.consultar_historico("x") == []


def test_excecao_do_chamador_atravessa_a_sessao_inerte():
    """Só o caminho inerte. O caminho com conexão aberta é outro bloco de código e está coberto em
    `test_crm_ponte.py`, onde há um servidor de verdade — aqui a conexão falha antes e este teste
    nunca chegaria lá. Escrito primeiro como se cobrisse os dois; a mutação mostrou que não."""
    crm = CRMviaMCP(url="http://127.0.0.1:9/mcp", token="qualquer")
    with pytest.raises(ZeroDivisionError):
        with crm.sessao():
            raise ZeroDivisionError("falha do chamador, não do CRM")


# --------------------------------------------------------------------------- versão da oportunidade

def test_versao_prefere_o_campo_da_oportunidade():
    """As rotas de preferência e de transição devolvem o recurso alterado MAIS a nova versão da
    oportunidade, num campo à parte. Ler `version` ali pegaria a versão do objeto errado, e o
    `If-Match` seguinte iria com número velho — um 412 no turno seguinte, longe da causa."""
    assert _versao({"version": 3}) == 3
    assert _versao({"opportunity_version": 7, "version": 1}) == 7
    assert _versao({}) is None
    assert _versao(None) is None
