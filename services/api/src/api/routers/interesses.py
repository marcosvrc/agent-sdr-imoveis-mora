"""Interesse: que imóvel importa para qual lead.

Duas leituras que o corretor não tinha: o que já foi mostrado a um lead (e em que pé está) e quem
está de olho num imóvel. E uma escrita: corrigir a situação quando o cliente diz, na ligação, que
aquele apartamento não serve — é o que impede a Mora de reoferecê-lo na próxima conversa.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sdr_shared.db import ImovelRepository, InteresseRepository, LeadRepository
from ..auth import corretor_atual

router = APIRouter(dependencies=[Depends(corretor_atual)])


class SituacaoIn(BaseModel):
    situacao: str

    @field_validator("situacao")
    @classmethod
    def _valida(cls, v: str) -> str:
        if v not in InteresseRepository.SITUACOES:
            raise ValueError(f"situação inválida; use uma de {list(InteresseRepository.SITUACOES)}")
        return v


@router.get("/lead/{lead_id}")
def do_lead(lead_id: str):
    """Imóveis que passaram pela conversa deste lead, do mais recente para o mais antigo."""
    if not LeadRepository().get(lead_id):
        raise HTTPException(404, "lead não encontrado")
    return InteresseRepository().do_lead(lead_id)


@router.get("/imovel/{imovel_id}")
def do_imovel(imovel_id: str):
    """Quem está de olho neste imóvel, do lead mais quente para o mais frio.

    Descartados ficam de fora — a pergunta é com quem falar, não quem já disse não."""
    if not ImovelRepository().get(imovel_id):
        raise HTTPException(404, "imóvel não encontrado")
    return InteresseRepository().interessados(imovel_id)


@router.put("/{lead_id}/{imovel_id}")
def atualizar(lead_id: str, imovel_id: str, body: SituacaoIn):
    """Corrige a situação do interesse — tipicamente marcar `descartado` depois de falar com o cliente.

    `sugerido` é recusado de propósito: rebaixar um interesse declarado para "só mostrei" apagaria
    informação. Para desfazer um descarte, marque `interessado`.
    """
    if body.situacao == "sugerido":
        raise HTTPException(422, "`sugerido` é registrado pelo agente; use interessado, descartado ou visita_marcada")
    if not LeadRepository().get(lead_id):
        raise HTTPException(404, "lead não encontrado")
    if not ImovelRepository().get(imovel_id):
        raise HTTPException(404, "imóvel não encontrado")
    repo = InteresseRepository()
    repo.registrar(lead_id, imovel_id, situacao=body.situacao, origem="corretor")
    # O CRM é o registro comercial: um descarte que o corretor anota aqui e não aparece lá faz os
    # dois painéis discordarem sobre o mesmo imóvel, justamente na ficha que alguém vai ler antes
    # de ligar. Best-effort — a correção local já foi gravada e vale por si.
    from sdr_shared.crm import publicar_interesses
    lead = LeadRepository().get(lead_id)
    if lead:
        publicar_interesses(lead, [(imovel_id, body.situacao)])
    return next((i for i in repo.do_lead(lead_id) if i["imovel_id"] == imovel_id), None)
