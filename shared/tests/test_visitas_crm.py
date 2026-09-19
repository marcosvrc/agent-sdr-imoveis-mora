"""Agenda e pedido de visita, contra o CRM de verdade.

O que está sob prova é uma distinção de negócio, não um caminho feliz: **a Mora pede, o corretor
confirma**. Um agente que grava "visita marcada" no CRM cria um cliente esperando na porta de um
imóvel no sábado, com um corretor que nunca soube. Então o teste olha o `status` da visita e o
estágio da oportunidade, que é onde a diferença aparece para quem vai agir.
"""
import os
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import psycopg.rows
import pytest

from sdr_shared.crm import horarios_do_imovel, pedir_visita, vinculo
from sdr_shared.models import Estagio, Intencao, Lead

DSN_CRM = os.environ.get("CRM_TEST_DSN", "postgresql://sdr:sdr@127.0.0.1:5432/crm_test")


@pytest.fixture
def imovel_com_horario(crm_api, token_crm):
    """Um imóvel com código conhecido e um horário livre, como o acervo real teria.

    Escrito direto no banco do CRM porque cadastrar imóvel e abrir agenda são ações HUMANAS ali —
    a credencial de serviço é recusada, com razão. Aqui isso é o cenário, não o comportamento sob
    prova. A primeira versão deste teste chamava a API e caía num `pytest.skip`, o que deixava
    cinco testes verdes sem nunca rodar: skip silencioso é tão ruim quanto teste falso.
    """
    codigo = f"SP-T{uuid.uuid4().hex[:6].upper()}"
    inicio = (datetime.now(UTC) + timedelta(days=3)).replace(minute=0, second=0, microsecond=0)
    imovel_id, slot_id = str(uuid.uuid4()), str(uuid.uuid4())
    # `row_factory=dict_row`: a conexão crua devolve tuplas, e ler `linha["id"]` nelas estoura com
    # "tuple indices must be integers". O pool da aplicação já vem configurado assim, o que torna
    # fácil escrever aqui um acesso que só falha aqui.
    with psycopg.connect(DSN_CRM, autocommit=True, row_factory=psycopg.rows.dict_row) as conn:
        # Um corretor NOVO por cenário. Reaproveitar o mesmo faria o segundo teste esbarrar no
        # `EXCLUDE` que impede dois horários sobrepostos do mesmo corretor — o CRM funcionando
        # como deve, e o teste construído de um jeito que não sobrevive a ter irmãos.
        corretor = conn.execute(
            "INSERT INTO users (id, name, email, role, active) "
            "VALUES (%s,%s,%s,'broker',true) RETURNING id",
            (str(uuid.uuid4()), "Corretor de Teste",
             f"corretor-{uuid.uuid4().hex[:8]}@example.com")).fetchone()
        conn.execute(
            """INSERT INTO properties (id, code, title, description, city, neighborhood, type,
                   purpose, base_price_cents, condo_monthly_cents, property_tax_monthly_cents,
                   other_monthly_cents, bedrooms, parking, status)
               VALUES (%s,%s,%s,%s,'São Paulo','Pinheiros','apartamento','rent',
                       300000, 50000, 10000, 0, 2, 1, 'available')""",
            (imovel_id, codigo, "Apartamento de teste (endereço fictício)", "Imóvel sintético."))
        conn.execute(
            "INSERT INTO availability_slots (id, property_id, broker_id, starts_at, ends_at) "
            "VALUES (%s,%s,%s,%s,%s)",
            (slot_id, imovel_id, corretor["id"], inicio, inicio + timedelta(hours=1)))
    return codigo, imovel_id, slot_id, inicio


@pytest.fixture
def lead_qualificado(ligado, crm_api, token_crm):
    from sdr_shared.crm import publicar_turno
    from sdr_shared.db import LeadRepository
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem

    lead = Lead(id=f"lead-vis-{uuid.uuid4().hex[:8]}", nome="Quem Quer Visitar",
                estagio=Estagio.QUALIFICADO, email=f"visita-{uuid.uuid4().hex[:8]}@exemplo.com")
    lead.cartao.intencao = Intencao.ALUGUEL
    lead.cartao.regiao, lead.cartao.bairros = "São Paulo", ["Pinheiros"]
    lead.cartao.preco_max, lead.cartao.quartos = 4000.0, 2
    lead.cartao.urgencia = "3 meses"
    lead = LeadRepository().upsert(lead)

    entrada = MensagemNormalizada(lead_id=lead.id, canal=Canal.WEB, tipo=TipoMensagem.TEXTO,
                                  identificador_canal="s", conteudo="quero visitar")
    publicar_turno(lead, entrada, texto_saida="claro")     # abre cliente e oportunidade no CRM
    assert vinculo.buscar(lead.id) is not None, "sem vínculo não há a que pendurar o pedido"
    return lead


# --------------------------------------------------------------------------- disponibilidade

def test_horarios_vem_do_crm_quando_ha_imovel(ligado, imovel_com_horario):
    codigo, _, slot_id, inicio = imovel_com_horario
    horarios = horarios_do_imovel(codigo)
    assert horarios, "o imóvel tem horário livre no CRM"
    achado = next((h for h in horarios if h.slot_id == slot_id), None)
    assert achado is not None
    assert achado.inicio.replace(tzinfo=None) == inicio.replace(tzinfo=None)


def test_codigo_desconhecido_nao_inventa_indisponibilidade(ligado):
    """Lista vazia significa "não sei" e quem chama cai na agenda do corretor. Se isto fosse lido
    como "não há", a Mora recusaria uma visita que existe."""
    assert horarios_do_imovel("SP-NAO-EXISTE") == []


def test_sem_imovel_nao_pergunta_ao_crm(ligado):
    """Antes de o cliente escolher um imóvel não há disponibilidade a consultar — e este caminho
    nem deve alcançar o CRM."""
    assert horarios_do_imovel(None) == []


def test_sem_crm_a_agenda_continua_sendo_a_do_corretor(monkeypatch):
    monkeypatch.delenv("SDR_CRM_URL", raising=False)
    monkeypatch.delenv("SDR_CRM_TOKEN", raising=False)
    assert horarios_do_imovel("SP-0001") == []


# --------------------------------------------------------------------------- pedir ≠ agendar

def test_pedido_entra_como_solicitado_e_nao_como_confirmado(lead_qualificado, imovel_com_horario,
                                                            crm_api, token_crm):
    """O coração desta integração.

    `requested` e não `confirmed`, e a oportunidade NÃO vai para `visit_scheduled`. Se algum dia
    alguém "melhorar" isto para confirmar direto, o corretor passa a ver como certo um compromisso
    que ninguém assumiu.
    """
    codigo, imovel_id, slot_id, _ = imovel_com_horario
    assert pedir_visita(lead_qualificado, codigo, slot_id) is True

    with psycopg.connect(DSN_CRM, autocommit=True, row_factory=psycopg.rows.dict_row) as conn:
        visita = conn.execute("SELECT status, property_id FROM visits WHERE slot_id = %s",
                              (slot_id,)).fetchone()
        v = vinculo.buscar(lead_qualificado.id)
        op = conn.execute("SELECT stage FROM opportunities WHERE id = %s",
                          (v.crm_opportunity_id,)).fetchone()

    assert visita is not None, "o pedido não chegou ao CRM"
    assert visita["status"] == "requested"
    assert str(visita["property_id"]) == str(imovel_id)
    assert op["stage"] == "qualified", "quem move para visit_scheduled é o corretor, não o agente"


def test_pedido_qualifica_antes_quando_o_crm_ainda_nao_sabe(ligado, imovel_com_horario,
                                                            crm_api, token_crm):
    """O caso COMUM, e não uma borda.

    A Mora qualifica o lead no meio do turno e o agendador roda em seguida; o publicador só move o
    estágio no CRM no FIM do turno. Então, quando o cliente escolhe o horário, a oportunidade lá
    ainda está em `in_service` — e o CRM exige `qualified` para aceitar pedido de visita.

    Sem garantir o estágio antes de pedir, o primeiro pedido de todo lead seria recusado por uma
    questão de ordem e passaria a funcionar "sozinho" no turno seguinte: o tipo de intermitência
    que ninguém liga à causa. A primeira versão deste arquivo não cobria isto — a fixture já
    entregava a oportunidade qualificada, e a mutação mostrou que o passo podia ser removido sem
    nenhum teste reclamar.
    """
    from sdr_shared.crm import publicar_turno
    from sdr_shared.db import LeadRepository
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem

    codigo, _, slot_id, _ = imovel_com_horario
    lead = Lead(id=f"lead-tarde-{uuid.uuid4().hex[:8]}", nome="Qualificou Agora",
                estagio=Estagio.QUALIFICANDO, email=f"tarde-{uuid.uuid4().hex[:8]}@exemplo.com")
    lead.cartao.intencao = Intencao.ALUGUEL
    lead.cartao.regiao, lead.cartao.preco_max, lead.cartao.quartos = "São Paulo", 4000.0, 2
    lead = LeadRepository().upsert(lead)
    publicar_turno(lead, MensagemNormalizada(lead_id=lead.id, canal=Canal.WEB,
                                             tipo=TipoMensagem.TEXTO, identificador_canal="s",
                                             conteudo="oi"), texto_saida="olá")

    v = vinculo.buscar(lead.id)
    with psycopg.connect(DSN_CRM, autocommit=True, row_factory=psycopg.rows.dict_row) as conn:
        antes = conn.execute("SELECT stage FROM opportunities WHERE id = %s",
                             (v.crm_opportunity_id,)).fetchone()["stage"]
    assert antes == "in_service", "o cenário depende de a oportunidade ainda não estar qualificada"

    lead.estagio = Estagio.QUALIFICADO          # o que o grafo fez neste turno, ainda não publicado
    assert pedir_visita(lead, codigo, slot_id) is True

    with psycopg.connect(DSN_CRM, autocommit=True, row_factory=psycopg.rows.dict_row) as conn:
        visita = conn.execute("SELECT status FROM visits WHERE slot_id = %s",
                              (slot_id,)).fetchone()
        depois = conn.execute("SELECT stage FROM opportunities WHERE id = %s",
                              (v.crm_opportunity_id,)).fetchone()["stage"]
    assert visita is not None and visita["status"] == "requested"
    assert depois == "qualified", "qualificou para poder pedir, e parou aí"


def test_pedir_duas_vezes_nao_duplica(lead_qualificado, imovel_com_horario):
    """Reentrega do mesmo turno não pode virar dois pedidos na fila do corretor."""
    codigo, _, slot_id, _ = imovel_com_horario
    assert pedir_visita(lead_qualificado, codigo, slot_id) is True
    assert pedir_visita(lead_qualificado, codigo, slot_id) is True

    with psycopg.connect(DSN_CRM, autocommit=True, row_factory=psycopg.rows.dict_row) as conn:
        n = conn.execute("SELECT count(*) AS n FROM visits WHERE slot_id = %s",
                         (slot_id,)).fetchone()["n"]
    assert n == 1


def test_sem_slot_do_crm_nao_ha_pedido(lead_qualificado, imovel_com_horario):
    """Horário que veio da agenda do corretor não tem `slot_id` no CRM. A reserva da Mora vale; o
    pedido não tem onde ser pendurado, e inventar um slot seria pior."""
    codigo, _, _, _ = imovel_com_horario
    assert pedir_visita(lead_qualificado, codigo, None) is False


def test_lead_sem_vinculo_nao_pede(ligado, imovel_com_horario, novo_lead_simples):
    codigo, _, slot_id, _ = imovel_com_horario
    assert pedir_visita(novo_lead_simples, codigo, slot_id) is False


@pytest.fixture
def novo_lead_simples():
    from sdr_shared.db import LeadRepository
    lead = Lead(id=f"lead-sem-{uuid.uuid4().hex[:8]}", nome="Sem Vínculo", estagio=Estagio.NOVO)
    return LeadRepository().upsert(lead)
