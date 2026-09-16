from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import json
import time

from sdr_shared.db import LeadRepository, MensagemRepository, CanalRepository, CorretorRepository, ClienteRepository, auditar
from sdr_shared.ports import get_broker
from ..auth import corretor_atual

router = APIRouter(dependencies=[Depends(corretor_atual)])

_JANELA_S = 600          # o painel recarrega sozinho; registrar cada refresh viraria ruído
_ultimo_acesso: dict[str, float] = {}      # chave → instante do último registro (None = nunca)


def _auditar_acesso_em_massa(ator: dict, filtros: dict, n: int) -> None:
    """Ver a carteira inteira de leads é acesso a dado de cliente — registra uma vez por janela, por corretor."""
    chave = f"{ator.get('id')}|{sorted(filtros.items())}"
    agora = time.monotonic()
    anterior = _ultimo_acesso.get(chave)
    # `anterior is None` em vez de comparar com zero: monotonic() começa perto de zero quando o
    # processo sobe, e o primeiro acesso de um container novo ficaria sem registro.
    if anterior is not None and agora - anterior < _JANELA_S:
        return
    _ultimo_acesso[chave] = agora
    auditar(acao="lead.listado", entidade="lead", ator_tipo="corretor", ator_id=ator.get("id"),
            ator_nome=ator.get("email"), dados={"filtros": filtros, "leads": n, "janela_min": _JANELA_S // 60})


def _com_corretor(lead, nomes: dict[str, str]) -> dict:
    d = lead.model_dump(mode="json")
    d["corretor_nome"] = nomes.get(lead.corretor_id) if lead.corretor_id else None
    return d


@router.get("")
def listar(estagio: str | None = None, temperatura: str | None = None, corretor_id: str | None = None,
           ator: dict = Depends(corretor_atual)):
    nomes = CorretorRepository().nomes()
    leads = [_com_corretor(l, nomes) for l in LeadRepository().listar(estagio, temperatura, corretor_id=corretor_id)]
    _auditar_acesso_em_massa(ator, {k: v for k, v in
                                    {"estagio": estagio, "temperatura": temperatura, "corretor_id": corretor_id}.items()
                                    if v}, len(leads))
    return leads


@router.get("/{lead_id}")
def detalhe(lead_id: str):
    lead = LeadRepository().get(lead_id)
    if not lead:
        raise HTTPException(404)
    outras = [o for o in ClienteRepository().oportunidades(lead.cliente_id) if o["id"] != lead_id] if lead.cliente_id else []
    return {**_com_corretor(lead, CorretorRepository().nomes()), "canais": CanalRepository().canais_do_lead(lead_id),
            "outras_oportunidades": outras}


@router.get("/{lead_id}/mensagens")
def mensagens(lead_id: str):
    return MensagemRepository().historico(lead_id)


class CorretorIn(BaseModel):
    corretor_id: str | None = None     # null = desvincular


@router.put("/{lead_id}/corretor")
def atribuir(lead_id: str, body: CorretorIn):
    """Atribui (ou troca/remove) o corretor responsável pelo lead; visitas futuras acompanham."""
    if not LeadRepository().get(lead_id):
        raise HTTPException(404)
    nome = None
    if body.corretor_id:
        co = CorretorRepository().get(body.corretor_id)
        if not co or not co.ativo:
            raise HTTPException(422, "corretor inexistente ou inativo")
        nome = co.nome
    LeadRepository().atribuir_corretor(lead_id, body.corretor_id)
    return {"lead_id": lead_id, "corretor_id": body.corretor_id, "corretor_nome": nome}


class ReativacaoIn(BaseModel):
    aceita: bool


@router.put("/{lead_id}/reativacao")
def preferencia_de_reativacao(lead_id: str, body: ReativacaoIn, ator: dict = Depends(corretor_atual)):
    """Liga/desliga o aviso de imóvel novo para este lead.

    O cliente pode desligar sozinho pela conversa ("não quero mais avisos"), mas o pedido também
    chega por telefone, por e-mail e no meio de uma visita — e aí quem registra é o corretor. Sem
    esta rota, honrar um opt-out exigiria UPDATE no banco, que é o mesmo que não honrar.
    """
    if not LeadRepository().definir_aceita_reativacao(lead_id, body.aceita):
        raise HTTPException(404)
    auditar(acao="lead.preferencia_reativacao", entidade="lead", entidade_id=lead_id, ator_tipo="corretor",
            ator_id=ator.get("id"), ator_nome=ator.get("email"), dados={"aceita_reativacao": body.aceita})
    return {"lead_id": lead_id, "aceita_reativacao": body.aceita}


@router.post("/{lead_id}/analisar", status_code=202)
def analisar(lead_id: str):
    """Pede ao agente (worker Resumidor) um novo briefing + análise de sentimento/perfil. Assíncrono: o painel recarrega."""
    if not LeadRepository().get(lead_id):
        raise HTTPException(404)
    LeadRepository().marcar_analise_pedida(lead_id)
    get_broker().publish("resumir", json.dumps({"lead_id": lead_id}), key=lead_id)
    return {"lead_id": lead_id, "status": "solicitado"}


@router.post("/crm/sync", status_code=202)
def crm_sync():
    """Simula integração com CRM externo (diferencial): exporta leads qualificados/agendados."""
    leads = [l for l in LeadRepository().listar() if l.estagio in ("qualificado", "agendado", "handoff")]
    return {"exportados": len(leads), "destino": "crm-simulado",
            "payload": [{"id": l.id, "nome": l.nome, "telefone": l.telefone, "score": l.score, "estagio": l.estagio, "corretor_id": l.corretor_id} for l in leads]}
