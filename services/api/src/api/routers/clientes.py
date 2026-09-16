"""Cliente = a pessoa. A ficha reúne todas as oportunidades dela, em todos os canais."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sdr_shared.db import ClienteRepository
from ..auth import corretor_atual

router = APIRouter(dependencies=[Depends(corretor_atual)])


@router.get("")
def listar(busca: str | None = None, limite: int = Query(200, le=500)):
    return ClienteRepository().listar(busca=busca, limite=limite)


@router.get("/{cliente_id}")
def ficha(cliente_id: str):
    ficha = ClienteRepository().ficha(cliente_id)
    if not ficha:
        raise HTTPException(404)
    return ficha
