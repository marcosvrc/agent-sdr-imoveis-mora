"""Regras puras do CRM: funil, custos e normalização de contato.

Sem banco e sem HTTP de propósito — é o que permite cobrir os casos de canto, que aqui são a
maioria do valor.
"""
import pytest

from sdr_crm.dominio import contatos, custos
from sdr_crm.dominio.funil import Contexto, avaliar, estagio_apos_cancelar_visita

COMPLETO = {"city": "São Paulo", "budget_max_cents": 800_000_00}


def ctx(stage="in_service", *, purpose="rent", atendimento="agent", prefs=None, visita=False):
    return Contexto(stage=stage, purpose=purpose, atendimento=atendimento,
                    preferencias=COMPLETO if prefs is None else prefs,
                    tem_visita_confirmada_futura=visita)


# --------------------------------------------------------------------------- funil

def test_caminho_feliz_ate_qualificado():
    assert avaliar(ctx("new"), "in_service", humano=False, motivo=None).ok
    assert avaliar(ctx("in_service"), "qualified", humano=False, motivo=None).ok


def test_qualificar_sem_orcamento_lista_os_campos():
    v = avaliar(ctx("in_service", prefs={"city": "São Paulo"}), "qualified", humano=False, motivo=None)
    assert not v.ok
    assert v.code == "QUALIFICATION_INCOMPLETE"
    # A lista é o que permite o agente perguntar a coisa certa em vez de tentar de novo às cegas.
    assert v.detalhes == {"missing_fields": ["budget_max_cents"]}


def test_purpose_vem_da_oportunidade_e_nao_das_preferencias():
    # `purpose` é campo da oportunidade; se ele não contasse como preenchido, toda qualificação
    # reclamaria de um dado que já existe.
    v = avaliar(ctx("in_service", prefs=COMPLETO), "qualified", humano=False, motivo=None)
    assert v.ok


def test_agente_nao_marca_ganho():
    v = avaliar(ctx("negotiation"), "won", humano=False, motivo=None)
    assert (v.ok, v.code) == (False, "FORBIDDEN")


def test_agente_nao_declara_perda_nem_com_motivo():
    v = avaliar(ctx("in_service"), "lost", humano=False, motivo="sumiu")
    assert (v.ok, v.code) == (False, "FORBIDDEN")


def test_humano_perde_com_motivo_e_nao_perde_sem():
    assert avaliar(ctx("in_service"), "lost", humano=True, motivo="comprou com outro").ok
    v = avaliar(ctx("in_service"), "lost", humano=True, motivo="   ")
    assert (v.ok, v.code) == (False, "REASON_REQUIRED")


def test_visit_scheduled_exige_visita_confirmada():
    assert not avaliar(ctx("qualified"), "visit_scheduled", humano=True, motivo=None).ok
    assert avaliar(ctx("qualified", visita=True), "visit_scheduled", humano=True, motivo=None).ok


def test_salto_de_estagio_recusado():
    v = avaliar(ctx("new"), "qualified", humano=True, motivo=None)
    assert (v.ok, v.code) == (False, "INVALID_TRANSITION")
    assert v.detalhes == {"allowed": ["in_service", "lost"]}


def test_atendimento_humano_congela_o_agente_mas_nao_o_corretor():
    c = ctx("in_service", atendimento="human_pending")
    assert avaliar(c, "qualified", humano=False, motivo=None).code == "HUMAN_IN_CONTROL"
    assert avaliar(c, "qualified", humano=True, motivo=None).ok


def test_ordem_das_checagens_403_antes_de_campos_faltantes():
    # Oportunidade em negociação, preferências vazias: a resposta tem de ser "isto é humano",
    # e não uma lista de campos que levaria o agente a insistir.
    v = avaliar(ctx("negotiation", prefs={}), "won", humano=False, motivo=None)
    assert v.code == "FORBIDDEN"


def test_reabertura_exige_motivo_e_e_humana():
    assert avaliar(ctx("won"), "in_service", humano=False, motivo="cliente voltou").code == "FORBIDDEN"
    assert avaliar(ctx("won"), "in_service", humano=True, motivo="cliente voltou").ok


def test_cancelar_visita_volta_para_qualified_mas_nao_regride_negociacao():
    assert estagio_apos_cancelar_visita(ctx("visit_scheduled")) == "qualified"
    assert estagio_apos_cancelar_visita(ctx("visit_scheduled", visita=True)) is None
    assert estagio_apos_cancelar_visita(ctx("negotiation")) is None


# --------------------------------------------------------------------------- custos

ALUGUEL = {"purpose": "rent", "base_price_cents": 300_000, "condo_monthly_cents": 80_000,
           "property_tax_monthly_cents": 20_000, "other_monthly_cents": 0}


def test_total_mensal_soma_os_quatro_componentes():
    c = custos.calcular(ALUGUEL)
    assert c.monthly_total_cents == 400_000
    assert not c.incompleto


def test_outros_igual_a_zero_e_conhecido_e_nao_torna_incompleto():
    # A diferença entre 0 e None é a razão de ser deste módulo: zero é uma afirmação.
    c = custos.calcular({**ALUGUEL, "other_monthly_cents": 0})
    assert (c.monthly_total_cents, c.incompleto) == (400_000, False)


def test_componente_desconhecido_nao_vira_zero():
    c = custos.calcular({**ALUGUEL, "condo_monthly_cents": None})
    assert c.monthly_total_cents is None
    assert c.incompleto and c.faltando == ("condo_monthly_cents",)


def test_compra_nao_tem_total_mensal():
    c = custos.calcular({"purpose": "buy", "base_price_cents": 650_000_00,
                         "condo_monthly_cents": None, "property_tax_monthly_cents": None,
                         "other_monthly_cents": None})
    assert c.monthly_total_cents is None
    assert not c.incompleto        # não é incompleto: compra simplesmente não tem essa grandeza


@pytest.mark.parametrize(("teto", "base", "esperado"), [
    (400_000, "monthly_total", True),
    (399_999, "monthly_total", False),
    (300_000, "base_price", True),
    (None, "monthly_total", True),
])
def test_cabe_no_orcamento(teto, base, esperado):
    assert custos.cabe_no_orcamento(ALUGUEL, teto, base) is esperado


def test_orcamento_indeterminado_quando_o_total_e_desconhecido():
    incompleto = {**ALUGUEL, "property_tax_monthly_cents": None}
    assert custos.cabe_no_orcamento(incompleto, 400_000, "monthly_total") is None
    # Na base de preço, o mesmo imóvel continua respondível: o aluguel em si é conhecido.
    assert custos.cabe_no_orcamento(incompleto, 400_000, "base_price") is True


# --------------------------------------------------------------------------- contatos

@pytest.mark.parametrize(("entrada", "esperado"), [
    ("  Cliente0001@Example.COM ", "cliente0001@example.com"),
    ("", None),
    (None, None),
])
def test_normalizar_email(entrada, esperado):
    assert contatos.normalizar_email(entrada) == esperado


def test_email_com_ponto_e_mais_nao_e_alterado():
    # Regra de provedor aplicada a todo mundo funde clientes distintos.
    assert contatos.normalizar_email("a.b+promo@gmail.com") == "a.b+promo@gmail.com"


@pytest.mark.parametrize(("entrada", "esperado"), [
    ("(11) 99999-0000", "+5511999990000"),
    ("11999990000", "+5511999990000"),
    ("+55 11 99999-0000", None),          # com '+' exige E.164 já limpo
    ("+5511999990000", "+5511999990000"),
    ("1234", None),
    ("", None),
])
def test_normalizar_telefone(entrada, esperado):
    assert contatos.normalizar_telefone(entrada) == esperado


def test_identificadores_so_traz_o_que_existe():
    assert contatos.identificadores({"email": " A@B.com", "phone_e164": None,
                                     "external_contact_id": " sim-chat-001 "}) == {
        "email": "a@b.com", "external_contact_id": "sim-chat-001"}


def test_comecar_atendimento_nao_exige_motivo_mas_reabrir_exige():
    # `in_service` aparece duas vezes na tabela de transições com significados opostos: início de
    # atendimento (vindo de `new`) e reabertura (vindo de `won`/`lost`). Só a segunda pede motivo.
    assert avaliar(ctx("new"), "in_service", humano=False, motivo=None).ok
    assert avaliar(ctx("lost"), "in_service", humano=True, motivo=None).code == "REASON_REQUIRED"
