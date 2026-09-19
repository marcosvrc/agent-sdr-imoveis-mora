"""Captura progressiva de contato: nome cedo, um contato só no momento do compromisso, nunca os três de uma vez."""
import pytest
from sdr_shared.messaging import Canal
from sdr_shared.models import CartaoQualificacao, Intencao, Lead
from agent.nodes.qualificador import _absorver_contato, _contexto_contato


def _lead(**kw) -> Lead:
    return Lead(id=kw.pop("id", "web_sess-1"), cartao=kw.pop("cartao", CartaoQualificacao()), **kw)


def _state(lead, canal=Canal.WEB):
    from sdr_shared.messaging import MensagemNormalizada, TipoMensagem
    return {"lead": lead, "entrada": MensagemNormalizada(lead_id=lead.id, canal=canal, identificador_canal="x",
                                                        conteudo="oi", tipo=TipoMensagem.TEXTO)}


def test_contato_informado_na_conversa_vira_dado_do_lead():
    lead = _lead(cartao=CartaoQualificacao(nome_informado=" Marcos ", telefone_informado="(11) 98888-7777",
                                           email_informado=" MARCOS@Exemplo.com "))
    _absorver_contato(lead)
    assert lead.nome == "Marcos" and lead.telefone == "11988887777" and lead.email == "marcos@exemplo.com"


@pytest.mark.parametrize("telefone", ["123", "sim, pode ligar", "0800", "9" * 20])
def test_telefone_invalido_nao_entra_no_cadastro(telefone):
    lead = _lead(cartao=CartaoQualificacao(telefone_informado=telefone))
    _absorver_contato(lead)
    assert lead.telefone is None, "o corretor não pode receber um telefone que não disca"


def test_contato_existente_nao_e_sobrescrito():
    lead = _lead(nome="Marcos", telefone="11911112222",
                 cartao=CartaoQualificacao(nome_informado="Outro", telefone_informado="11933334444"))
    _absorver_contato(lead)
    assert lead.nome == "Marcos" and lead.telefone == "11911112222"


def test_canal_externo_nunca_pede_contato():
    """No Telegram o identificador e o nome já vieram do perfil; pedir de novo é burocracia."""
    lead = _lead(id="tg_5511", cartao=CartaoQualificacao(intencao=Intencao.COMPRA))
    assert _contexto_contato(lead, _state(lead, Canal.TELEGRAM)) == ""


def test_no_web_pede_o_nome_antes_de_qualquer_contato():
    lead = _lead()
    ctx = _contexto_contato(lead, _state(lead))
    assert "nome" in ctx.lower()
    assert "telefone" not in ctx.lower() and "e-mail" not in ctx.lower(), "nunca os três de uma vez"


def test_pede_um_contato_so_quando_ha_compromisso():
    cheio = CartaoQualificacao(intencao=Intencao.COMPRA, regiao="zona_sul", bairros=["pinheiros"],
                               preco_max=800000, quartos=2, tipo_imovel="apartamento", urgencia="imediata",
                               pediu_visita=True)
    sem_contato = _lead(nome="Marcos", cartao=cheio)
    if cheio.completo():
        ctx = _contexto_contato(sem_contato, _state(sem_contato))
        assert ctx and "telefone" in ctx.lower()
        assert "cpf" not in ctx.lower() and "renda" not in ctx.lower()

    com_contato = _lead(nome="Marcos", telefone="11988887777",
                        cartao=cheio.model_copy(update={"telefone_informado": "11988887777"}))
    assert _contexto_contato(com_contato, _state(com_contato)) == "", "já tem contato: não insiste"
