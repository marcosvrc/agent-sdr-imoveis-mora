"""Corretor assume / responde / devolve a conversa. Enquanto em handoff, a Mora fica em silêncio."""
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sdr_shared.db import LeadRepository, CanalRepository, MensagemRepository, CorretorRepository
from sdr_shared.messaging import RespostaAgente
from sdr_shared.models import Estagio
from sdr_shared.ports import get_broker, get_scheduler
from ..auth import corretor_atual

router = APIRouter()


class Texto(BaseModel):
    texto: str


class AssumirIn(BaseModel):
    corretor_id: str | None = None     # opcional: em nome de qual corretor do cadastro


def _lead(lead_id: str):
    if lead := LeadRepository().get(lead_id):
        return lead
    raise HTTPException(404)


@router.post("/{lead_id}/assumir")
def assumir(lead_id: str, body: AssumirIn | None = None, corretor=Depends(corretor_atual)):
    """Corretor assume a conversa. Responsável: o informado no body → o já vinculado → roteamento
    por região → ninguém (fila da equipe).

    O último caso já foi "o usuário logado", e isso gravava no lead um id que não existe no cadastro
    de corretores: hoje o literal `corretor-dev`, vindo do token do painel. Quem está
    logado é um ATOR (serve para auditoria), não necessariamente um corretor cadastrado — e o lead
    ficava atribuído a alguém que a tela de corretores não conhece. Sem corretor apto, o certo é
    deixar na fila da equipe, estado que o sistema já entende (`corretor_id IS NULL`).
    """
    lead = _lead(lead_id)
    repo = CorretorRepository()
    if body and body.corretor_id:
        co = repo.get(body.corretor_id)
        if not co or not co.ativo:
            raise HTTPException(422, "corretor inexistente ou inativo")
        lead.corretor_id = co.id
    elif not (lead.corretor_id and repo.get(lead.corretor_id)):
        lead.corretor_id = co.id if (co := repo.escolher(lead.cartao.regiao)) else None
    nomes = repo.nomes()
    # Lead em handoff com OUTRO corretor não muda de dono por aqui: eram dois corretores falando com
    # o mesmo cliente, e o primeiro descobria pelo cliente. Trocar o responsável é ato explícito
    # (PUT /leads/{id}/corretor). A condição vai no UPDATE para valer também com dois cliques juntos.
    if not LeadRepository().assumir_handoff(lead_id, lead.corretor_id):   # visitas futuras acompanham
        atual = LeadRepository().get(lead_id)
        dono = atual.corretor_id if atual else None
        raise HTTPException(409, f"lead já assumido por {nomes.get(dono, dono)}; para trocar o "
                                 "responsável, use a atribuição de corretor")
    get_scheduler().cancel(lead_id)
    return {"lead_id": lead_id, "corretor_id": lead.corretor_id, "corretor_nome": nomes.get(lead.corretor_id), "estagio": "handoff"}


@router.post("/{lead_id}/responder")
def responder(lead_id: str, body: Texto, corretor=Depends(corretor_atual)):
    """Envia a mensagem do corretor por TODOS os canais do lead (Telegram e/ou web), sem passar pelo agente.

    Só com o lead em handoff: fora dele a Mora segue respondendo o cliente, e a mensagem do
    corretor chegava no meio da conversa do agente — duas vozes, uma sem saber da outra."""
    if _lead(lead_id).estagio != Estagio.HANDOFF:
        raise HTTPException(409, "o lead não está em atendimento humano: assuma a conversa antes de responder")
    canais = CanalRepository().canais_do_lead(lead_id)
    if not canais:
        raise HTTPException(409, "lead sem canal vinculado")
    resposta = RespostaAgente(lead_id=lead_id, texto=body.texto)
    for c in canais:
        get_broker().publish(f"outbound-{c['canal']}", json.dumps(
            {"identificador": c["identificador"], "resposta": resposta.model_dump(mode="json")}), key=lead_id)
    MensagemRepository().registrar(lead_id, canais[0]["canal"], "corretor", body.texto, {"corretor_id": corretor["id"]})
    return {"ok": True, "canais": [c["canal"] for c in canais]}


@router.post("/{lead_id}/devolver")
def devolver(lead_id: str, corretor=Depends(corretor_atual)):
    lead = _lead(lead_id)
    lead.estagio = Estagio.QUALIFICADO if lead.cartao.completo() else Estagio.QUALIFICANDO
    LeadRepository().upsert(lead)
    return {"lead_id": lead_id, "estagio": lead.estagio}
