"""Consulta da trilha de auditoria."""
import csv
import io
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sdr_shared.db import AuditoriaRepository, SENSIVEIS, auditar
from ..auth import corretor_atual

router = APIRouter(dependencies=[Depends(corretor_atual)])

# Planilha trata célula que começa com estes caracteres como fórmula. Vários campos da trilha vêm de
# fora (o id da entidade sai do caminho da URL, o nome do ator e os dados do corpo enviado): um
# `=HYPERLINK(...)` gravado ali virava um link ou comando ativo no Excel de quem abrisse a exportação.
_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _celula(valor) -> str:
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto.startswith(_FORMULA) else texto


@router.get("")
def listar(dias: int = Query(30, ge=1, le=365), ator: str | None = None, acao: str | None = None,
           entidade: str | None = None, entidade_id: str | None = None, busca: str | None = None,
           so_sensiveis: bool = False, limite: int = Query(300, ge=1, le=1000)):
    repo = AuditoriaRepository()
    return {"registros": repo.listar(dias=dias, ator=ator, acao=acao, entidade=entidade,
                                     entidade_id=entidade_id, busca=busca, so_sensiveis=so_sensiveis, limite=limite),
            "resumo": repo.resumo(dias), "acoes_sensiveis": sorted(SENSIVEIS)}


@router.get("/exportar")
def exportar(dias: int = Query(30, ge=1, le=365), acao: str | None = None, entidade: str | None = None,
             ator: dict = Depends(corretor_atual)):
    """CSV do período — para enviar a quem pediu a prestação de contas."""
    registros = AuditoriaRepository().listar(dias=dias, acao=acao, entidade=entidade, limite=5000)
    auditar(acao="auditoria.exportada", entidade="auditoria", ator_tipo="corretor",
            ator_id=ator.get("id"), ator_nome=ator.get("email"),
            dados={"dias": dias, "acao": acao, "entidade": entidade, "linhas": len(registros)})
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["quando", "ator_tipo", "ator", "acao", "entidade", "entidade_id", "resultado", "origem", "dados"])
    for r in registros:
        w.writerow([_celula(c) for c in (
            r["em"], r["ator_tipo"], r["ator_nome"] or r["ator_id"] or "", r["acao"], r["entidade"],
            r["entidade_id"] or "", r["resultado"], r["origem"] or "", json.dumps(r["dados"], ensure_ascii=False))])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="auditoria-{dias}d.csv"'})
