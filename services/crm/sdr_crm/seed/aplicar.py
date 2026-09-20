"""Escreve o dataset no banco, em uma transação só.

`ON CONFLICT (id) DO UPDATE` em toda tabela: é isto que torna o seed **idempotente**. Aplicar duas
vezes com os mesmos parâmetros deixa exatamente as mesmas linhas, com os mesmos identificadores —
o cenário "seed aplicado duas vezes" da seção 14.

Uma transação só, e não uma por tabela, porque um seed pela metade é pior que nenhum: as contagens
não fecham e o próximo teste falha por um motivo que não tem nada a ver com ele.
"""
import random
from datetime import timedelta

from ..db.connection import transacao
from . import gerar
from .gerar import Plano, det


def aplicar(p: Plano) -> dict[str, int]:
    usuarios = gerar.usuarios(p)
    imoveis = gerar.imoveis(p)
    leads = gerar.leads(p)
    oportunidades = gerar.oportunidades(p, leads)
    slots = gerar.slots(p, imoveis)

    with transacao() as conn:
        for u in usuarios:
            conn.execute(
                """INSERT INTO users (id, name, email, password_hash, role, active)
                   VALUES (%s, %s, %s, NULL, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, role = EXCLUDED.role""",
                (u["id"], u["name"], u["email"], u["role"], u["active"]))

        for x in imoveis:
            conn.execute(
                """INSERT INTO properties (id, code, title, description, city, neighborhood, type,
                       purpose, base_price_cents, condo_monthly_cents, property_tax_monthly_cents,
                       other_monthly_cents, bedrooms, parking, area_m2, status, synthetic, dataset_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s)
                   ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status,
                       description = EXCLUDED.description, base_price_cents = EXCLUDED.base_price_cents,
                       condo_monthly_cents = EXCLUDED.condo_monthly_cents""",
                (x["id"], x["code"], x["title"], x["description"], x["city"], x["neighborhood"],
                 x["type"], x["purpose"], x["base_price_cents"], x["condo_monthly_cents"],
                 x["property_tax_monthly_cents"], x["other_monthly_cents"], x["bedrooms"],
                 x["parking"], x["area_m2"], x["status"], p.dataset_id))

        for x in imoveis:
            # Reaplicar o seed não pode duplicar foto nem embaralhar a ordem: a chave (imóvel, url)
            # recusa a repetida e o UPDATE reafirma a posição.
            for posicao, url in enumerate(x.get("photos") or []):
                conn.execute(
                    """INSERT INTO property_photos (property_id, url, position)
                       VALUES (%s,%s,%s)
                       ON CONFLICT (property_id, url) DO UPDATE SET position = EXCLUDED.position""",
                    (x["id"], url, posicao))

        for x in leads:
            conn.execute(
                """INSERT INTO leads (id, name, email, phone_e164, external_contact_id, source,
                       contact_policy, synthetic, dataset_id, archived_at, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,true,%s,%s,%s)
                   ON CONFLICT (id) DO UPDATE SET contact_policy = EXCLUDED.contact_policy,
                       archived_at = EXCLUDED.archived_at""",
                (x["id"], x["name"], x["email"], x["phone_e164"], x["external_contact_id"],
                 x["source"], x["contact_policy"], p.dataset_id,
                 x["created_at"] if x["archived"] else None, x["created_at"]))

        for x in oportunidades:
            conn.execute(
                """INSERT INTO opportunities (id, lead_id, owner_id, purpose, stage, atendimento,
                       lost_reason, closed_at, dataset_id, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (id) DO UPDATE SET stage = EXCLUDED.stage,
                       atendimento = EXCLUDED.atendimento, lost_reason = EXCLUDED.lost_reason,
                       closed_at = EXCLUDED.closed_at""",
                (x["id"], x["lead_id"], x["owner_id"], x["purpose"], x["stage"], x["atendimento"],
                 x["lost_reason"], x["closed_at"], p.dataset_id, x["created_at"]))
            pr = x["preferencias"]
            conn.execute(
                """INSERT INTO preferences (opportunity_id, city, neighborhoods, property_types,
                       budget_min_cents, budget_max_cents, budget_basis, bedrooms_min, parking_min,
                       requirements)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT (opportunity_id) DO UPDATE SET city = EXCLUDED.city,
                       budget_max_cents = EXCLUDED.budget_max_cents,
                       neighborhoods = EXCLUDED.neighborhoods""",
                (x["id"], pr["city"], pr["neighborhoods"], pr["property_types"],
                 pr["budget_min_cents"], pr["budget_max_cents"], pr["budget_basis"],
                 pr["bedrooms_min"], pr["parking_min"], pr["requirements"]))

        for s in slots:
            conn.execute(
                """INSERT INTO availability_slots (id, property_id, broker_id, starts_at, ends_at,
                       dataset_id)
                   VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
                (s["id"], s["property_id"], s["broker_id"], s["starts_at"], s["ends_at"],
                 p.dataset_id))

        interacoes = _interacoes(p, leads, oportunidades, conn)
        visitas = _visitas(p, oportunidades, slots, imoveis, conn)
        tarefas = _tarefas(p, leads, oportunidades, conn)
        handoffs = _handoffs(p, oportunidades, conn)

    return {"users": len(usuarios), "properties": len(imoveis),
            "property_photos": sum(len(x.get("photos") or []) for x in imoveis), "leads": len(leads),
            "opportunities": len(oportunidades), "availability_slots": len(slots),
            "interactions": interacoes, "visits": visitas, "tasks": tarefas, "handoffs": handoffs}


def _interacoes(p: Plano, leads, oportunidades, conn) -> int:
    frases = ["Oi, vi o anúncio e queria saber se ainda está disponível.",
              "Procuro dois dormitórios, até R$ 3.000 com tudo incluso.",
              "Consigo visitar no sábado de manhã?",
              "Achei caro, tem algo parecido mais barato?",
              "Obrigado, vou pensar e retorno.",
              "Registro interno: cliente respondeu por telefone."]
    total = 0
    for i in range(300):
        op = oportunidades[i % len(oportunidades)]
        direcao = ["inbound", "outbound", "internal"][i % 3]
        conn.execute(
            """INSERT INTO interactions (id, lead_id, opportunity_id, channel, direction, summary,
                   external_event_id, occurred_at, actor_type, dataset_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'service',%s) ON CONFLICT (id) DO NOTHING""",
            (det(p.seed, "interaction", i), op["lead_id"], op["id"],
             gerar.CANAIS[i % len(gerar.CANAIS)], direcao,
             frases[i % len(frases)], f"sim-evt-{i:04d}",
             op["created_at"] + timedelta(hours=1 + (i % 48)), p.dataset_id))
        total += 1
    return total


def _visitas(p: Plano, oportunidades, slots, imoveis, conn) -> int:
    """20 visitas: 15 confirmadas nas oportunidades `visit_scheduled` e 5 solicitadas em
    `qualified` (seção 9). Encerradas não recebem visita futura ativa."""
    agendadas = [o for o in oportunidades if o["stage"] == "visit_scheduled"]
    qualificadas = [o for o in oportunidades if o["stage"] == "qualified"]
    proposito = {x["id"]: x["purpose"] for x in imoveis}
    total = 0
    usados = set()
    for i, op in enumerate(agendadas + qualificadas[:5]):
        confirmada = i < len(agendadas)
        # Cada visita confirmada em um slot diferente (o índice único parcial do banco recusaria
        # duas) E com o imóvel do mesmo propósito da oportunidade — visitar um imóvel de venda numa
        # busca por aluguel é massa incoerente, que faria um teste legítimo falhar sem bug nenhum.
        slot = next((s for s in slots if s["id"] not in usados
                     and proposito.get(s["property_id"]) == op["purpose"]), None)
        if slot is None:
            continue
        usados.add(slot["id"])
        conn.execute(
            """INSERT INTO visits (id, opportunity_id, property_id, slot_id, status, dataset_id)
               VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status""",
            (det(p.seed, "visit", i), op["id"], slot["property_id"], slot["id"],
             "confirmed" if confirmada else "requested", p.dataset_id))
        total += 1
    return total


def _tarefas(p: Plano, leads, oportunidades, conn) -> int:
    bloqueados = {x["id"] for x in leads if x["contact_policy"] == "blocked"}
    r = random.Random(f"{p.seed}:tarefas")
    total = 0
    for i in range(30):
        op = oportunidades[(i * 7) % len(oportunidades)]
        # Contato bloqueado nunca recebe `follow_up` — nem no seed. Uma massa que viola a própria
        # regra de negócio faz o primeiro teste de regressão falhar sem nenhum bug no código.
        tipo = "internal" if op["lead_id"] in bloqueados else ("follow_up" if i % 2 == 0 else "internal")
        vence = p.referencia + timedelta(days=r.randrange(-10, 15))
        conn.execute(
            """INSERT INTO tasks (id, opportunity_id, assignee_id, title, due_at, status, kind,
                   dataset_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
            (det(p.seed, "task", i), op["id"], op["owner_id"],
             ["Retornar contato", "Confirmar documentação", "Enviar opções", "Atualizar cadastro"][i % 4],
             vence, "done" if i % 5 == 0 else "open", tipo, p.dataset_id))
        total += 1
    return total


def _handoffs(p: Plano, oportunidades, conn) -> int:
    alvos = [o for o in oportunidades if o["stage"] in {"negotiation", "qualified"}][:10]
    total = 0
    for i, op in enumerate(alvos):
        conn.execute(
            """INSERT INTO handoffs (id, opportunity_id, reason, summary, assignee_id, status,
                   dataset_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING""",
            (det(p.seed, "handoff", i), op["id"], "cliente pediu falar com uma pessoa",
             "Cliente quer negociar valor e condições; agente parou aqui.", op["owner_id"],
             "accepted" if op["atendimento"] == "human" else "pending", p.dataset_id))
        total += 1
    return total
