"""Governança de LLM: consumo de tokens, custos, limites de orçamento e tabela de preços."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sdr_shared.config import get_settings
from sdr_shared.db import UsoRepository, estado_do_orcamento, invalidar_cache_orcamento, LIMITES_PADRAO
from sdr_shared.governanca import PRECOS_PADRAO
from ..auth import corretor_atual

router = APIRouter(dependencies=[Depends(corretor_atual)])


@router.get("/uso")
def uso(dias: int = Query(30, ge=1, le=180)):
    """Consumo do período com variação, série diária, quebra por modelo/nó/papel e chamadas recentes."""
    s = get_settings()
    return {**UsoRepository().resumo(dias), "orcamento": estado_do_orcamento(cache_segundos=0),
            "configuracao_atual": {"provider": s.llm_provider, "modelo_conversa": s.model_conversa,
                                   "modelo_roteamento": s.model_roteamento, "embeddings": s.embeddings_provider}}


class LimitesIn(BaseModel):
    orcamento_mensal_usd: float = Field(ge=0)
    teto_tokens_dia: int = Field(ge=0)
    alerta_pct: int = Field(ge=1, le=100)
    acao_ao_estourar: str = Field(pattern="^(degradar|alertar|bloquear)$")
    cotacao_brl: float = Field(gt=0, le=100)


@router.get("/limites")
def limites():
    return {"limites": UsoRepository().limites(), "defaults": LIMITES_PADRAO, "estado": estado_do_orcamento(cache_segundos=0)}


@router.put("/limites")
def salvar_limites(body: LimitesIn):
    valor = UsoRepository().salvar_limites(body.model_dump())
    invalidar_cache_orcamento()                       # o agente passa a valer-se do novo limite na hora
    return {"limites": valor, "estado": estado_do_orcamento(cache_segundos=0)}


@router.get("/precos")
def precos():
    """Preços por 1M de tokens: (entrada, saída, escrita de cache, leitura de cache) em USD."""
    salvos = UsoRepository().precos()
    return {"precos": {**PRECOS_PADRAO, **salvos}, "defaults": PRECOS_PADRAO, "personalizados": list(salvos)}


class PrecoIn(BaseModel):
    entrada: float = Field(ge=0)
    saida: float = Field(ge=0)
    cache_escrita: float = Field(ge=0, default=0)
    cache_leitura: float = Field(ge=0, default=0)


@router.put("/precos/{modelo}")
def salvar_preco(modelo: str, body: PrecoIn):
    if not modelo.strip():
        raise HTTPException(422, "modelo inválido")
    repo = UsoRepository()
    salvos = {**repo.precos(), modelo: [body.entrada, body.saida, body.cache_escrita, body.cache_leitura]}
    repo.salvar_precos(salvos)
    return {"modelo": modelo, "preco": salvos[modelo]}


@router.delete("/precos/{modelo}", status_code=204)
def restaurar_preco(modelo: str):
    repo = UsoRepository()
    salvos = repo.precos()
    salvos.pop(modelo, None)
    repo.salvar_precos(salvos)
