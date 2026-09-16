"""Simulação da reativação proativa (modo seco).

Responde "se este imóvel tivesse acabado de entrar, quem a Mora avisaria — e por quê". Não envia
nada: é a fase em que se descobre que a régua está errada olhando a lista, e não depois de escrever
para trinta pessoas.

O envio de verdade virá de um worker consumindo o evento de imóvel novo, com cadência, orçamento e
os guardrails do agente. Esta rota é a mesma função de casamento, exposta para inspeção.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sdr_shared.db import ImovelRepository, InteresseRepository, LeadRepository
from sdr_shared.reativacao import avaliar
from ..auth import corretor_atual

router = APIRouter(dependencies=[Depends(corretor_atual)])

# Teto de leads varridos por simulação. A POC tem centenas; um catálogo real tem milhares, e a
# varredura completa é trabalho do worker (em lote), não de uma rota que alguém abre no painel.
MAX_LEADS = 500


@router.get("/imovel/{imovel_id}")
def simular(imovel_id: str, limite: int = Query(20, ge=1, le=50)):
    """Quem seria avisado sobre este imóvel, ordenado por aderência.

    Cada candidato vem com os motivos em português — são eles que viram a primeira frase da
    mensagem. Os excluídos vêm com o motivo da exclusão, que é o que permite calibrar a régua.
    """
    im = ImovelRepository().get(imovel_id)
    if not im:
        raise HTTPException(404, "imóvel não encontrado")

    leads = LeadRepository().listar(limite=MAX_LEADS)
    conhecidos = {l.id: InteresseRepository().por_situacao(l.id) for l in leads}
    return avaliar(im, leads, conhecidos, limite=limite)
