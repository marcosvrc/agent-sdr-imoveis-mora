"""Paginação do catálogo com orçamento pelo total mensal (filtro aplicado fora do SQL)."""
import uuid

import pytest

from sdr_crm.api.routers import imoveis_rt


def _imovel(humano, i: int, cabe: bool) -> str:
    # Total mensal = aluguel + condomínio + IPTU. Os que "cabem" ficam em 300 mil centavos; os
    # outros, em 900 mil — o teto do teste é 400 mil.
    r = humano.post("/v1/properties", {
        "code": f"PG-{i}-{uuid.uuid4().hex[:4]}", "title": f"Imóvel {i}", "city": "São Paulo",
        "neighborhood": "Moema", "type": "apartamento", "purpose": "rent",
        "base_price_cents": 250_000 if cabe else 850_000, "condo_monthly_cents": 40_000,
        "property_tax_monthly_cents": 10_000, "other_monthly_cents": 0, "bedrooms": 2, "parking": 1})
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


def _todas_as_paginas(humano, limite: int) -> list[list[str]]:
    paginas, cursor = [], None
    for _ in range(20):
        url = (f"/v1/properties?purpose=rent&max_price_cents=400000&budget_basis=monthly_total"
               f"&limit={limite}" + (f"&cursor={cursor}" if cursor else ""))
        corpo = humano.get(url).json()
        paginas.append([x["id"] for x in corpo["items"]])
        if not (cursor := corpo["next_cursor"]):
            break
    return paginas


@pytest.mark.parametrize("lote", [3, imoveis_rt.LOTE_ORCAMENTO])
def test_paginar_pelo_total_mensal_nao_pula_nem_repete(humano, monkeypatch, lote):
    """O filtro em Python rodava DEPOIS de cortar `limit+1` linhas no SQL, e o cursor saía da linha
    `n-1` do SQL, não do último item devolvido: uma página com caros no meio vinha curta, sem
    próxima página, ou pulava imóveis que cabiam no orçamento."""
    monkeypatch.setattr(imoveis_rt, "LOTE_ORCAMENTO", lote)    # 3: força várias idas ao banco
    padrao = [True, False, False, True, False, True, True, False, False, False, True, False, True]
    criados = [_imovel(humano, i, cabe) for i, cabe in enumerate(padrao)]
    cabem = [pid for pid, c in zip(criados, padrao, strict=True) if c]

    paginas = _todas_as_paginas(humano, limite=2)
    vistos = [pid for p in paginas for pid in p]

    assert sorted(vistos) == sorted(cabem), "pulou ou repetiu imóvel"
    assert len(vistos) == len(set(vistos))
    assert all(len(p) == 2 for p in paginas[:-1]), f"página curta no meio: {paginas}"


def test_base_price_continua_igual(humano):
    ids = [_imovel(humano, i, True) for i in range(3)]
    corpo = humano.get("/v1/properties?purpose=rent&max_price_cents=400000&limit=2").json()
    assert len(corpo["items"]) == 2 and corpo["next_cursor"]
    resto = humano.get(f"/v1/properties?purpose=rent&max_price_cents=400000&limit=2"
                       f"&cursor={corpo['next_cursor']}").json()
    assert sorted([x["id"] for x in corpo["items"] + resto["items"]]) == sorted(ids)
    assert resto["next_cursor"] is None
