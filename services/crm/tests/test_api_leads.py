"""Clientes: deduplicação, conflito entre identificadores, idempotência e política de contato.

Estes são os cenários 1, 2, 3, 5, 6 e 10 da matriz de validação (seção 14).
"""
import uuid

NOVO = {"name": "Cliente Sintético 001", "email": "cliente0001@example.com",
        "source": "agent_chat", "external_contact_id": "sim-chat-001", "synthetic": True}


def test_novo_cliente_cria_lead(agente):
    r = agente.post("/v1/leads", NOVO)
    assert r.status_code == 201, r.text
    assert r.json()["data"]["email"] == "cliente0001@example.com"
    assert r.json()["request_id"]


def test_cliente_que_volta_pelo_mesmo_email_nao_vira_segundo_cadastro(agente):
    primeiro = agente.post("/v1/leads", NOVO).json()["data"]
    # Mesmo e-mail, outra caixa, outro nome, outra origem: é a mesma pessoa voltando.
    volta = agente.post("/v1/leads", {"name": "Cliente 001", "email": "Cliente0001@EXAMPLE.com",
                                      "source": "site"})
    assert volta.status_code == 200          # 200, não 201: nada nasceu
    assert volta.json()["data"]["id"] == primeiro["id"]


def test_email_e_telefone_apontando_para_clientes_diferentes_e_409(agente):
    a = agente.post("/v1/leads", {"name": "A", "email": "a@example.com", "source": "site"})
    b = agente.post("/v1/leads", {"name": "B", "phone": "(11) 99999-0000", "source": "site"})
    assert (a.status_code, b.status_code) == (201, 201)

    conflito = agente.post("/v1/leads", {"name": "A ou B?", "email": "a@example.com",
                                         "phone": "11999990000", "source": "site"})
    assert conflito.status_code == 409
    corpo = conflito.json()["error"]
    assert corpo["code"] == "LEAD_CONFLICT"
    # Os dois IDs vão na resposta: quem revisa precisa saber quais registros olhar.
    assert len(corpo["details"]["lead_ids"]) == 2


def test_replay_da_mesma_chave_devolve_o_mesmo_id(cliente, token_agente):
    chave = f"lead-conversa-{uuid.uuid4()}"
    cab = {"Authorization": f"Bearer {token_agente}", "Idempotency-Key": chave}
    primeira = cliente.post("/v1/leads", json=NOVO, headers=cab)
    segunda = cliente.post("/v1/leads", json=NOVO, headers=cab)

    assert primeira.status_code == 201
    assert segunda.status_code == 201
    assert segunda.json()["data"]["id"] == primeira.json()["data"]["id"]
    assert segunda.headers.get("Idempotent-Replay") == "true"
    # E o request_id é o da PRIMEIRA: a resposta guardada é devolvida inteira, não recriada.
    assert segunda.json()["request_id"] == primeira.json()["request_id"]


def test_replay_gera_uma_linha_e_um_evento_de_auditoria(cliente, token_agente, humano):
    chave = f"lead-{uuid.uuid4()}"
    cab = {"Authorization": f"Bearer {token_agente}", "Idempotency-Key": chave}
    cliente.post("/v1/leads", json=NOVO, headers=cab)
    cliente.post("/v1/leads", json=NOVO, headers=cab)

    lista = humano.get("/v1/leads").json()["items"]
    assert len(lista) == 1
    eventos = humano.get("/v1/audit-events?entity_type=lead").json()["items"]
    assert len(eventos) == 1          # a mutação não rodou de novo, então não houve o que auditar


def test_mesma_chave_com_outro_corpo_e_409(cliente, token_agente):
    chave = f"lead-{uuid.uuid4()}"
    cab = {"Authorization": f"Bearer {token_agente}", "Idempotency-Key": chave}
    cliente.post("/v1/leads", json=NOVO, headers=cab)
    outro = cliente.post("/v1/leads", json={**NOVO, "name": "Outro nome"}, headers=cab)
    assert outro.status_code == 409
    assert outro.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_ordem_das_chaves_no_json_nao_muda_o_hash(cliente, token_agente):
    chave = f"lead-{uuid.uuid4()}"
    cab = {"Authorization": f"Bearer {token_agente}", "Idempotency-Key": chave}
    cliente.post("/v1/leads", json=NOVO, headers=cab)
    invertido = {k: NOVO[k] for k in reversed(list(NOVO))}
    r = cliente.post("/v1/leads", json=invertido, headers=cab)
    # Mesmo conteúdo em outra ordem é o MESMO corpo — 409 aqui puniria um cliente que não errou.
    assert r.status_code == 201
    assert r.headers.get("Idempotent-Replay") == "true"


def test_post_sem_idempotency_key_e_recusado(cliente, token_agente):
    r = cliente.post("/v1/leads", json=NOVO, headers={"Authorization": f"Bearer {token_agente}"})
    assert r.status_code == 409
    assert "Idempotency-Key" in r.json()["error"]["message"]


def test_lead_sem_identificador_e_422(agente):
    r = agente.post("/v1/leads", {"name": "Só o nome", "source": "site"})
    assert r.status_code == 422        # corpo mal formado: é sintaxe
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_campo_desconhecido_e_recusado(agente):
    # `budget_max` em vez de `budget_max_cents` tem de doer aqui, não três passos adiante.
    r = agente.post("/v1/leads", {**NOVO, "telefone": "11999990000"})
    assert r.status_code == 422


def test_agente_bloqueia_contato_mas_nao_libera(agente):
    lead = agente.post("/v1/leads", NOVO).json()["data"]
    versao = lead["version"]

    bloqueio = agente.patch(f"/v1/leads/{lead['id']}", {"contact_policy": "blocked"},
                            headers={"If-Match": f'"{versao}"'})
    assert bloqueio.status_code == 200
    assert bloqueio.json()["data"]["contact_policy"] == "blocked"

    liberacao = agente.patch(f"/v1/leads/{lead['id']}", {"contact_policy": "allowed"},
                             headers={"If-Match": f'"{bloqueio.json()["data"]["version"]}"'})
    assert liberacao.status_code == 403


def test_humano_libera_contato(humano, agente):
    lead = agente.post("/v1/leads", NOVO).json()["data"]
    r = humano.patch(f"/v1/leads/{lead['id']}", {"contact_policy": "allowed"},
                     headers={"If-Match": f'"{lead["version"]}"'})
    assert r.status_code == 200


def test_duas_edicoes_na_mesma_versao_uma_vence(agente):
    lead = agente.post("/v1/leads", NOVO).json()["data"]
    cab = {"If-Match": f'"{lead["version"]}"'}
    primeira = agente.patch(f"/v1/leads/{lead['id']}", {"name": "Nome A"}, headers=cab)
    segunda = agente.patch(f"/v1/leads/{lead['id']}", {"name": "Nome B"}, headers=cab)
    assert primeira.status_code == 200
    assert segunda.status_code == 412
    assert segunda.json()["error"]["details"]["current_version"] == lead["version"] + 1


def test_alteracao_sem_if_match_e_428(agente):
    lead = agente.post("/v1/leads", NOVO).json()["data"]
    r = agente.patch(f"/v1/leads/{lead['id']}", {"name": "X"})
    assert r.status_code == 428        # falta a precondição — não é 412, que é ela ter falhado


def test_detalhe_devolve_etag(agente):
    lead = agente.post("/v1/leads", NOVO).json()["data"]
    r = agente.get(f"/v1/leads/{lead['id']}")
    assert r.headers["ETag"] == f'"{lead["version"]}"'


def test_arquivado_some_da_lista_e_continua_acessivel_por_id(humano, agente):
    lead = agente.post("/v1/leads", NOVO).json()["data"]
    humano.patch(f"/v1/leads/{lead['id']}", {"archived": True},
                 headers={"If-Match": f'"{lead["version"]}"'})
    assert humano.get("/v1/leads").json()["items"] == []
    assert humano.get(f"/v1/leads/{lead['id']}").status_code == 200
    assert len(humano.get("/v1/leads?include_archived=true").json()["items"]) == 1


def test_agente_nao_arquiva(agente):
    lead = agente.post("/v1/leads", NOVO).json()["data"]
    r = agente.patch(f"/v1/leads/{lead['id']}", {"archived": True},
                     headers={"If-Match": f'"{lead["version"]}"'})
    assert r.status_code == 403


def test_evento_externo_reentregue_nao_duplica_o_historico(agente):
    lead = agente.post("/v1/leads", NOVO).json()["data"]
    corpo = {"channel": "telegram", "direction": "inbound", "summary": "Oi, ainda tem o apê?",
             "occurred_at": "2026-09-17T12:00:00Z", "external_event_id": "tg-42"}
    a = agente.post(f"/v1/leads/{lead['id']}/interactions", corpo)
    b = agente.post(f"/v1/leads/{lead['id']}/interactions", corpo)
    assert (a.status_code, b.status_code) == (201, 200)
    assert len(agente.get(f"/v1/leads/{lead['id']}/interactions").json()["items"]) == 1


def test_mesmo_id_de_evento_em_canais_diferentes_sao_mensagens_diferentes(agente):
    lead = agente.post("/v1/leads", NOVO).json()["data"]
    base = {"direction": "inbound", "summary": "Oi", "occurred_at": "2026-09-17T12:00:00Z",
            "external_event_id": "42"}
    agente.post(f"/v1/leads/{lead['id']}/interactions", {**base, "channel": "telegram"})
    agente.post(f"/v1/leads/{lead['id']}/interactions", {**base, "channel": "site"})
    assert len(agente.get(f"/v1/leads/{lead['id']}/interactions").json()["items"]) == 2


def test_mensagem_recebida_e_registrada_mesmo_com_contato_bloqueado(agente):
    """Bloqueio impede contato ativo, não impede ouvir. Perder a mensagem de quem pediu para não
    ser incomodado seria o pior dos dois mundos."""
    lead = agente.post("/v1/leads", {**NOVO, "contact_policy": "blocked"}).json()["data"]
    r = agente.post(f"/v1/leads/{lead['id']}/interactions",
                    {"channel": "telegram", "direction": "inbound", "summary": "Mudei de ideia",
                     "occurred_at": "2026-09-17T12:00:00Z"})
    assert r.status_code == 201


def test_sem_token_e_401(cliente):
    assert cliente.get("/v1/leads").status_code == 401


def test_token_revogado_e_recusado(cliente, token_agente):
    from sdr_crm.api import auth as autenticacao
    from sdr_crm.db.connection import transacao
    cab = {"Authorization": f"Bearer {token_agente}"}
    assert cliente.get("/v1/leads", headers=cab).status_code == 200
    with transacao() as conn:
        conn.execute("UPDATE service_credentials SET revoked_at = now() WHERE token_hash = %s",
                     (autenticacao.hash_token(token_agente),))
    r = cliente.get("/v1/leads", headers=cab)
    assert r.status_code == 401
    assert "revogada" in r.json()["error"]["message"]
