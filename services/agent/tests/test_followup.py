"""Cadência do follow-up: quando a Mora volta a falar com quem sumiu, e quando não volta."""
from datetime import datetime, timedelta

import pytest
from sdr_shared import followup as pol
from sdr_shared.db import ConfigRepository
from sdr_shared.messaging import Canal
from sdr_shared.models import CartaoQualificacao, Estagio, Intencao, Lead, Temperatura

from agent.dispatch import reagendar_followup

TERCA_10H = datetime(2026, 9, 8, 10, 0, tzinfo=pol.FUSO)      # dia útil, dentro da janela


@pytest.fixture(autouse=True)
def config_limpa():
    ConfigRepository().salvar("followup", {})
    pol.invalidar_cache()
    yield
    ConfigRepository().salvar("followup", {})
    pol.invalidar_cache()


def _configurar(**valores):
    ConfigRepository().salvar("followup", valores)
    pol.invalidar_cache()


# ---------------------------------------------------------------- cadência

def test_cadencia_padrao_segue_a_sequencia_configurada():
    assert pol.calcular(0, "morno", TERCA_10H) == 120
    assert pol.calcular(1, "morno", TERCA_10H) == 1440
    assert pol.calcular(2, "morno", TERCA_10H) == 4320
    assert pol.calcular(3, "morno", TERCA_10H) is None, "acabaram as tentativas"


def test_o_numero_de_tentativas_vem_da_lista_de_tempos():
    _configurar(tempos_min=[30, 60, 120, 240, 480])
    assert pol.calcular(4, "morno", TERCA_10H) is not None, "cinco tentativas configuradas, cinco acontecem"
    assert pol.calcular(5, "morno", TERCA_10H) is None


def test_tempos_alterados_no_painel_valem_no_proximo_turno():
    _configurar(tempos_min=[15, 45])
    assert pol.calcular(0, "morno", TERCA_10H) == 15
    assert pol.calcular(1, "morno", TERCA_10H) == 45
    assert pol.calcular(2, "morno", TERCA_10H) is None


def test_lead_quente_e_chamado_de_volta_mais_cedo_que_o_frio():
    quente = pol.calcular(0, "quente", TERCA_10H)
    morno = pol.calcular(0, "morno", TERCA_10H)
    frio = pol.calcular(0, "frio", TERCA_10H)
    assert quente < morno < frio
    assert quente == 30 and frio == 240        # 120 × 0,25 e 120 × 2


def test_desligar_o_followup_para_tudo():
    _configurar(ativo=False)
    assert pol.calcular(0, "quente", TERCA_10H) is None


def test_configuracao_invalida_cai_no_padrao_em_vez_de_quebrar():
    _configurar(tempos_min=[], ritmo={"quente": "muito rápido"})
    assert pol.calcular(0, "morno", TERCA_10H) == 120


# ---------------------------------------------------------------- janela civilizada

def test_followup_da_madrugada_e_adiado_para_a_manha():
    tarde_da_noite = datetime(2026, 9, 8, 23, 30, tzinfo=pol.FUSO)
    minutos = pol.calcular(0, "morno", tarde_da_noite)          # 2h → 1h30 da manhã
    quando = tarde_da_noite + timedelta(minutes=minutos)
    assert quando.hour == 8 and quando.day == 9, "espera a janela abrir, não acorda o cliente"


def test_dentro_da_janela_nao_ha_adiamento():
    manha = datetime(2026, 9, 8, 9, 0, tzinfo=pol.FUSO)
    assert pol.calcular(0, "morno", manha) == 120               # 11h ainda é horário civilizado


def test_janela_configuravel():
    _configurar(janela_inicio="09:00", janela_fim="18:00")
    fim_de_tarde = datetime(2026, 9, 8, 17, 0, tzinfo=pol.FUSO)
    quando = fim_de_tarde + timedelta(minutes=pol.calcular(0, "morno", fim_de_tarde))
    assert quando.hour == 9 and quando.day == 9, "19h já está fora da janela configurada"


def test_dias_uteis_pula_o_fim_de_semana():
    _configurar(dias_uteis=True)
    sexta_19h = datetime(2026, 9, 11, 19, 0, tzinfo=pol.FUSO)   # 11/09/2026 é sexta
    quando = sexta_19h + timedelta(minutes=pol.calcular(0, "morno", sexta_19h))
    assert quando.weekday() == 0, "cairia no sábado; espera segunda"


def test_sem_dias_uteis_o_sabado_vale():
    sabado = datetime(2026, 9, 12, 10, 0, tzinfo=pol.FUSO)
    assert pol.calcular(0, "morno", sabado) == 120


def test_nunca_agenda_para_agora_mesmo():
    _configurar(tempos_min=[1])
    assert pol.calcular(0, "quente", TERCA_10H) >= pol.MIN_DELAY


# ---------------------------------------------------------------- agendamento

def _lead(**kw) -> Lead:
    return Lead(id=kw.pop("id", "l_follow"), cartao=CartaoQualificacao(intencao=Intencao.COMPRA), **kw)


def test_agenda_conforme_a_temperatura(infra):
    _, sched = infra
    reagendar_followup(_lead(temperatura=Temperatura.QUENTE), Canal.WHATSAPP, "5511999990000")
    assert sched.agendados["l_follow"][0] == 30


def test_lead_encerrado_nao_recebe_followup(infra):
    _, sched = infra
    for estagio in (Estagio.HANDOFF, Estagio.AGENDADO, Estagio.FRIO):
        sched.agendados["l_follow"] = (99, "{}")
        reagendar_followup(_lead(estagio=estagio), Canal.WHATSAPP, "5511999990000")
        assert "l_follow" not in sched.agendados, f"{estagio} não deveria ter follow-up pendente"


def test_tentativas_esgotadas_limpam_o_agendamento(infra):
    _, sched = infra
    sched.agendados["l_follow"] = (99, "{}")
    reagendar_followup(_lead(followups_enviados=3), Canal.WHATSAPP, "5511999990000")
    assert "l_follow" not in sched.agendados


def test_desligado_no_painel_limpa_o_que_estava_armado(infra):
    _, sched = infra
    sched.agendados["l_follow"] = (99, "{}")
    _configurar(ativo=False)
    reagendar_followup(_lead(), Canal.WHATSAPP, "5511999990000")
    assert "l_follow" not in sched.agendados


def test_cliente_que_responde_em_handoff_nao_leva_followup_por_cima(infra):
    """O corretor está conduzindo; o agente cutucar por cima seria constrangedor."""
    from agent.handler import processar
    from sdr_shared.db import LeadRepository
    from sdr_shared.messaging import MensagemNormalizada, TipoMensagem
    _, sched = infra
    LeadRepository().upsert(_lead(id="l_hand", estagio=Estagio.HANDOFF))
    sched.agendados["l_hand"] = (99, "{}")
    processar(MensagemNormalizada(lead_id="l_hand", canal=Canal.WHATSAPP, identificador_canal="5511999990000",
                                  conteudo="e aí, tem novidade?", tipo=TipoMensagem.TEXTO))
    assert "l_hand" not in sched.agendados


# ---------------------------------------------------------------- prévia

def test_previa_mostra_quando_cada_tentativa_cairia():
    p = pol.previa("morno", TERCA_10H)
    assert [x["tentativa"] for x in p] == [1, 2, 3]
    assert [x["minutos"] for x in p] == [120, 1440, 4320]
    assert all(pol.dentro_da_janela(datetime.fromisoformat(x["em"])) for x in p), "toda tentativa em horário civilizado"


def test_previa_respeita_a_temperatura():
    assert pol.previa("quente", TERCA_10H)[0]["minutos"] < pol.previa("frio", TERCA_10H)[0]["minutos"]


# ---------------------------------------------------------------- formato anterior da tela

def test_configuracao_antiga_continua_valendo():
    """Quem salvou no formato de três tempos fixos não perde a configuração nem recebe erro."""
    _configurar(primeiro_min=30, segundo_h=2, terceiro_h=8)
    assert pol.calcular(0, "morno", TERCA_10H) == 30
    assert pol.calcular(1, "morno", TERCA_10H) == 120
    assert pol.calcular(2, "morno", TERCA_10H) == 480


def test_maximo_antigo_vira_o_tamanho_da_lista():
    _configurar(primeiro_min=30, segundo_h=2, terceiro_h=8, maximo=2)
    assert pol.calcular(1, "morno", TERCA_10H) == 120
    assert pol.calcular(2, "morno", TERCA_10H) is None, "o antigo 'máximo: 2' são duas tentativas"


def test_formato_novo_tem_precedencia_sobre_o_antigo():
    _configurar(primeiro_min=999, tempos_min=[15, 45])
    assert pol.calcular(0, "morno", TERCA_10H) == 15


def test_chave_desconhecida_no_banco_e_ignorada():
    _configurar(tempos_min=[20], coisa_que_nao_existe=True)
    assert pol.calcular(0, "morno", TERCA_10H) == 20
