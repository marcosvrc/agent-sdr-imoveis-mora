# ADR-0002 — Runtime do agente: Lambda (container) consumindo SQS

**Status:** aceito · **Data:** 2026-09-08

## Contexto
Um turno multiagente faz 2–5 chamadas ao Bedrock (20–40 s). Lambda tem limite de 15 min e cold start
de alguns segundos para container Python + LangGraph.

## Decisão
Lambda container (Python 3.12, arm64) com event source SQS (batch 1, visibility 120 s).
Provisioned concurrency = 1 no ambiente de demo para eliminar cold start.

## Alternativas
- ECS Fargate: sem cold start, mas custo fixo e mais infra. Fica como fallback: o handler
  `agent/handler.py` é um consumidor SQS puro e roda igual em um container Fargate.
- Bedrock AgentCore Runtime: avaliar disponibilidade na região; se GA e compatível com LangGraph,
  é o caminho "mais nativo" e diferencial de inovação.
