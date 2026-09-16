---
title: Banco de dados
description: PostgreSQL + pgvector, schema, migrations e o mesmo esquema em local e AWS.
---

# Banco de dados

## Motor

**PostgreSQL com a extensão pgvector**, armazenando dados relacionais e vetores na mesma base:

- **Local** — container `pgvector/pgvector:pg16` (porta host 5433 → 5432).
- **AWS** — Aurora Serverless v2 (Postgres 16), que escala a zero quando ocioso (ADR-0004).

## Schema e migrations

O schema vive em `shared/sdr_shared/db/schema.sql` e é idempotente
(`CREATE`/`ALTER ... IF NOT EXISTS`).

```bash
# Perfil local: aplicado automaticamente ao subir o container db; para reaplicar:
make migrate

# Execução manual:
psql "$SDR_DATABASE_DSN" -f shared/sdr_shared/db/schema.sql
```

## Banco de testes

Os testes usam um banco separado, **`sdr_test`**. As suítes apagam tabelas e uma trava recusa rodar
contra um banco sem "test" no nome. Veja [Testes](../quality/testes.md).

## Tabelas de observabilidade

A observabilidade leve grava três tabelas no próprio Postgres — `turnos`, `saude` e `batimentos`
(ADR-0011). Veja [Observabilidade](../quality/observabilidade.md).

## Vetores e RAG

Os embeddings de imóveis (Titan v2 na AWS ou `bge-m3` local) ficam no pgvector e alimentam o RAG com
cascata por localidade. Reindexe com `make seed` após alterar bairros ou descrições. Veja
[Dados e persistência](../architecture/dados.md).

!!! info "Ingestão"
    `services/ingestion` carrega imóveis e gera embeddings. No local, `make seed` cria 200 imóveis
    determinísticos.
