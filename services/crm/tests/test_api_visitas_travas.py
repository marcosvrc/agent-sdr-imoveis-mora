"""Visitas: confirmar/cancelar sem regredir o funil, nada no passado, e remarcar com as travas de pedir."""
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from sdr_crm.db.connection import get_pool, transacao

IMOVEL = {"code": "SP-8001", "title": "Apto", "city": "São Paulo", "neighborhood": "Pinheiros",
          "type": "apartamento", "purpose": "rent", "base_price_cents": 300_000,
          "bedrooms": 2, "parking": 1}


def _cenario(humano, corretor_id, *, status="requested", stage="qualified", dias=None):
    """Imóvel, dois horários, oportunidade e uma visita. `dias` negativo põe o 1º horário no passado."""
    code = f"SP-{uuid.uuid4().int % 10**6}"
    pid = humano.post("/v1/properties", {**IMOVEL, "code": code}).json()["data"]["id"]
    inicio = datetime.now(UTC) + timedelta(days=dias if dias is not None else 2 + uuid.uuid4().int % 900)
    slots = [str(uuid.uuid4()), str(uuid.uuid4())]
    with transacao() as conn:
        for i, s in enumerate(slots):
            conn.execute("""INSERT INTO availability_slots (id, property_id, broker_id, starts_at, ends_at)
                            VALUES (%s,%s,%s,%s,%s)""",
                         (s, pid, corretor_id, inicio + timedelta(days=4000 * i),
                          inicio + timedelta(days=4000 * i, hours=1)))
        lead = conn.execute("INSERT INTO leads (name, email, source) VALUES ('X', %s, 'site') RETURNING id",
                            (f"x{uuid.uuid4().hex[:8]}@example.com",)).fetchone()["id"]
        fechada = stage in ("won", "lost")
        op = conn.execute("""INSERT INTO opportunities (lead_id, purpose, stage, lost_reason, closed_at)
                             VALUES (%s,'rent',%s,%s,%s) RETURNING id""",
                          (lead, stage, "x" if stage == "lost" else None,
                           datetime.now(UTC) if fechada else None)).fetchone()["id"]
        vid = conn.execute("""INSERT INTO visits (opportunity_id, property_id, slot_id, status)
                              VALUES (%s,%s,%s,%s) RETURNING id""", (op, pid, slots[0], status)).fetchone()["id"]
    return pid, slots, str(op), str(vid)


def _estagio(oid: str) -> str:
    with transacao() as conn:
        return conn.execute("SELECT stage FROM opportunities WHERE id = %s", (oid,)).fetchone()["stage"]


def _transicao(humano, vid, alvo, motivo=None):
    versao = humano.get(f"/v1/visits/{vid}").json()["data"]["version"]
    corpo = {"target_status": alvo, **({"reason": motivo} if motivo else {})}
    return humano.post(f"/v1/visits/{vid}/transitions", corpo, headers={"If-Match": f'"{versao}"'})


@pytest.fixture
def negociacao_em_curso():
    """Outra transação move a oportunidade para `negotiation` e ainda não fez commit — a janela em
    que a visita lida sem trava enxerga o estágio velho."""
    def abrir(oid: str):
        conn = get_pool().getconn()
        conn.execute("UPDATE opportunities SET stage = 'negotiation' WHERE id = %s", (oid,))
        return conn
    abertas = []
    yield lambda oid: abertas.append(abrir(oid)) or abertas[-1]
    for c in abertas:
        c.rollback()
        get_pool().putconn(c)


def _durante(conexao, acao):
    """Roda `acao` numa thread enquanto `conexao` segura a oportunidade; depois faz o commit."""
    saida = {}
    t = threading.Thread(target=lambda: saida.update(r=acao()))
    t.start()
    time.sleep(0.5)                     # a requisição chega e lê enquanto a outra não comitou
    conexao.commit()
    t.join(10)
    return saida["r"]


# ------------------------------------------------------------------ B8

def test_confirmar_nao_regride_negociacao_que_andou_em_paralelo(humano, corretor_id, negociacao_em_curso):
    """A visita era lida com o estágio da oportunidade SEM trava, e o UPDATE gravava
    `visit_scheduled` sem condição: uma negociação aberta no meio voltava para visita marcada."""
    _, _, oid, vid = _cenario(humano, corretor_id)
    versao = humano.get(f"/v1/visits/{vid}").json()["data"]["version"]
    outra = negociacao_em_curso(oid)
    r = _durante(outra, lambda: humano.post(f"/v1/visits/{vid}/transitions", {"target_status": "confirmed"},
                                            headers={"If-Match": f'"{versao}"'}))
    assert r.status_code == 200, r.text
    assert _estagio(oid) == "negotiation"
    assert r.json()["data"]["opportunity_stage"] is None


def test_cancelar_nao_regride_negociacao_que_andou_em_paralelo(humano, corretor_id, negociacao_em_curso):
    _, _, oid, vid = _cenario(humano, corretor_id, status="confirmed", stage="visit_scheduled")
    versao = humano.get(f"/v1/visits/{vid}").json()["data"]["version"]
    outra = negociacao_em_curso(oid)
    r = _durante(outra, lambda: humano.post(f"/v1/visits/{vid}/transitions",
                                            {"target_status": "cancelled", "reason": "cliente desistiu"},
                                            headers={"If-Match": f'"{versao}"'}))
    assert r.status_code == 200, r.text
    assert _estagio(oid) == "negotiation", "o recálculo usou o estágio lido antes da negociação"


def test_confirmar_continua_avancando_qualificada(humano, corretor_id):
    _, _, oid, vid = _cenario(humano, corretor_id)
    r = _transicao(humano, vid, "confirmed")
    assert r.status_code == 200 and r.json()["data"]["opportunity_stage"] == "visit_scheduled"
    assert _estagio(oid) == "visit_scheduled"


def test_nao_confirma_visita_em_horario_que_ja_passou(humano, corretor_id):
    """Solicitar já recusava horário no passado; confirmar não — e a visita "confirmada" de ontem
    movia a oportunidade para visita marcada."""
    _, _, oid, vid = _cenario(humano, corretor_id, dias=-1)
    r = _transicao(humano, vid, "confirmed")
    assert r.status_code == 409 and "passado" in r.json()["error"]["message"]
    assert _estagio(oid) == "qualified"


# ------------------------------------------------------------------ B9

def test_agente_nao_remarca_com_atendimento_humano(agente, humano, corretor_id):
    _, slots, oid, vid = _cenario(humano, corretor_id)
    with transacao() as conn:
        conn.execute("UPDATE opportunities SET atendimento = 'human' WHERE id = %s", (oid,))
    r = agente.post(f"/v1/visits/{vid}/reschedule", {"slot_id": slots[1], "reason": "x"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "HUMAN_IN_CONTROL"
    # o corretor, que é quem está atendendo, pode
    assert humano.post(f"/v1/visits/{vid}/reschedule", {"slot_id": slots[1], "reason": "x"}).status_code == 201


@pytest.mark.parametrize("stage", ["won", "lost"])
def test_oportunidade_encerrada_nao_remarca(humano, corretor_id, stage):
    _, slots, _, vid = _cenario(humano, corretor_id, stage=stage)
    r = humano.post(f"/v1/visits/{vid}/reschedule", {"slot_id": slots[1], "reason": "x"})
    assert r.status_code == 409 and "encerrada" in r.json()["error"]["message"]


def test_imovel_indisponivel_nao_remarca(humano, corretor_id):
    pid, slots, _, vid = _cenario(humano, corretor_id)
    with transacao() as conn:
        conn.execute("UPDATE properties SET status = 'unavailable' WHERE id = %s", (pid,))
    r = humano.post(f"/v1/visits/{vid}/reschedule", {"slot_id": slots[1], "reason": "x"})
    assert r.status_code == 409 and "disponível" in r.json()["error"]["message"]
    assert humano.get(f"/v1/visits/{vid}").json()["data"]["status"] == "requested"
