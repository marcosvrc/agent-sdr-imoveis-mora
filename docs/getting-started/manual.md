---
title: Executando manualmente
description: Rodar o Mora sem Docker, processo a processo, para desenvolvimento. Inclui a CLI e o deploy AWS.
---

# Executando manualmente (desenvolvimento)

Requer um Postgres com pgvector acessível e Python 3.12. Os comandos espelham o `docker-compose.yml`.

## Preparar

```bash
make setup                                # instala serviços (uv/pip) e front-ends (npm)
psql "$SDR_DATABASE_DSN" -f shared/sdr_shared/db/schema.sql
```

## Subir cada processo (um terminal por serviço)

```bash
# API REST
cd services/api/src && uvicorn api.main:app --port 8000 --reload

# Canais (HTTP + WebSocket)
cd services/channels/local && uvicorn app:app --port 8001 --reload

# Agente (worker)
cd services/agent/src && python -c "from agent.handler import local_worker; local_worker()"

# Front-ends
cd apps/web && npm run dev
cd apps/dashboard && npm run dev -- --port 5174
```

## CLI do agente

Uma alternativa via linha de comando, sem canais externos:

```bash
make cli                                  # conversa com a Mora no terminal (perfil local)
```

## Deploy AWS (referência)

```bash
make deploy ENV=dev                       # build dos front-ends + cdk deploy --all (perfil aws)
```

!!! info "Regras de dependência"
    As imagens Docker são construídas **a partir da raiz do repositório** porque dependem de `shared/`:
    `docker build -f services/<serviço>/Dockerfile .`. Veja
    [Estrutura do repositório](../technical-reference/estrutura.md).
