---
title: Executando manualmente
description: Rodar o Mora sem Docker, processo a processo, para desenvolvimento. Inclui a CLI.
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

# Canal Telegram (opcional: entrada por long polling e saída)
cd services/channels/telegram && python -c "from canal_telegram.inbound import local_worker; local_worker()"
cd services/channels/telegram && python -c "from canal_telegram.outbound import local_worker; local_worker()"

# Front-ends
cd apps/web && npm run dev
cd apps/dashboard && npm run dev -- --port 5174
```

## CLI do agente

Uma alternativa via linha de comando, sem canais externos:

```bash
make cli                                  # conversa com a Mora no terminal (perfil local)
```

!!! info "Regras de dependência"
    Há uma imagem Python só (`local/Dockerfile.python`), construída **a partir da raiz do
    repositório** porque todos os serviços dependem de `shared/`. Veja
    [Estrutura do repositório](../technical-reference/estrutura.md).

!!! note "Não há deploy"
    A entrega roda inteira na máquina de quem avalia. As stacks CDK e os alvos `make synth` /
    `make deploy` foram removidos junto com a AWS; nada está implantado em servidor.
