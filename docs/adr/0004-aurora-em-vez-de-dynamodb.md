# ADR-0004 — Aurora Serverless v2 (Postgres) em vez de DynamoDB

**Status:** aceito · **Data:** 2026-09-08

## Decisão
Aurora Serverless v2 com pgvector, escala a 0 ACU quando ocioso.

## Motivos
Dashboard exige funil, filtros e agregações (SQL); pgvector unifica RAG e dados transacionais;
checkpointer do LangGraph tem suporte nativo a Postgres. DynamoDB seria "mais serverless" mas
tornaria o dashboard e o RAG mais custosos de implementar numa semana.
