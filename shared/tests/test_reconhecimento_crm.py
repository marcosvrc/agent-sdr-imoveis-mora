"""Reconhecer no CRM um cliente que já existe.

É a parte da integração que muda o ATENDIMENTO e não só o registro, então o que se prova aqui é
comportamento: a Mora chega sabendo o que o corretor já anotou, e não pergunta de novo.

MUDOU (S4): contato AUTODECLARADO no chat não reconhece mais. Um visitante anônimo que digitava o
telefone ou o e-mail de um cliente existente herdava o orçamento e os bairros dele e passava a
escrever na ficha dele. Hoje nenhum canal entrega contato verificado, então o caminho normal é o
autodeclarado: o lead segue como novo e a coincidência fica sinalizada para o corretor. A semeadura
continua existindo para contato verificado pelo canal (`contato_verificado=True`), e os testes que a
provam passaram a dizer isso explicitamente.

Contra o CRM de verdade, atrás do MCP. Um dublê provaria que eu chamo o que eu mesmo mandei
chamar — inútil para uma integração cujo risco é justamente o encontro dos dois vocabulários.
"""
import os
import uuid

import httpx
import pytest

from sdr_shared.crm import reconhecer, vinculo
from sdr_shared.models import Estagio, Intencao, Lead

# Com padrão, e não `os.environ[...]`: o teste passava a depender de a variável estar exportada, e
# falhava com KeyError — que não diz que o problema é ambiente, e não código.
DSN_CRM = os.environ.get("CRM_TEST_DSN", "postgresql://sdr:sdr@127.0.0.1:5432/crm_test")


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

    assert reconhecer(lead, contato_verificado=True) is True
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

    reconhecer(lead, contato_verificado=True)
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

    reconhecer(lead, contato_verificado=True)
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
    contato nenhum) valesse para sempre, a coincidência com um cliente do CRM nunca seria vista.

    Antes este teste afirmava que o cartão era semeado ao aparecer o e-mail. Contato digitado no
    chat não prova identidade (S4): agora a procura acontece, a coincidência é anotada e sinalizada,
    e o cartão NÃO herda nada."""
    email = f"tardio-{uuid.uuid4().hex[:8]}@exemplo.com"
    _criar_no_crm(crm_api, token_crm, email=email, prefs=PREFS)

    lead = novo_lead()
    assert reconhecer(lead) is False        # anônimo: não há por onde procurar

    lead.cartao.email_informado = email     # agora ele disse um e-mail
    assert reconhecer(lead) is False
    assert lead.cartao.regiao is None
    from sdr_shared.crm import reconhecimento
    assert reconhecimento._ja_procurado(lead.id, reconhecimento._marca(lead)) is True


# --------------------------------------------------------------------------- S4: contato de outra pessoa

def _sinalizacoes(lead_id: str) -> list[dict]:
    from sdr_shared.db import AuditoriaRepository
    return AuditoriaRepository().listar(acao="cliente.contato_coincide", entidade_id=lead_id)


def test_visitante_com_contato_de_cliente_nao_herda_a_ficha_dele(ligado, crm_api, token_crm, novo_lead):
    """O ataque: abrir o chat anônimo e digitar o e-mail (ou telefone) de um cliente do CRM. Antes,
    o visitante herdava orçamento e bairros da vítima — e a Mora os repetia para ele — e tudo o que
    ele escrevesse entrava no histórico da ficha dela."""
    from sdr_shared.crm import publicar_turno
    from sdr_shared.messaging import Canal, MensagemNormalizada
    cab = {"Authorization": f"Bearer {token_crm}"}
    email = f"vitima-{uuid.uuid4().hex[:8]}@exemplo.com"
    op_vitima = _criar_no_crm(crm_api, token_crm, email=email, prefs=PREFS)
    vitima = httpx.get(f"{crm_api}/v1/opportunities/{op_vitima}", headers=cab, timeout=10).json()["data"]["lead_id"]

    lead = novo_lead()
    lead.cartao.email_informado = email
    assert reconhecer(lead) is False
    assert lead.cartao.bairros == [] and lead.cartao.preco_max is None, "nada herdado da vítima"
    assert vinculo.buscar(lead.id) is None, "não pode ser vinculado à oportunidade dela"
    assert len(_sinalizacoes(lead.id)) == 1, "o corretor precisa ver a coincidência"
    reconhecer(lead)                        # mesmo contato: não procura nem sinaliza de novo
    assert len(_sinalizacoes(lead.id)) == 1

    # O turno seguinte, com intenção clara, abre o lead no CRM: tem de ser uma ficha NOVA.
    lead.cartao.intencao = Intencao.ALUGUEL
    entrada = MensagemNormalizada(lead_id=lead.id, canal=Canal.WEB, identificador_canal="s-vit",
                                  conteudo="quero alugar em Pinheiros")
    publicar_turno(lead, entrada, texto_saida="Certo!")
    v = vinculo.buscar(lead.id)
    assert v is not None and v.crm_lead_id != str(vitima) and v.crm_opportunity_id != str(op_vitima)

    da_vitima = httpx.get(f"{crm_api}/v1/leads/{vitima}/interactions", headers=cab, timeout=10).json()["items"]
    assert not any("Pinheiros" in (x.get("summary") or "") for x in da_vitima)
    do_novo = httpx.get(f"{crm_api}/v1/leads/{v.crm_lead_id}/interactions", headers=cab, timeout=10).json()["items"]
    assert any(x["direction"] == "internal" and "coincide" in x["summary"] for x in do_novo), \
        "a ficha nova leva a observação para o corretor revisar"


def test_contato_coincidente_dito_antes_da_procura_tambem_abre_ficha_nova(ligado, crm_api, token_crm, novo_lead):
    """O contato pode aparecer no MESMO turno em que a intenção fica clara: a publicação roda antes
    de qualquer procura, e o CRM deduplica por e-mail — devolveria a ficha da vítima."""
    from sdr_shared.crm import publicar_turno
    from sdr_shared.messaging import Canal, MensagemNormalizada
    email = f"vitima2-{uuid.uuid4().hex[:8]}@exemplo.com"
    op_vitima = _criar_no_crm(crm_api, token_crm, email=email, prefs=PREFS)
    lead = novo_lead()
    lead.cartao.email_informado = email
    lead.cartao.intencao = Intencao.ALUGUEL
    entrada = MensagemNormalizada(lead_id=lead.id, canal=Canal.WEB, identificador_canal="s-vit2",
                                  conteudo=f"quero alugar, meu e-mail é {email}")
    publicar_turno(lead, entrada, texto_saida="Anotado!")
    v = vinculo.buscar(lead.id)
    assert v is not None and v.crm_opportunity_id != str(op_vitima)
    assert len(_sinalizacoes(lead.id)) == 1


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
    import psycopg
    with psycopg.connect(DSN_CRM, autocommit=True) as conn:
        # `closed_at` junto: o schema do CRM exige coerência entre estágio final e fechamento, e
        # burlar isso deixaria a linha num estado que a aplicação nunca produz.
        conn.execute("UPDATE opportunities SET stage = 'lost', lost_reason = 'cenário de teste', "
                     "closed_at = now() WHERE id = %s", (op_id,))

    lead = novo_lead(email=email)
    assert reconhecer(lead, contato_verificado=True) is False
    assert lead.cartao.regiao is None


def test_sem_crm_configurado_nao_faz_nada(novo_lead, monkeypatch):
    monkeypatch.delenv("SDR_CRM_URL", raising=False)
    monkeypatch.delenv("SDR_CRM_TOKEN", raising=False)
    lead = novo_lead(email="qualquer@exemplo.com")
    assert reconhecer(lead) is False
