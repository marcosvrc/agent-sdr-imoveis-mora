"""Reconhecer no CRM um cliente que já existe.

É a parte da integração que muda o ATENDIMENTO e não só o registro, então o que se prova aqui é
comportamento: a Mora chega sabendo o que o corretor já anotou, e não pergunta de novo.

Contra o CRM de verdade, atrás do MCP. Um dublê provaria que eu chamo o que eu mesmo mandei
chamar — inútil para uma integração cujo risco é justamente o encontro dos dois vocabulários.
"""
import uuid

import httpx
import pytest

from sdr_shared.crm import reconhecer, vinculo
from sdr_shared.models import Estagio, Intencao, Lead


def _criar_no_crm(base: str, token: str, *, email: str, prefs: dict, purpose: str = "rent",
                  estagio: str | None = "in_service") -> str:
    """Cria cliente e oportunidade no CRM como um corretor faria pelo painel."""
    cab = {"Authorization": f"Bearer {token}"}

    def post(rota, corpo, op):
        r = httpx.post(f"{base}{rota}", json=corpo, timeout=10,
                       headers={**cab, "Idempotency-Key": op})
        assert r.status_code in (200, 201), r.text
        return r.json()["data"]

    lead = post("/v1/leads", {"name": "Cliente Antigo", "source": "corretor", "email": email},
                f"op-lead-{uuid.uuid4().hex}")
    op = post("/v1/opportunities", {"lead_id": lead["id"], "purpose": purpose},
              f"op-opo-{uuid.uuid4().hex}")

    # `monthly_total` só existe em aluguel, e o CRM recusa a combinação errada com 409 — regra dele,
    # não detalhe do teste.
    prefs = {**prefs, "budget_basis": "monthly_total" if purpose == "rent" else "base_price"}
    r = httpx.put(f"{base}/v1/opportunities/{op['id']}/preferences", json=prefs, timeout=10,
                  headers={**cab, "If-Match": f'W/"{op["version"]}"',
                           "Idempotency-Key": f"op-pref-{uuid.uuid4().hex}"})
    assert r.status_code == 200, r.text
    versao = r.json()["data"]["opportunity_version"]

    if estagio:
        r = httpx.post(f"{base}/v1/opportunities/{op['id']}/transitions",
                       json={"target_stage": estagio, "reason": None}, timeout=10,
                       headers={**cab, "If-Match": f'W/"{versao}"',
                                "Idempotency-Key": f"op-tr-{uuid.uuid4().hex}"})
        assert r.status_code in (200, 201), r.text
    return op["id"]


@pytest.fixture
def novo_lead():
    def montar(**campos) -> Lead:
        from sdr_shared.db import LeadRepository
        lead = Lead(id=f"lead-rec-{uuid.uuid4().hex[:8]}", nome="Quem Voltou",
                    estagio=Estagio.NOVO, **campos)
        return LeadRepository().upsert(lead)
    return montar


PREFS = {"city": "São Paulo", "neighborhoods": ["Pinheiros"], "property_types": ["apartamento"],
         "budget_min_cents": None, "budget_max_cents": 350_000, "budget_basis": "monthly_total",
         "bedrooms_min": 2, "parking_min": None, "requirements": []}


# --------------------------------------------------------------------------- o caso que importa

def test_cliente_conhecido_chega_com_o_cartao_semeado(ligado, crm_api, token_crm, novo_lead):
    """O corretor já anotou cidade, bairro, orçamento e quartos. A Mora não pode perguntar de novo.

    R$ 3.500 é o teto anotado em centavos (350000) — a conversão de volta é onde um fator de cem
    passa despercebido e o cliente recebe imóveis cem vezes fora do orçamento dele.
    """
    email = f"antigo-{uuid.uuid4().hex[:8]}@exemplo.com"
    _criar_no_crm(crm_api, token_crm, email=email, prefs=PREFS)
    lead = novo_lead(email=email)

    assert reconhecer(lead) is True
    assert lead.cartao.intencao == Intencao.ALUGUEL
    assert lead.cartao.regiao == "São Paulo"
    assert lead.cartao.bairros == ["Pinheiros"]
    assert lead.cartao.preco_max == 3500.0
    assert lead.cartao.quartos == 2
    assert lead.cartao.tipo_imovel == "apartamento"

    v = vinculo.buscar(lead.id)
    assert v is not None, "reconhecer sem vincular publicaria o turno numa ficha nova"


def test_o_que_o_cliente_diz_agora_vence_o_registro(ligado, crm_api, token_crm, novo_lead):
    """O CRM diz aluguel em Pinheiros até 3.500; o cliente acabou de dizer que quer comprar.

    Sobrescrever seria pior que não reconhecer: a Mora conduziria a conversa inteira pela intenção
    velha, com o cliente repetindo que mudou de ideia.
    """
    email = f"mudou-{uuid.uuid4().hex[:8]}@exemplo.com"
    _criar_no_crm(crm_api, token_crm, email=email, prefs=PREFS)
    lead = novo_lead(email=email)
    lead.cartao.intencao = Intencao.COMPRA
    lead.cartao.preco_max = 900_000.0

    reconhecer(lead)
    assert lead.cartao.intencao == Intencao.COMPRA
    assert lead.cartao.preco_max == 900_000.0
    assert lead.cartao.regiao == "São Paulo", "o que estava vazio ainda é aproveitado"


def test_investimento_nao_e_rebaixado_a_compra(ligado, crm_api, token_crm, novo_lead):
    """A tradução de ida junta investimento e compra em `buy`, então a volta é ambígua por
    construção. A regra de só preencher campo vazio é o que contém a perda — e este teste é o que
    impede alguém de "melhorar" essa regra mais tarde sem perceber o efeito."""
    email = f"investidor-{uuid.uuid4().hex[:8]}@exemplo.com"
    _criar_no_crm(crm_api, token_crm, email=email, prefs=PREFS, purpose="buy")
    lead = novo_lead(email=email)
    lead.cartao.intencao = Intencao.INVESTIMENTO

    reconhecer(lead)
    assert lead.cartao.intencao == Intencao.INVESTIMENTO


# --------------------------------------------------------------------------- o que NÃO reconhecer

def test_cliente_desconhecido_nao_e_procurado_duas_vezes(ligado, novo_lead):
    """Sem a marca, um cliente que o CRM não conhece custaria uma busca por turno, para sempre."""
    lead = novo_lead(email=f"nunca-visto-{uuid.uuid4().hex[:8]}@exemplo.com")
    assert reconhecer(lead) is False

    from sdr_shared.crm import reconhecimento
    assert reconhecimento._ja_procurado(lead.id, reconhecimento._marca(lead)) is True


def test_contato_novo_merece_nova_procura(ligado, crm_api, token_crm, novo_lead):
    """O chat do site é anônimo: o e-mail só aparece no meio da conversa. Se a primeira procura (sem
    contato nenhum) valesse para sempre, o cliente nunca seria reconhecido."""
    email = f"tardio-{uuid.uuid4().hex[:8]}@exemplo.com"
    _criar_no_crm(crm_api, token_crm, email=email, prefs=PREFS)

    lead = novo_lead()
    assert reconhecer(lead) is False        # anônimo: não há por onde procurar

    lead.cartao.email_informado = email     # agora ele se identificou
    assert reconhecer(lead) is True
    assert lead.cartao.regiao == "São Paulo"


# A ambiguidade de contato (dois cadastros, mesmo telefone) NÃO é testável aqui: este CRM
# deduplica por e-mail e por telefone, na API e por índice único no banco, então a situação não
# pode ser montada. Houve um teste neste lugar que dizia prová-la e passava por outro motivo — o
# cliente encontrado simplesmente não tinha oportunidade aberta. A mutação mostrou. A regra é do
# adaptador e está provada lá, em `test_porta_crm.py`, com a resposta que um CRM que PERMITA
# duplicata devolveria.


def test_oportunidade_fechada_nao_vira_contexto(ligado, crm_api, token_crm, novo_lead):
    """Preferências de um negócio ganho ou perdido conduziriam a conversa nova pela intenção velha."""
    email = f"fechado-{uuid.uuid4().hex[:8]}@exemplo.com"
    op_id = _criar_no_crm(crm_api, token_crm, email=email, prefs=PREFS, estagio="in_service")

    # O fechamento é escrito direto no banco do CRM porque marcar `lost` é ação HUMANA e a
    # credencial de serviço é recusada — com razão, e isso já tem teste próprio lá. Aqui o
    # fechamento é o cenário, não o comportamento sob prova.
    import os

    import psycopg
    with psycopg.connect(os.environ["CRM_TEST_DSN"], autocommit=True) as conn:
        # `closed_at` junto: o schema do CRM exige coerência entre estágio final e fechamento, e
        # burlar isso deixaria a linha num estado que a aplicação nunca produz.
        conn.execute("UPDATE opportunities SET stage = 'lost', lost_reason = 'cenário de teste', "
                     "closed_at = now() WHERE id = %s", (op_id,))

    lead = novo_lead(email=email)
    assert reconhecer(lead) is False
    assert lead.cartao.regiao is None


def test_sem_crm_configurado_nao_faz_nada(novo_lead, monkeypatch):
    monkeypatch.delenv("SDR_CRM_URL", raising=False)
    monkeypatch.delenv("SDR_CRM_TOKEN", raising=False)
    lead = novo_lead(email="qualquer@exemplo.com")
    assert reconhecer(lead) is False
