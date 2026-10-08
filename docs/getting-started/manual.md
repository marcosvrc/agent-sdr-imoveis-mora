---
title: Executando manualmente
description: Rodar o Mora sem Docker, processo a processo, para desenvolvimento. Inclui a CLI.
---

# Executando manualmente (desenvolvimento)

Requer um Postgres 16 com pgvector, um Redis e Python 3.12. Os comandos espelham o
`local/docker-compose.yml`, que é a referência quando os dois divergirem.

## Preparar

```bash
make setup        # instala serviços (uv/pip) e os três front-ends (npm)
```

O jeito mais simples de ter Postgres e Redis é subir só a infraestrutura do compose. O serviço
`db-init` cria os bancos `sdr`, `crm` e `langfuse` e aplica os dois schemas:

```bash
cd local && docker compose up -d db db-init redis && cd ..
# publicados no host em 127.0.0.1:5433 (Postgres) e 127.0.0.1:6380 (Redis)
```

Com um Postgres próprio, aplique os schemas à mão (os dois são idempotentes):

```bash
psql "$SDR_DATABASE_DSN" -f shared/sdr_shared/db/schema.sql
psql "postgresql://sdr:sdr@localhost:5432/crm" -f services/crm/sdr_crm/db/schema.sql   # se for usar o CRM
```

## Carregar o ambiente (em todo terminal)

!!! warning "O processo não lê o `local/.env` sozinho"
    A configuração da Mora procura um `.env` **no diretório em que o processo roda** (por exemplo
    `services/api/src/.env`), e algumas chaves — `OPENAI_API_KEY`, `SDR_CRM_URL`, `SDR_CRM_TOKEN` —
    são lidas direto do ambiente. Sem exportar, o processo sobe com os padrões (Postgres em
    `localhost:5432`, Redis em `localhost:6379`) e sem chave nenhuma, e só falha no primeiro turno.

```bash
set -a; source local/.env; set +a
# o local/.env aponta para os nomes do compose (db, redis, ollama); no host, sobrescreva:
export SDR_PROFILE=local
export SDR_DATABASE_DSN=postgresql://sdr:sdr@localhost:5433/sdr
export SDR_REDIS_URL=redis://localhost:6380/0
export SDR_OLLAMA_URL=http://localhost:11435        # só com o perfil ollama
export SDR_CRM_URL=http://localhost:8200/mcp SDR_CRM_TOKEN="$CRM_MCP_TOKEN"   # só com o CRM
```

Valores com espaço ou JSON (como `CRM_ALLOWED_ORIGINS`) precisam estar entre aspas no `.env` para o
`source` funcionar. Com `uv`, rode cada comando com `uv run` a partir da pasta do serviço, ou ative o
`.venv` dele.

## Subir cada processo (um terminal por serviço)

```bash
# API REST (painel e site) — porta 8000
cd services/api/src && uvicorn api.main:app --port 8000 --reload

# Canais (HTTP + WebSocket do chat do site) — porta 8001
cd services/channels/local && uvicorn app:app --port 8001 --reload

# Agente (worker do turno)
cd services/agent/src && python -c "from agent.handler import local_worker; local_worker()"

# Resumo do lead fora do turno (tópico `resumir`)
cd services/agent/src && python -c "from agent.eventos import local_worker; local_worker()"

# Reativação de leads quando entra imóvel novo (tópico `imovel-novo`)
cd services/agent/src && python -c "from agent.reativador import local_worker; local_worker()"

# Scheduler: follow-up, amostra de saúde, drenagem do CRM e refresh do acervo.
# Sem ele não há follow-up nem publicação no CRM.
cd services/scheduler && python -m sdr_scheduler.local_worker

# Canal Telegram (opcional: entrada por long polling e saída)
cd services/channels/telegram && python -c "from canal_telegram.inbound import local_worker; local_worker()"
cd services/channels/telegram && python -c "from canal_telegram.outbound import local_worker; local_worker()"

# Front-ends
cd apps/web && npm run dev                          # 5173
cd apps/dashboard && npm run dev -- --port 5174
```

### CRM (opcional)

O CRM é um sistema à parte, com ambiente próprio: **não** carregue o `local/.env` nesses terminais.

```bash
# API do CRM — porta 8100
cd services/crm && CRM_DATABASE_DSN=postgresql://sdr:sdr@localhost:5433/crm \
  uvicorn sdr_crm.api.main:app --port 8100 --reload

# Servidor MCP por HTTP — porta 8200 (é por ele que a Mora entra)
cd services/crm && CRM_API_BASE_URL=http://localhost:8100 CRM_API_TOKEN=<token da Mora> \
  CRM_MCP_TOKEN=<o mesmo do local/.env> python -m sdr_crm.mcp --http --porta 8200

# Painel do CRM — porta 3000
cd apps/crm && npm run dev -- --port 3000
```

O token da Mora no CRM sai de `python -m sdr_crm.credenciais emitir --nome mora`, rodado em
`services/crm` com o mesmo `CRM_DATABASE_DSN`.

## CLI do agente

Uma alternativa via linha de comando, sem canais externos:

```bash
set -a; source local/.env; set +a      # e os exports da seção acima
make cli                                # conversa com a Mora no terminal (perfil local)
```

O `make cli` roda `python cli.py` em `services/agent` e confere o `local/.env` antes (`check-env`),
mas o processo **não** o lê: sem os exports, a CLI usa os padrões.

!!! info "Regras de dependência"
    Há uma imagem Python só (`local/Dockerfile.python`), construída **a partir da raiz do
    repositório** porque todos os serviços dependem de `shared/`. Veja
    [Estrutura do repositório](../technical-reference/estrutura.md).

!!! note "Não há deploy"
    A entrega roda inteira na máquina de quem avalia. As stacks CDK e os alvos `make synth` /
    `make deploy` foram removidos junto com a AWS; nada está implantado em servidor.
