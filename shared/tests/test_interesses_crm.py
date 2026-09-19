"""Quais imóveis o cliente viu, gostou e recusou — publicados no CRM.

É o que o corretor lê antes de ligar. O teste olha a linha que ele veria, e o encadeamento de
versão, que é onde esta operação difere das outras: publicar três imóveis são três escritas na
MESMA oportunidade, e a segunda já parte de uma versão que a primeira mudou.
"""
import os
import uuid

import psycopg
import psycopg.rows
import pytest

from sdr_shared.crm import publicar_interesses, vinculo
from sdr_shared.models import Estagio, Intencao, Lead

# Definido aqui e não importado do arquivo vizinho: a pasta de testes não é pacote, e um teste que
# depende de outro teste é acoplamento que só aparece quando alguém roda um dos dois sozinho.
DSN_CRM = os.environ.get("CRM_TEST_DSN", "postgresql://sdr:sdr@127.0.0.1:5432/crm_test")


@pytest.fixture
def imoveis_no_crm():
    """Três imóveis com código conhecido, como o acervo compartilhado teria."""
    codigos = [f"SP-I{uuid.uuid4().hex[:6].upper()}" for _ in range(3)]
    with psycopg.connect(DSN_CRM, autocommit=True, row_factory=psycopg.rows.dict_row) as conn:
        for codigo in codigos:
            conn.execute(
                """INSERT INTO properties (id, code, title, city, neighborhood, type, purpose,
                       base_price_cents, condo_monthly_cents, property_tax_monthly_cents,
                       other_monthly_cents, bedrooms, parking, status)
                   VALUES (%s,%s,%s,'São Paulo','Pinheiros','apartamento','rent',
                           300000, 50000, 10000, 0, 2, 1, 'available')""",
                (str(uuid.uuid4()), codigo, f"Apartamento {codigo} (endereço fictício)"))
    return codigos


@pytest.fixture
def lead_com_oportunidade(ligado):
    from sdr_shared.crm import publicar_turno
    from sdr_shared.db import LeadRepository
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem

    lead = Lead(id=f"lead-int-{uuid.uuid4().hex[:8]}", nome="Quem Viu Imóveis",
                estagio=Estagio.QUALIFICANDO, email=f"int-{uuid.uuid4().hex[:8]}@exemplo.com")
    lead.cartao.intencao = Intencao.ALUGUEL
    lead = LeadRepository().upsert(lead)
    publicar_turno(lead, MensagemNormalizada(lead_id=lead.id, canal=Canal.WEB,
                                             tipo=TipoMensagem.TEXTO, identificador_canal="s",
                                             conteudo="oi"), texto_saida="olá")
    assert vinculo.buscar(lead.id) is not None
    return lead


def _interesses(crm_opportunity_id):
    with psycopg.connect(DSN_CRM, autocommit=True, row_factory=psycopg.rows.dict_row) as conn:
        return {str(x["property_id"]): x["status"] for x in conn.execute(
            "SELECT property_id, status FROM property_interests WHERE opportunity_id = %s",
            (crm_opportunity_id,)).fetchall()}


def test_tres_imoveis_numa_tacada_encadeiam_a_versao(lead_com_oportunidade, imoveis_no_crm):
    """Cada registro incrementa a versão da oportunidade.

    Publicar os três com a MESMA versão faria o segundo e o terceiro baterem em 412 e sumirem em
    silêncio — o corretor veria um imóvel apresentado onde foram três, e ninguém teria motivo para
    desconfiar.
    """
    entraram = publicar_interesses(lead_com_oportunidade,
                                   [(c, "sugerido") for c in imoveis_no_crm])
    assert entraram == 3

    v = vinculo.buscar(lead_com_oportunidade.id)
    assert len(_interesses(v.crm_opportunity_id)) == 3
    assert set(_interesses(v.crm_opportunity_id).values()) == {"presented"}


def test_a_versao_guardada_acompanha(lead_com_oportunidade, imoveis_no_crm):
    """Se a versão do vínculo ficasse para trás, a PRÓXIMA escrita do publicador levaria um número
    velho — um 412 no turno seguinte, longe da causa."""
    antes = vinculo.buscar(lead_com_oportunidade.id).crm_version
    publicar_interesses(lead_com_oportunidade, [(c, "sugerido") for c in imoveis_no_crm])
    depois = vinculo.buscar(lead_com_oportunidade.id).crm_version
    assert depois > antes

    with psycopg.connect(DSN_CRM, autocommit=True, row_factory=psycopg.rows.dict_row) as conn:
        real = conn.execute("SELECT version FROM opportunities WHERE id = %s",
                            (vinculo.buscar(lead_com_oportunidade.id).crm_opportunity_id,)
                            ).fetchone()["version"]
    assert depois == real, "o vínculo tem de refletir a versão que o CRM realmente tem"


def test_descarte_do_corretor_chega_como_recusado(lead_com_oportunidade, imoveis_no_crm):
    """Descarte é ato explícito, e é a informação mais útil da lista: é o que impede o corretor de
    reoferecer o que a pessoa já recusou."""
    publicar_interesses(lead_com_oportunidade, [(imoveis_no_crm[0], "sugerido")])
    publicar_interesses(lead_com_oportunidade, [(imoveis_no_crm[0], "descartado")])

    v = vinculo.buscar(lead_com_oportunidade.id)
    assert set(_interesses(v.crm_opportunity_id).values()) == {"rejected"}


def test_pedido_de_visita_vira_interesse_forte(lead_com_oportunidade, imoveis_no_crm):
    publicar_interesses(lead_com_oportunidade, [(imoveis_no_crm[0], "visita_marcada")])
    v = vinculo.buscar(lead_com_oportunidade.id)
    assert set(_interesses(v.crm_opportunity_id).values()) == {"interested"}


def test_imovel_que_o_crm_nao_conhece_nao_para_os_outros(lead_com_oportunidade, imoveis_no_crm):
    """Enquanto os dois acervos não estiverem perfeitamente sincronizados, um código órfão é
    possível. Ele não pode levar junto os imóveis que existem."""
    entraram = publicar_interesses(
        lead_com_oportunidade,
        [("SP-NAO-EXISTE", "sugerido"), (imoveis_no_crm[0], "sugerido")])
    assert entraram == 1
    v = vinculo.buscar(lead_com_oportunidade.id)
    assert len(_interesses(v.crm_opportunity_id)) == 1


def test_lead_sem_vinculo_nao_publica(ligado, imoveis_no_crm):
    from sdr_shared.db import LeadRepository
    lead = LeadRepository().upsert(Lead(id=f"lead-sv-{uuid.uuid4().hex[:8]}", nome="Sem Vínculo",
                                        estagio=Estagio.NOVO))
    assert publicar_interesses(lead, [(imoveis_no_crm[0], "sugerido")]) == 0


def test_sem_crm_e_no_op(imoveis_no_crm, monkeypatch):
    from sdr_shared.db import LeadRepository
    monkeypatch.delenv("SDR_CRM_URL", raising=False)
    monkeypatch.delenv("SDR_CRM_TOKEN", raising=False)
    lead = LeadRepository().upsert(Lead(id=f"lead-nc-{uuid.uuid4().hex[:8]}", nome="Sem CRM",
                                        estagio=Estagio.NOVO))
    assert publicar_interesses(lead, [(imoveis_no_crm[0], "sugerido")]) == 0
