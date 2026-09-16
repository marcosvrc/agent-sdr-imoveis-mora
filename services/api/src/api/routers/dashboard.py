from fastapi import APIRouter, Depends, Query
from sdr_shared.db import (LeadRepository, VisitaRepository, MensagemRepository, MetricasRepository,
                           resumo_de_turnos, resumo_reativacao, ultima_amostra, batimentos)
from ..auth import corretor_atual

router = APIRouter(dependencies=[Depends(corretor_atual)])


@router.get("/funil")
def funil():
    repo = LeadRepository()
    return {"estagios": repo.funil(), "temperaturas": repo.por_temperatura()}


@router.get("/visitas")
def visitas():
    return VisitaRepository().listar()


@router.get("/atividade")
def atividade():
    return MensagemRepository().recentes(50)


@router.get("/metricas")
def metricas(dias: int = Query(7, ge=1, le=90)):
    """KPIs do período com variação vs. período anterior, série diária, pipeline em R$ e distribuições."""
    return MetricasRepository().resumo(dias)


@router.get("/saude")
def saude(horas: int = Query(24, ge=1, le=168)):
    """Observabilidade leve (ADR-0011): o que o corretor precisa ver sem abrir um Grafana.

    Três leituras baratas do Postgres — espera do cliente por turno, última amostra de filas e
    quem está batendo ponto. Sem coletor, sem série temporal de métricas, sem agente extra."""
    return {"turnos": resumo_de_turnos(horas), "amostra": ultima_amostra(),
            "servicos": batimentos(), "horas": horas}


@router.get("/reativacao")
def reativacao(dias: int = Query(30, ge=1, le=180)):
    """Fase 4 do ADR-0013: o que o aviso de imóvel novo produziu.

    Janela padrão de 30 dias porque reativação é lenta por natureza — o lead sumiu semanas atrás e o
    imóvel certo aparece quando aparece; sete dias mostrariam quase sempre zero.
    """
    return resumo_reativacao(dias)
