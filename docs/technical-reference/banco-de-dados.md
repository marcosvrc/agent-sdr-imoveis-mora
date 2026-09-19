---
title: Banco de dados
description: PostgreSQL + pgvector, schema, migrations e o banco único que atende dados e vetores.
---

# Banco de dados

## Motor

**PostgreSQL com a extensão pgvector**, armazenando dados relacionais e vetores na mesma base
(ADR-0004): container `pgvector/pgvector:pg16` do `local/docker-compose.yml`, porta host 5433 → 5432
(ajustável por `DB_HOST_PORT`).

Há um servidor só, o do compose. Não existe variante gerenciada: o que havia de banco hospedado saiu
do projeto junto com a infraestrutura em nuvem. Dentro dele, o CRM tem **banco próprio** (`crm`),
separado do `sdr` — é o que faz a regra de que nada da Mora escreve direto no CRM ser estrutural, e
não só combinada (ver [decisões](../decisions.md) D-02).

## Schema e migrations

O schema vive em `shared/sdr_shared/db/schema.sql` e é idempotente
(`CREATE`/`ALTER ... IF NOT EXISTS`).

```bash
# Aplicado automaticamente na PRIMEIRA subida do container db (initdb.d); para reaplicar:
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

Os embeddings ficam no pgvector, em duas tabelas: `imoveis.embedding` (catálogo, com cascata por
localidade) e `documentos.embedding` (documentos institucionais fatiados, com a coluna gerada `busca`
em `tsvector` para a fusão léxica). Ambas são `vector(1024)` — a dimensão do `bge-m3`, o único modelo
de embeddings do projeto, servido pelo Ollama. Reindexe o catálogo com `make seed` após alterar
bairros ou descrições, e os documentos com `make docs-kb`. Veja
[Dados e persistência](../architecture/dados.md).

!!! info "Ingestão"
    `services/ingestion` carrega imóveis e gera embeddings. No local, `make seed` cria 200 imóveis
    determinísticos.
