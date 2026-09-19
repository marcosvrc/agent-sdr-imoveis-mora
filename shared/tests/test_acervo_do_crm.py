"""O acervo que a Mora indexa, vindo do CRM.

A razão de existir desta ligação cabe numa frase: **o agente não pode oferecer o que já foi
vendido.** Quem muda o preço de um imóvel ou o marca como vendido é o corretor, no sistema dele, e
um índice que não acompanha isso transforma cada conversa numa promessa que a imobiliária não pode
cumprir.

O que se testa aqui é a junção — registro comercial do CRM com dados de vitrine do arquivo — e a
purga, que é a parte destrutiva e por isso a que precisa das guardas mais firmes.
"""
import json
import os
import sys
import uuid
from pathlib import Path

import psycopg
import psycopg.rows
import pytest

DSN_CRM = os.environ.get("CRM_TEST_DSN", "postgresql://sdr:sdr@127.0.0.1:5432/crm_test")
RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "services" / "ingestion"))


@pytest.fixture
def acervo_no_crm():
    """Três disponíveis e um vendido, com códigos próprios."""
    codigos = [f"SP-A{uuid.uuid4().hex[:6].upper()}" for _ in range(4)]
    with psycopg.connect(DSN_CRM, autocommit=True, row_factory=psycopg.rows.dict_row) as conn:
        conn.execute("DELETE FROM properties WHERE code LIKE 'SP-A%'")
        for i, codigo in enumerate(codigos):
            conn.execute(
                """INSERT INTO properties (id, code, title, description, city, neighborhood, type,
                       purpose, base_price_cents, condo_monthly_cents,
                       property_tax_monthly_cents, other_monthly_cents, bedrooms, parking,
                       area_m2, status)
                   VALUES (%s,%s,%s,%s,'São Paulo','Pinheiros','apartamento','rent',
                           350000, 60000, 10000, 0, 2, 1, 70, %s)""",
                (str(uuid.uuid4()), codigo, f"Apartamento {codigo}", "Perto do metrô.",
                 "available" if i < 3 else "unavailable"))
    yield codigos
    with psycopg.connect(DSN_CRM, autocommit=True) as conn:
        conn.execute("DELETE FROM properties WHERE code LIKE 'SP-A%'")


@pytest.fixture
def arquivo_de_vitrine(tmp_path, acervo_no_crm):
    """O arquivo traz fotos e região só do PRIMEIRO — os outros ficam órfãos de propósito."""
    caminho = tmp_path / "imoveis.json"
    caminho.write_text(json.dumps([{
        "id": acervo_no_crm[0], "tipo": "apartamento", "operacao": "aluguel",
        "cidade": "São Paulo", "regiao": "zona_oeste", "bairro": "Pinheiros", "quartos": 2,
        "suites": 1, "vagas": 1, "area_m2": 70, "preco": 3500.0, "condominio": 600.0,
        "descricao": "Descrição da vitrine.", "fotos": ["/fotos/a.jpg", "/fotos/b.jpg"],
        "destaque_investimento": True}], ensure_ascii=False), encoding="utf-8")
    return str(caminho)


# --------------------------------------------------------------------------- a junção

def test_vendido_fica_fora_do_indice(ligado, acervo_no_crm, arquivo_de_vitrine):
    """A razão de existir da ligação inteira.

    A garantia é do CRM, não deste código: `GET /v1/properties` filtra por `available` por padrão.
    Houve um filtro repetido do lado da Mora, e a mutação mostrou que ele nunca excluía nada —
    saiu. Este teste continua valendo, e talvez valha mais: prova o RESULTADO que o cliente vê,
    independentemente de qual camada o garante. Se um dia o padrão da rota mudar, é aqui que
    aparece.
    """
    from sdr_ingestion.acervo import carregar
    imoveis, do_crm = carregar(arquivo_de_vitrine)
    assert do_crm is True
    codigos = {im.id for im in imoveis}
    assert acervo_no_crm[3] not in codigos, "imóvel indisponível não pode ser oferecido"
    assert set(acervo_no_crm[:3]) <= codigos


def test_preco_vem_do_crm_e_foto_vem_da_vitrine(ligado, acervo_no_crm, arquivo_de_vitrine):
    """Cada lado manda no que é dele. O preço em centavos no CRM vira reais aqui — é onde um fator
    de cem passaria batido e o agente ofereceria imóvel cem vezes fora do orçamento."""
    from sdr_ingestion.acervo import carregar
    imoveis, _ = carregar(arquivo_de_vitrine)
    im = next(x for x in imoveis if x.id == acervo_no_crm[0])
    assert im.preco == 3500.0
    assert im.condominio == 600.0
    assert im.fotos == ["/fotos/a.jpg", "/fotos/b.jpg"]
    assert im.suites == 1 and im.destaque_investimento is True
    assert im.regiao == "zona_oeste"


def test_imovel_so_do_crm_deduz_a_regiao_do_bairro(ligado, acervo_no_crm, arquivo_de_vitrine):
    """`regiao` é obrigatória no modelo e é o que faz a busca em cascata funcionar. Bairro→região é
    uma relação de fato, então deduzir é honesto — inventar o bairro não seria."""
    from sdr_ingestion.acervo import carregar
    imoveis, _ = carregar(arquivo_de_vitrine)
    orfao = next(x for x in imoveis if x.id == acervo_no_crm[1])
    assert orfao.regiao, "sem região o imóvel some da busca por zona"
    assert orfao.fotos == []


def test_sem_crm_o_arquivo_e_o_acervo(arquivo_de_vitrine, monkeypatch):
    from sdr_ingestion.acervo import carregar
    monkeypatch.delenv("SDR_CRM_URL", raising=False)
    monkeypatch.delenv("SDR_CRM_TOKEN", raising=False)
    imoveis, do_crm = carregar(arquivo_de_vitrine)
    assert do_crm is False, "sem fonte autoritativa não se autoriza purga"
    assert len(imoveis) == 1


# --------------------------------------------------------------------------- a purga

def test_purga_recusa_lista_vazia():
    """A guarda mais importante do arquivo.

    Uma leitura que falhou devolve vazio igual a um acervo que esvaziou, e a diferença entre as
    duas é o catálogo inteiro. Mesmo defeito que já apareceu na ingestão de documentos: esvaziar
    tem de ser ato explícito, nunca efeito colateral de uma fonte que não respondeu.
    """
    from sdr_shared.db import ImovelRepository
    with pytest.raises(ValueError, match="recusa lista vazia"):
        ImovelRepository().apagar_fora_de([])


def test_purga_tira_do_indice_o_que_saiu_do_acervo():
    from sdr_shared.db import ImovelRepository
    from sdr_shared.models import Imovel
    repo = ImovelRepository()

    def novo(codigo):
        return Imovel(id=codigo, tipo="apartamento", operacao="aluguel", cidade="São Paulo",
                      regiao="zona_oeste", bairro="Pinheiros", quartos=2, area_m2=70.0,
                      preco=3500.0, descricao="x")

    fica, sai = f"SP-P{uuid.uuid4().hex[:6]}", f"SP-P{uuid.uuid4().hex[:6]}"
    repo.upsert(novo(fica))
    repo.upsert(novo(sai))
    assert repo.get(sai) is not None

    # Lê os ids direto: a lista que sobrevive à purga é a que a ingestão passaria, e montá-la a
    # partir de uma busca pública acoplaria este teste ao formato de retorno dela.
    from sdr_shared.db.connection import get_pool
    with get_pool().connection() as conn:
        existentes = [r["id"] for r in conn.execute("SELECT id FROM imoveis").fetchall()]
    repo.apagar_fora_de([i for i in existentes if i != sai])

    assert repo.get(sai) is None
    assert repo.get(fica) is not None
