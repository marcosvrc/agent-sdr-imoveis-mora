"""Remarcação de visita: uma operação, não cancelar e pedir de novo."""
import uuid
from datetime import UTC, datetime, timedelta

from sdr_crm.db.connection import transacao

IMOVEL = {"code": "SP-7001", "title": "Apto", "city": "São Paulo", "neighborhood": "Pinheiros",
          "type": "apartamento", "purpose": "rent", "base_price_cents": 300_000,
          "bedrooms": 2, "parking": 1}


def _cenario(humano, corretor_id, code, *, confirmada: bool):
    """Um imóvel, dois horários futuros, uma oportunidade qualificada e uma visita.

    As semanas são deslocadas pelo código do imóvel porque o banco impede o MESMO corretor de ter
    horários sobrepostos — inclusive em imóveis diferentes, que é a regra certa: a pessoa é uma só.
    Dois cenários no mesmo instante estouravam a restrição de exclusão, e o vermelho era do teste.
    """
    pid = humano.post("/v1/properties", {**IMOVEL, "code": code}).json()["data"]["id"]
    inicio = datetime.now(UTC) + timedelta(days=2 + 10 * int(code.split("-")[1]) % 500)
    slots = [str(uuid.uuid4()), str(uuid.uuid4())]
    with transacao() as conn:
        for i, s in enumerate(slots):
            conn.execute("""INSERT INTO availability_slots (id, property_id, broker_id, starts_at, ends_at)
                            VALUES (%s,%s,%s,%s,%s)""",
                         (s, pid, corretor_id, inicio + timedelta(days=i),
                          inicio + timedelta(days=i, hours=1)))
        lead = conn.execute("INSERT INTO leads (name, email, source) VALUES ('X', %s, 'site') RETURNING id",
                            (f"x{uuid.uuid4().hex[:8]}@example.com",)).fetchone()["id"]
        op = conn.execute("""INSERT INTO opportunities (lead_id, purpose, stage)
                             VALUES (%s,'rent','qualified') RETURNING id""", (lead,)).fetchone()["id"]
        vid = conn.execute("""INSERT INTO visits (opportunity_id, property_id, slot_id, status)
                              VALUES (%s,%s,%s,%s) RETURNING id""",
                           (op, pid, slots[0], "confirmed" if confirmada else "requested")).fetchone()["id"]
    return pid, slots, str(op), str(vid)


def test_remarcar_liga_a_antiga_na_nova(humano, corretor_id):
    """O motivo de existir: sem o vínculo, o histórico fica com dois eventos soltos e a visita
    cancelada parece cliente perdido."""
    _, slots, _, vid = _cenario(humano, corretor_id, "SP-7001", confirmada=False)

    r = humano.post(f"/v1/visits/{vid}/reschedule",
                    {"slot_id": slots[1], "reason": "cliente pediu outro dia"})
    assert r.status_code == 201, r.text
    nova = r.json()["data"]
    assert nova["slot_id"] == slots[1]

    antiga = humano.get(f"/v1/visits/{vid}").json()["data"]
    assert antiga["status"] == "cancelled"
    assert antiga["cancellation_reason"] == "cliente pediu outro dia"
    assert antiga["rescheduled_to"] == nova["id"], "é a seta que o histórico não reconstrói sozinho"


def test_humano_remarcando_confirmada_ja_nasce_confirmada(humano, corretor_id):
    """A fricção que a remarcação existia para tirar: quem remarca uma visita confirmada é quem
    confirma, e obrigá-lo a confirmar de novo é passo sem decisão."""
    _, slots, _, vid = _cenario(humano, corretor_id, "SP-7002", confirmada=True)
    nova = humano.post(f"/v1/visits/{vid}/reschedule",
                       {"slot_id": slots[1], "reason": "corretor remarcou"}).json()["data"]
    assert nova["status"] == "confirmed"


def test_agente_remarca_solicitada_mas_nao_confirmada(agente, humano, corretor_id):
    """Mesma regra do cancelamento: quebrar compromisso já combinado é ato de gente. E o que o
    agente remarca nasce SOLICITADO — confirmar continua sendo humano."""
    _, slots, _, vid = _cenario(humano, corretor_id, "SP-7003", confirmada=False)
    nova = agente.post(f"/v1/visits/{vid}/reschedule",
                       {"slot_id": slots[1], "reason": "cliente pediu"}).json()["data"]
    assert nova["status"] == "requested"

    _, slots2, _, vid2 = _cenario(humano, corretor_id, "SP-7004", confirmada=True)
    r = agente.post(f"/v1/visits/{vid2}/reschedule", {"slot_id": slots2[1], "reason": "x"})
    assert r.status_code == 409 and "não remarca visita já confirmada" in r.json()["error"]["message"]


def test_horario_ja_tomado_nao_cancela_a_antiga(humano, corretor_id):
    """A razão de ser uma transação só: se a nova não pode existir, a antiga não pode sumir —
    senão a remarcação que falhou deixaria o cliente sem visita nenhuma."""
    pid, slots, _, vid = _cenario(humano, corretor_id, "SP-7005", confirmada=True)
    # alguém confirma o horário de destino primeiro
    with transacao() as conn:
        lead = conn.execute("INSERT INTO leads (name, email, source) VALUES ('Y', %s, 'site') RETURNING id",
                            (f"y{uuid.uuid4().hex[:8]}@example.com",)).fetchone()["id"]
        op2 = conn.execute("""INSERT INTO opportunities (lead_id, purpose, stage)
                              VALUES (%s,'rent','qualified') RETURNING id""", (lead,)).fetchone()["id"]
        conn.execute("""INSERT INTO visits (opportunity_id, property_id, slot_id, status)
                        VALUES (%s,%s,%s,'confirmed')""", (op2, pid, slots[1]))

    r = humano.post(f"/v1/visits/{vid}/reschedule", {"slot_id": slots[1], "reason": "tentativa"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "SLOT_UNAVAILABLE"
    assert humano.get(f"/v1/visits/{vid}").json()["data"]["status"] == "confirmed", \
        "a visita original tem de continuar de pé"


def test_recusas_de_horario(humano, corretor_id):
    _, slots, _, vid = _cenario(humano, corretor_id, "SP-7006", confirmada=False)
    assert humano.post(f"/v1/visits/{vid}/reschedule",
                       {"slot_id": slots[0], "reason": "x"}).status_code == 409   # o mesmo horário
    assert humano.post(f"/v1/visits/{vid}/reschedule",
                       {"slot_id": str(uuid.uuid4()), "reason": "x"}).status_code == 404
    assert humano.post(f"/v1/visits/{vid}/reschedule", {"slot_id": slots[1]}).status_code == 422
