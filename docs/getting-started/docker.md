---
title: Executando com Docker
description: Suba o Mora inteiro no perfil local com Docker Compose, popule o catálogo e encerre.
---

# Executando com Docker Compose

Este é o caminho recomendado. Sobe Postgres + pgvector, Redis, canais, API, agente, workers e os
front-ends de uma vez.

## Passo a passo

É a mesma ordem que `make` sozinho imprime (o alvo `ajuda`).

```bash
# 1. Clonar e entrar no diretório
git clone <url-do-repositorio>
cd agent-sdr-morai

# 2. Configurar o ambiente do perfil local
cp -n local/.env.example local/.env      # -n NÃO sobrescreve um .env que já existe
# preencha ANTHROPIC_API_KEY e CRM_MCP_TOKEN

# 3. Conferir o .env antes de subir nada
make check-env

# 4. Subir o compose (fica em primeiro plano; siga noutro terminal)
make local-ollama
# equivalente a: cd local && docker compose --profile ollama up --build
# sem o Ollama: make local

# 5. Bancos e massa do CRM, na ordem certa
make preparar

# 6. Emitir a credencial da Mora no CRM e colar CRM_API_TOKEN em local/.env
make crm-token
cd local && docker compose up -d crm-mcp agent     # releem o .env

# 7. Baixar o modelo de embeddings (demora, uma vez só)
make ollama-pull

# 8. Indexar acervo e documentos institucionais
make seed && make docs-kb

# Encerrar o ambiente
cd local && docker compose down          # use down -v para apagar também os volumes (Postgres/Ollama)
```

Sem CRM a Mora roda sozinha: pule os passos 5 e 6 e a parte de CRM — os alvos avisam.

O `make local` e o `make local-ollama` executam `scripts/check_env.py` antes de subir. O schema do
banco também é aplicado na inicialização do container `db` (`shared/sdr_shared/db/schema.sql`), mas
só quando o volume é novo; `make preparar` cuida do caso de um volume que já existia.

## Reaplicar schema e reindexar

```bash
make migrate      # (re)aplica o schema no Postgres do compose — idempotente
make seed         # recarrega imóveis e regenera embeddings
make docs-kb      # reindexa os documentos institucionais (make docs-secos lista sem indexar)
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
| Painel do CRM | <http://localhost:3000> | 3000 | — (Vite dev server) |
| API do CRM | <http://localhost:8100> | 8100 | `GET /health/ready` |
| Servidor MCP do CRM | <http://localhost:8200/mcp> | 8200 | `GET /saude` |
| Langfuse (opcional) | <http://localhost:3000> | 3000 | — |
| Postgres / Redis / Ollama | host: 5433 / 6380 / 11435 | — | `pg_isready` (db) |

!!! note "Portas deslocadas de propósito"
    As portas do host (5433, 6380, 11435) evitam colisão com instâncias nativas de Postgres, Redis e
    Ollama e podem ser ajustadas por `DB_HOST_PORT`, `REDIS_HOST_PORT` e `OLLAMA_HOST_PORT`.

!!! warning "O Langfuse disputa a porta 3000 com o painel do CRM"
    Os dois publicam 3000 e não sobem juntos. Com o profile `observability` ligado, um dos dois falha
    ao vincular a porta.

## LLM 100% local com Ollama

```bash
make local-ollama    # sobe o compose com o perfil ollama
make ollama-pull     # baixa o modelo de embeddings bge-m3
```

Depois de subir, siga para [Validando a instalação](validacao.md).
