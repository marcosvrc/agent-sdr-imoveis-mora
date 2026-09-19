---
title: Executando com Docker
description: Suba o Mora inteiro no perfil local com Docker Compose, popule o catálogo e encerre.
---

# Executando com Docker Compose

Este é o caminho recomendado. Sobe Postgres + pgvector, Redis, canais, API, agente, workers e os
front-ends de uma vez.

## Passo a passo

```bash
# 1. Clonar e entrar no diretório
git clone <url-do-repositorio>
cd agent-sdr-morai

# 2. Configurar o ambiente do perfil local
cp -n local/.env.example local/.env
# edite local/.env: escolha o provedor de LLM e, se for usar o canal externo, o token do Telegram

# 3. Subir tudo
#    --profile ollama       → LLM local
#    --profile observability → Langfuse (tracing de LLM)
make local
# equivalente a: cd local && docker compose up --build

# 4. Popular o catálogo (200 imóveis determinísticos + embeddings)
make seed

# 5. Encerrar o ambiente
cd local && docker compose down          # use down -v para apagar também os volumes (Postgres/Ollama)
```

O `make local` executa `scripts/check_env.py` antes de subir. O schema do banco é aplicado
automaticamente na inicialização do container `db` (`shared/sdr_shared/db/schema.sql`).

## Reaplicar schema e reindexar

```bash
make migrate      # (re)aplica o schema no Postgres do compose — idempotente
make seed         # recarrega imóveis e regenera embeddings
```

## Serviços e portas (perfil local)

| Serviço | URL local | Porta | Health check |
|---|---|---:|---|
| Site (PWA) | <http://localhost:5173> | 5173 | — (Vite dev server) |
| Painel | <http://localhost:5174> | 5174 | — (Vite dev server) |
| API | <http://localhost:8000> | 8000 | `GET /health` (503 quando degradado) |
| API (OpenAPI) | <http://localhost:8000/docs> | 8000 | — |
| Canais (HTTP / WS) | <http://localhost:8001> · `ws://localhost:8001/ws` | 8001 | `GET /health` (503 se o Redis cair) |
| Agente | worker (sem HTTP) | — | via tabela de saúde no Postgres (ADR-0011) |
| Langfuse (opcional) | <http://localhost:3000> | 3000 | — |
| Postgres / Redis / Ollama | host: 5433 / 6380 / 11435 | — | `pg_isready` (db) |

!!! note "Portas deslocadas de propósito"
    As portas do host (5433, 6380, 11435) evitam colisão com instâncias nativas de Postgres, Redis e
    Ollama e podem ser ajustadas por `DB_HOST_PORT`, `REDIS_HOST_PORT` e `OLLAMA_HOST_PORT`.

## LLM 100% local com Ollama

```bash
make local-ollama    # sobe o compose com o perfil ollama
make ollama-pull     # baixa o modelo de embeddings bge-m3
```

Depois de subir, siga para [Validando a instalação](validacao.md).
