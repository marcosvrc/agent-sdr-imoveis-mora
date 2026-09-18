"""A ponte Mora → CRM, contra um CRM DE VERDADE.

Sobe a API do CRM num processo e publica nela um lead da Mora, como o agente faz no fim de cada
turno. Um dublê do cliente HTTP provaria que o código chama o que eu mandei chamar; o que precisa
ser provado é outra coisa — que a tradução entre os dois vocabulários está certa e que as regras do
CRM (versão, idempotência, limite do agente) são respeitadas de fato.

Roda só quando há Postgres: `SDR_DATABASE_DSN` e `CRM_TEST_DSN` apontando para bancos de teste.
"""
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest

RAIZ = Path(__file__).resolve().parents[2]
CRM = RAIZ / "services" / "crm"

DSN_MORA = os.environ.get("SDR_DATABASE_DSN", "")
DSN_CRM = os.environ.get("CRM_TEST_DSN", "postgresql://sdr:sdr@127.0.0.1:5432/crm_test")

pytestmark = pytest.mark.skipif(
    not DSN_MORA or "test" not in DSN_MORA.rsplit("/", 1)[-1],
    reason="exige SDR_DATABASE_DSN apontando para um banco de teste")


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def crm_api():
    """A API do CRM, de verdade, num processo separado."""
    porta = _porta_livre()
    env = {**os.environ, "CRM_DATABASE_DSN": DSN_CRM, "CRM_APP_ENV": "test",
           "PYTHONPATH": str(CRM)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "sdr_crm.api.main:app", "--port", str(porta),
         "--host", "127.0.0.1", "--log-level", "warning"],
        cwd=CRM, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{porta}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/health/ready", timeout=1).status_code == 200:
                break
        except Exception:
            time.sleep(0.15)
    else:
        proc.kill()
        pytest.skip("a API do CRM não subiu")
    yield base
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture
def token_crm():
    sys.path.insert(0, str(CRM))
    import psycopg
    from sdr_crm.api import auth as autenticacao
    bruto, hash_ = autenticacao.novo_token("mora")
    with psycopg.connect(DSN_CRM, autocommit=True) as conn:
        conn.execute("INSERT INTO service_credentials (name, token_hash, scopes) VALUES (%s,%s,%s)",
                     ("mora", hash_,
                      ["crm:read", "leads:write", "opportunities:write", "interactions:write",
                       "visits:request", "tasks:write", "handoffs:write"]))
    return bruto


@pytest.fixture
def ligado(crm_api, token_crm, monkeypatch):
    monkeypatch.setenv("SDR_CRM_URL", crm_api)
    monkeypatch.setenv("SDR_CRM_TOKEN", token_crm)
    return crm_api


@pytest.fixture
def lead():
    from sdr_shared.db import LeadRepository
    from sdr_shared.models import Estagio, Intencao, Lead
    lead = Lead(id=f"lead-crm-{uuid.uuid4().hex[:8]}", nome="Cliente da Ponte",
                estagio=Estagio.QUALIFICANDO)
    lead.cartao.intencao = Intencao.ALUGUEL
    lead.cartao.regiao = "São Paulo"
    lead.cartao.bairros = ["Brooklin"]
    lead.cartao.preco_max = 4000.0
    lead.cartao.quartos = 2
    lead.cartao.urgencia = "3 meses"
    return LeadRepository().upsert(lead)


def _consultar(base, token, rota, **params):
    r = httpx.get(f"{base}{rota}", params=params or None, timeout=10,
                  headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- tradução

def test_traducao_do_cartao_para_preferencias():
    """Sem rede: a tradução é onde os dois vocabulários se encontram, e onde um engano silencioso
    viraria uma busca errada para o cliente."""
    from sdr_shared.crm import traducao
    from sdr_shared.models import Intencao, Lead

    lead = Lead(id="x", nome="Y")
    lead.cartao.intencao = Intencao.ALUGUEL
    lead.cartao.preco_max = 3000.0
    p = traducao.preferencias(lead)
    assert p["budget_max_cents"] == 300_000            # reais → centavos
    assert p["budget_basis"] == "monthly_total"        # aluguel fala em custo total

    lead.cartao.intencao = Intencao.COMPRA
    lead.cartao.preco_max = 650_000.0
    assert traducao.preferencias(lead)["budget_basis"] == "base_price"


def test_investidor_usa_o_ticket_como_teto():
    """Sem isto, a oportunidade do investidor ficaria eternamente sem teto — e nunca poderia ser
    qualificada, apesar de ele ter dito exatamente quanto pretende investir."""
    from sdr_shared.crm import traducao
    from sdr_shared.models import Intencao, Lead
    lead = Lead(id="x")
    lead.cartao.intencao = Intencao.INVESTIMENTO
    lead.cartao.ticket = 900_000.0
    p = traducao.preferencias(lead)
    assert p["budget_max_cents"] == 90_000_000
    assert traducao.proposito(lead) == "buy"           # investimento é compra


def test_intencao_indefinida_nao_vira_oportunidade():
    from sdr_shared.crm import traducao
    from sdr_shared.models import Lead
    assert traducao.proposito(Lead(id="x")) is None


def test_agendado_nao_vira_visit_scheduled():
    """O CRM só aceita `visit_scheduled` com visita confirmada por uma pessoa. O agente não
    confirma visita — então o estágio para em `qualified` e avança lá quando o corretor confirmar."""
    from sdr_shared.crm import traducao
    from sdr_shared.models import Estagio
    assert traducao.ESTAGIO[Estagio.AGENDADO] == "qualified"
    assert "visit_scheduled" not in traducao.ESTAGIO.values()


# --------------------------------------------------------------------------- publicação

def test_turno_cria_cliente_oportunidade_preferencias_e_historico(ligado, token_crm, lead):
    from sdr_shared.crm import publicar_turno, vinculo
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem

    entrada = MensagemNormalizada(lead_id=lead.id, canal=Canal.WEB, tipo=TipoMensagem.TEXTO,
                                  identificador_canal="sessao-1",
                                  conteudo="Quero alugar 2 quartos no Brooklin até 4 mil.")
    publicar_turno(lead, entrada, texto_saida="Achei três opções no Brooklin.")

    v = vinculo.buscar(lead.id)
    assert v is not None, "o vínculo com o CRM não foi gravado"

    op = _consultar(ligado, token_crm, f"/v1/opportunities/{v.crm_opportunity_id}")["data"]
    assert op["purpose"] == "rent"
    assert op["stage"] == "in_service"                  # `qualificando` da Mora
    assert op["preferences"]["city"] == "São Paulo"
    assert op["preferences"]["budget_max_cents"] == 400_000
    assert op["preferences"]["neighborhoods"] == ["Brooklin"]

    historico = _consultar(ligado, token_crm, f"/v1/leads/{v.crm_lead_id}/interactions")["items"]
    assert {x["direction"] for x in historico} == {"inbound", "outbound"}

    # O lead no CRM tem o identificador externo que aponta de volta para a Mora.
    cliente = _consultar(ligado, token_crm, f"/v1/leads/{v.crm_lead_id}")["data"]
    assert cliente["external_contact_id"] == f"mora-{lead.id}"
    assert cliente["source"] == "mora_agent"


def test_republicar_o_mesmo_turno_nao_duplica_nada(ligado, token_crm, lead):
    from sdr_shared.crm import publicar_turno, vinculo
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem

    entrada = MensagemNormalizada(lead_id=lead.id, canal=Canal.WEB, tipo=TipoMensagem.TEXTO,
                                  identificador_canal="s", conteudo="Mesma mensagem de sempre.")
    publicar_turno(lead, entrada, texto_saida="Mesma resposta.")
    publicar_turno(lead, entrada, texto_saida="Mesma resposta.")

    v = vinculo.buscar(lead.id)
    historico = _consultar(ligado, token_crm, f"/v1/leads/{v.crm_lead_id}/interactions")["items"]
    assert len(historico) == 2              # uma de entrada, uma de saída — não quatro

    leads = _consultar(ligado, token_crm, "/v1/leads",
                       external_contact_id=f"mora-{lead.id}")["items"]
    assert len(leads) == 1


def test_qualificacao_avanca_passo_a_passo_no_crm(ligado, token_crm, lead):
    """A Mora salta de `novo` para `qualificado` num turno quando o cliente diz tudo de uma vez; o
    CRM não aceita salto. O publicador percorre o caminho."""
    from sdr_shared.crm import publicar_turno, vinculo
    from sdr_shared.db import LeadRepository
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
    from sdr_shared.models import Estagio

    lead.estagio = Estagio.QUALIFICADO
    lead = LeadRepository().upsert(lead)
    entrada = MensagemNormalizada(lead_id=lead.id, canal=Canal.WEB, tipo=TipoMensagem.TEXTO,
                                  identificador_canal="s", conteudo="Tudo isso de uma vez.")
    publicar_turno(lead, entrada, estagio_antes=Estagio.NOVO)

    v = vinculo.buscar(lead.id)
    op = _consultar(ligado, token_crm, f"/v1/opportunities/{v.crm_opportunity_id}")["data"]
    assert op["stage"] == "qualified"


def test_encaminhamento_passa_o_atendimento_para_humano(ligado, token_crm, lead):
    from sdr_shared.crm import publicar_turno, vinculo
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
    from sdr_shared.models import Estagio

    entrada = MensagemNormalizada(lead_id=lead.id, canal=Canal.WEB, tipo=TipoMensagem.TEXTO,
                                  identificador_canal="s", conteudo="Quero falar com uma pessoa.")
    publicar_turno(lead, entrada)                       # abre o vínculo

    lead.estagio = Estagio.HANDOFF
    publicar_turno(lead, entrada, texto_saida="Vou passar para um corretor.",
                   estagio_antes=Estagio.QUALIFICANDO)

    v = vinculo.buscar(lead.id)
    op = _consultar(ligado, token_crm, f"/v1/opportunities/{v.crm_opportunity_id}")["data"]
    assert op["atendimento"] == "human_pending"
    assert op["handoffs"] and op["handoffs"][0]["status"] == "pending"
    # O resumo não pode ser vazio: é o que o corretor lê antes de ligar.
    assert len(op["handoffs"][0]["summary"]) > 10


def test_intencao_indefinida_nao_abre_nada_no_crm(ligado, token_crm):
    from sdr_shared.crm import publicar_turno, vinculo
    from sdr_shared.db import LeadRepository
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
    from sdr_shared.models import Lead

    lead = LeadRepository().upsert(Lead(id=f"lead-vago-{uuid.uuid4().hex[:8]}", nome="Só um oi"))
    entrada = MensagemNormalizada(lead_id=lead.id, canal=Canal.WEB, tipo=TipoMensagem.TEXTO,
                                  identificador_canal="s", conteudo="Oi")
    publicar_turno(lead, entrada, texto_saida="Olá! Você procura para alugar ou comprar?")

    assert vinculo.buscar(lead.id) is None
    encontrados = _consultar(ligado, token_crm, "/v1/leads",
                             external_contact_id=f"mora-{lead.id}")["items"]
    assert encontrados == []


def test_crm_fora_do_ar_nao_derruba_o_turno(lead, monkeypatch):
    """O compromisso mais importante do módulo: um CRM indisponível não pode virar um atendimento
    indisponível. A porta está fechada de propósito — nada escuta ali."""
    from sdr_shared.crm import publicar_turno
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem

    monkeypatch.setenv("SDR_CRM_URL", f"http://127.0.0.1:{_porta_livre()}")
    monkeypatch.setenv("SDR_CRM_TOKEN", "irrelevante")
    entrada = MensagemNormalizada(lead_id=lead.id, canal=Canal.WEB, tipo=TipoMensagem.TEXTO,
                                  identificador_canal="s", conteudo="oi")
    publicar_turno(lead, entrada, texto_saida="olá")    # não pode levantar


def test_sem_configuracao_e_no_op(lead, monkeypatch):
    """Sem `SDR_CRM_URL`, a Mora continua exatamente como era — é o que mantém o compose de sempre
    funcionando sem subir mais um serviço."""
    from sdr_shared.crm import habilitado, publicar_turno
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem

    monkeypatch.delenv("SDR_CRM_URL", raising=False)
    monkeypatch.delenv("SDR_CRM_TOKEN", raising=False)
    assert habilitado() is False
    entrada = MensagemNormalizada(lead_id=lead.id, canal=Canal.WEB, tipo=TipoMensagem.TEXTO,
                                  identificador_canal="s", conteudo="oi")
    publicar_turno(lead, entrada)


def test_mesma_frase_de_dois_clientes_nao_colide_no_historico(ligado, token_crm):
    """O defeito que a segunda execução da suíte revelou.

    O `external_event_id` saía de um hash do TEXTO, e o índice único do CRM é por canal — então
    "Oi, tudo bem?" de dois clientes diferentes colidia, e a mensagem do segundo entrava (ou
    melhor, não entrava) no histórico do primeiro.
    """
    from sdr_shared.crm import publicar_turno, vinculo
    from sdr_shared.db import LeadRepository
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
    from sdr_shared.models import Estagio, Intencao, Lead

    frase = "Oi, tudo bem? Quero alugar."
    vinculos = []
    for _ in range(2):
        lead = Lead(id=f"lead-col-{uuid.uuid4().hex[:8]}", nome="Homônimo",
                    estagio=Estagio.QUALIFICANDO)
        lead.cartao.intencao = Intencao.ALUGUEL
        lead.cartao.regiao = "São Paulo"
        lead = LeadRepository().upsert(lead)
        entrada = MensagemNormalizada(lead_id=lead.id, canal=Canal.WEB, tipo=TipoMensagem.TEXTO,
                                      identificador_canal="s", conteudo=frase)
        publicar_turno(lead, entrada)
        vinculos.append(vinculo.buscar(lead.id))

    for v in vinculos:
        historico = _consultar(ligado, token_crm, f"/v1/leads/{v.crm_lead_id}/interactions")["items"]
        assert len(historico) == 1, "a mensagem de um cliente sumiu no histórico do outro"
        assert historico[0]["summary"] == frase


def test_url_sem_token_conta_como_desligado(monkeypatch):
    """No compose a URL tem padrão. Sem token, cada turno viraria um 401 no log de quem nunca pediu
    a integração — então "configurado" é ter os dois."""
    from sdr_shared.crm import habilitado
    monkeypatch.setenv("SDR_CRM_URL", "http://crm-api:8100")
    monkeypatch.delenv("SDR_CRM_TOKEN", raising=False)
    assert habilitado() is False
