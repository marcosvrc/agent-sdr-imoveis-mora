"""Avisos do corretor. O painel pergunta; o agente escreve (sdr_shared/db/notificacoes.py)."""
from fastapi import APIRouter, Depends, Query
from sdr_shared.db import NotificacaoRepository
from ..auth import corretor_atual

router = APIRouter(dependencies=[Depends(corretor_atual)])


def _quem(ator: dict) -> str | None:
    """No perfil local há um login único que representa a equipe: vê os avisos de todos.
    Com autenticação por corretor, cada um veria os seus (mais os sem dono)."""
    ident = ator.get("id")
    return None if ident == "corretor-dev" else ident


@router.get("")
def listar(apenas_nao_lidas: bool = False, limite: int = Query(50, le=200),
           ator: dict = Depends(corretor_atual)):
    repo, quem = NotificacaoRepository(), _quem(ator)
    return {"notificacoes": repo.listar(quem, apenas_nao_lidas, limite), "nao_lidas": repo.nao_lidas(quem)}


@router.post("/{notificacao_id}/lida", status_code=204)
def marcar_lida(notificacao_id: int, ator: dict = Depends(corretor_atual)):
    NotificacaoRepository().marcar_lida(notificacao_id, _quem(ator))


@router.post("/lidas")
def marcar_todas(ator: dict = Depends(corretor_atual)):
    return {"marcadas": NotificacaoRepository().marcar_todas(_quem(ator))}
