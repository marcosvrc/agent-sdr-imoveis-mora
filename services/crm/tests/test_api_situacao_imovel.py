"""Situação do imóvel: o que tira do catálogo, o que devolve, e o que isso protege."""
IMOVEL = {"code": "SP-8001", "title": "Apartamento de teste", "city": "São Paulo",
          "neighborhood": "Pinheiros", "type": "apartamento", "purpose": "rent",
          "base_price_cents": 300_000, "bedrooms": 2, "parking": 1}


def _imovel(humano, code):
    return humano.post("/v1/properties", {**IMOVEL, "code": code}).json()["data"]["id"]


def test_reservar_e_devolver_ao_catalogo(humano):
    """O par que importa: `reserved` na proposta aceita, e a VOLTA quando ela cai. Situação que só
    anda para a frente faz o acervo minguar sozinho."""
    pid = _imovel(humano, "SP-8001")
    r = humano.put(f"/v1/properties/{pid}/status", {"status": "reserved", "reason": "proposta aceita"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "reserved"

    # some do catálogo disponível, que é o que a Mora consome
    assert all(x["code"] != "SP-8001" for x in humano.get("/v1/properties").json()["items"])
    # mas continua acessível por código — quem pergunta por AQUELE imóvel quer saber que saiu
    assert humano.get("/v1/properties?code=SP-8001").json()["items"][0]["status"] == "reserved"

    volta = humano.put(f"/v1/properties/{pid}/status", {"status": "available"})
    assert volta.status_code == 200 and volta.json()["data"]["status"] == "available"
    assert any(x["code"] == "SP-8001" for x in humano.get("/v1/properties").json()["items"])


def test_sair_do_catalogo_exige_motivo_e_voltar_nao(humano):
    pid = _imovel(humano, "SP-8002")
    assert humano.put(f"/v1/properties/{pid}/status", {"status": "unavailable"}).status_code == 422
    assert humano.put(f"/v1/properties/{pid}/status",
                      {"status": "unavailable", "reason": "vendido"}).status_code == 200
    assert humano.put(f"/v1/properties/{pid}/status", {"status": "available"}).status_code == 200


def test_visita_confirmada_no_futuro_impede_tirar_do_catalogo(humano, corretor_id):
    """Tirar o imóvel por baixo de uma visita confirmada mandaria o corretor a um endereço para
    mostrar o que não está mais à venda — e ninguém seria avisado."""
    import uuid
    from datetime import UTC, datetime, timedelta
    from sdr_crm.db.connection import transacao

    pid = _imovel(humano, "SP-8003")
    inicio = datetime.now(UTC) + timedelta(days=2)
    slot = str(uuid.uuid4())
    with transacao() as conn:
        conn.execute("""INSERT INTO availability_slots (id, property_id, broker_id, starts_at, ends_at)
                        VALUES (%s,%s,%s,%s,%s)""",
                     (slot, pid, corretor_id, inicio, inicio + timedelta(hours=1)))
        lead = conn.execute("INSERT INTO leads (name, email, source) VALUES ('X', %s, 'site') RETURNING id",
                            (f"x{uuid.uuid4().hex[:8]}@example.com",)).fetchone()["id"]
        op = conn.execute("""INSERT INTO opportunities (lead_id, purpose, stage)
                             VALUES (%s,'rent','qualified') RETURNING id""", (lead,)).fetchone()["id"]
        conn.execute("""INSERT INTO visits (opportunity_id, property_id, slot_id, status)
                        VALUES (%s,%s,%s,'confirmed')""", (op, pid, slot))

    r = humano.put(f"/v1/properties/{pid}/status", {"status": "unavailable", "reason": "vendido"})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["details"]["visitas_confirmadas"] == 1
    # o caminho é cancelar a visita antes — e aí passa
    with transacao() as conn:
        conn.execute("UPDATE visits SET status = 'cancelled', cancellation_reason = 'x' "
                     "WHERE property_id = %s", (pid,))
    assert humano.put(f"/v1/properties/{pid}/status",
                      {"status": "unavailable", "reason": "vendido"}).status_code == 200


def test_agente_nao_muda_situacao_de_imovel(agente, humano):
    """A trava de sempre: o acervo é humano. Um agente que tira imóvel de circulação a partir de
    uma conversa é a versão destrutiva do anúncio inventado."""
    pid = _imovel(humano, "SP-8004")
    assert agente.put(f"/v1/properties/{pid}/status",
                      {"status": "unavailable", "reason": "x"}).status_code == 403


def test_mudar_para_a_mesma_situacao_e_recusado(humano):
    """Não é purismo: aceitar geraria um evento de auditoria dizendo que alguém mudou algo que não
    mudou, e a auditoria é onde se vai procurar o que aconteceu."""
    pid = _imovel(humano, "SP-8005")
    r = humano.put(f"/v1/properties/{pid}/status", {"status": "available"})
    assert r.status_code == 409


def test_procura_conta_clientes_distintos_e_ignora_descartado(humano, corretor_id):
    """Dois clientes no mesmo imóvel é normal — o que faltava era o corretor saber disso.

    Quem descartou o imóvel não entra: é o oposto de procura."""
    import uuid
    from sdr_crm.db.connection import transacao

    pid = _imovel(humano, "SP-8006")
    with transacao() as conn:
        for situacao in ("presented", "interested", "rejected"):
            lead = conn.execute("INSERT INTO leads (name, email, source) VALUES ('X', %s, 'site') RETURNING id",
                                (f"p{uuid.uuid4().hex[:8]}@example.com",)).fetchone()["id"]
            op = conn.execute("""INSERT INTO opportunities (lead_id, purpose, stage)
                                 VALUES (%s,'rent','qualified') RETURNING id""", (lead,)).fetchone()["id"]
            conn.execute("""INSERT INTO property_interests (opportunity_id, property_id, status)
                            VALUES (%s,%s,%s)""", (op, pid, situacao))

    achado = next(x for x in humano.get("/v1/properties?code=SP-8006").json()["items"])
    assert achado["interested_count"] == 2, "o descartado não conta"
    assert humano.get(f"/v1/properties/{pid}").json()["data"]["interested_count"] == 2
