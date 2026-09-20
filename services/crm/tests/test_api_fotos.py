"""Fotos do imóvel: quem cadastra, o que é recusado e quem vence na hora de indexar."""
IMOVEL = {"code": "SP-9001", "title": "Apartamento de teste", "city": "São Paulo",
          "neighborhood": "Pinheiros", "type": "apartamento", "purpose": "rent",
          "base_price_cents": 300_000, "bedrooms": 2, "parking": 1}


def test_cadastro_com_fotos_guarda_a_ordem_e_devolve_na_leitura(humano):
    r = humano.post("/v1/properties", {**IMOVEL, "photos": [
        {"url": "https://cdn.exemplo/sp9001/sala.jpg", "alt": "Sala com varanda"},
        {"url": "https://cdn.exemplo/sp9001/quarto.jpg"},
    ]})
    assert r.status_code == 201, r.text
    pid = r.json()["data"]["id"]
    fotos = r.json()["data"]["photos"]
    assert [f["url"] for f in fotos] == ["https://cdn.exemplo/sp9001/sala.jpg",
                                         "https://cdn.exemplo/sp9001/quarto.jpg"]
    assert [f["position"] for f in fotos] == [0, 1], "a capa é a primeira, e a ordem é do índice"
    assert fotos[0]["alt"] == "Sala com varanda" and fotos[1]["alt"] is None

    # e a lista do catálogo também traz — é dela que a reindexação da Mora se alimenta
    lista = humano.get("/v1/properties?code=SP-9001").json()["items"]
    assert [f["url"] for f in lista[0]["photos"]] == [f["url"] for f in fotos]
    assert humano.get(f"/v1/properties/{pid}").json()["data"]["photos"][0]["position"] == 0


def test_url_que_nao_e_http_e_recusada(humano):
    """O que entra aqui vira `<img src>` na vitrine e dado estruturado da ficha. `javascript:` e
    `data:` nesse lugar são script de terceiro rodando na página do cliente."""
    for ruim in ("javascript:alert(1)", "data:text/html;base64,PHNjcmlwdD4=", "/local/foto.jpg"):
        r = humano.post("/v1/properties", {**IMOVEL, "code": "SP-9002",
                                           "photos": [{"url": ruim}]})
        assert r.status_code == 422, f"{ruim} passou"


def test_agente_nao_cadastra_imovel_nem_mexe_em_foto(agente, humano):
    """A trava que já existia para o imóvel vale para a galeria: anúncio inventado numa conversa
    é o caminho mais curto para a imobiliária responder por algo que não existe."""
    assert agente.post("/v1/properties", IMOVEL).status_code == 403
    pid = humano.post("/v1/properties", {**IMOVEL, "code": "SP-9003"}).json()["data"]["id"]
    assert agente.put(f"/v1/properties/{pid}/photos",
                      {"photos": [{"url": "https://cdn.exemplo/x.jpg"}]}).status_code == 403


def test_substituir_a_galeria_apaga_o_que_saiu_e_reordena(humano):
    pid = humano.post("/v1/properties", {**IMOVEL, "code": "SP-9004", "photos": [
        {"url": "https://cdn.exemplo/a.jpg"}, {"url": "https://cdn.exemplo/b.jpg"},
        {"url": "https://cdn.exemplo/c.jpg"}]}).json()["data"]["id"]

    # quem tirou a foto do meio e inverteu as outras espera exatamente isso
    r = humano.put(f"/v1/properties/{pid}/photos", {"photos": [
        {"url": "https://cdn.exemplo/c.jpg"}, {"url": "https://cdn.exemplo/a.jpg"}]})
    assert r.status_code == 200, r.text
    assert [f["url"] for f in r.json()["data"]["photos"]] == ["https://cdn.exemplo/c.jpg",
                                                              "https://cdn.exemplo/a.jpg"]
    assert [f["position"] for f in r.json()["data"]["photos"]] == [0, 1]
    assert humano.put(f"/v1/properties/{pid}/photos", {"photos": []}).json()["data"]["photos"] == []


def test_a_mesma_foto_duas_vezes_e_recusada(humano):
    r = humano.post("/v1/properties", {**IMOVEL, "code": "SP-9005", "photos": [
        {"url": "https://cdn.exemplo/igual.jpg"}, {"url": "https://cdn.exemplo/igual.jpg"}]})
    assert r.status_code == 422, r.text
