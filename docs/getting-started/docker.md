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
cd local && docker compose down          # use down -v para apagar também os volumes (Postgres, Redis, Ollama, whisper-mora)
```

Sem CRM a Mora roda sozinha: pule os passos 5 e 6 e a parte de CRM — os alvos avisam.

O `make local` e o `make local-ollama` executam `scripts/check_env.py` antes de subir. O schema do
banco também é aplicado na inicialização do container `db` (`shared/sdr_shared/db/schema.sql`), mas
só quando o volume é novo; `make preparar` cuida do caso de um volume que já existia.

## Reaplicar schema e reindexar

```bash
make migrate      # (re)aplica o schema no Postgres do compose — idempotente
make seed         # recarrega imóveis e regenera embeddings
make corretores   # cria a equipe de 20 corretores e casa com os usuários do CRM
make docs-kb      # reindexa os documentos institucionais (make docs-secos lista sem indexar)
```

## O que recarrega sozinho, e o que não

O código é montado no container, então editar arquivo no host é o suficiente — **para os três
serviços que rodam com `--reload`**: `api`, `crm-api` e `channels`. Eles vigiam o próprio serviço e
também `/app/shared`, e o compose liga `WATCHFILES_FORCE_POLLING` neles: o `--reload` sozinho usa
inotify, e evento de inotify não atravessa bind mount de forma confiável no Docker Desktop do macOS
— o arquivo muda, o processo segue com o código antigo e nada avisa.

Os **workers não recarregam nunca**: `agent`, `scheduler`, `telegram-in`, `telegram-out`,
`resumidor` e `reativador` são processos Python comuns. Mudou o código deles, reinicie:

```bash
cd local && docker compose restart agent scheduler resumidor reativador telegram-in telegram-out
```

Mudança em variável de ambiente ou no próprio `docker-compose.yml` exige **recriar**, não reiniciar:

```bash
cd local && docker compose up -d
```

!!! warning "Variável nova num serviço Python: mescle o `x-pyenv`"
    O ambiente comum dos serviços Python fica no anchor `x-pyenv`, separado do `x-py`. Um
    `environment:` declarado dentro de um serviço **substitui** o mapa herdado por `<<: *py` — não
    mescla. Para acrescentar uma variável, mescle o anchor explicitamente, como faz a `api`
    (`environment: { <<: *pyenv, SDR_DB_POOL_MAX: "12" }`). Sem isso o serviço perde o
    `SDR_DATABASE_DSN` e só descobre na próxima recriação, com `PoolTimeout` no `/health`.

## Reinício automático e o que sobrevive a ele

Os serviços de longa duração sobem com `restart: unless-stopped`: um worker que cai por exceção
volta sozinho, em vez de ficar `Exited` com a fila crescendo. Duas exceções, de propósito:
`telegram-in` usa `on-failure` (sem `SDR_TELEGRAM_BOT_TOKEN` ele sai com status 0, e religá-lo seria
um laço de avisos) e `crm-mcp` usa `on-failure:5` (sem `CRM_MCP_TOKEN` ele recusa subir, e rodar sem
CRM é um modo suportado). `docker compose stop` continua parando tudo — `unless-stopped` respeita.

O Redis grava em AOF num volume próprio (`redis`): a fila entre os canais e o agente sobrevive a um
`restart` ou a um reinício do Docker Desktop. Antes, mensagem de cliente ainda não consumida se
perdia em silêncio.

## Usuário dos containers Python

A imagem de `local/Dockerfile.python` roda como o usuário `mora` (UID/GID 1000), não como root. No
Docker Desktop do Mac isso não muda nada para os bind mounts: o compartilhamento de arquivos grava
no disco como o usuário do Mac, qualquer que seja o UID do container. Num Linux cujo usuário não é o
1000, a API pode não conseguir gravar em `data/fotos`. Duas saídas:

```bash
# reconstruir a imagem com o seu UID (os arquivos gravados ficam seus)
cd local && docker compose build --build-arg UID=$(id -u) --build-arg GID=$(id -g) && docker compose up -d
# ou, sem rebuild, voltar a rodar como root: no local/.env
CONTAINER_USER=root
```

O cache do modelo de transcrição mora no volume `whisper-mora` (`HF_HOME=/home/mora/.cache/huggingface`).
O volume antigo, `whisper`, foi povoado pelo root e não serve ao usuário novo; pode ser apagado com
`docker volume rm sdr-local_whisper` — o modelo é baixado de novo na primeira transcrição (ou em
`make whisper-aquecer`).

Sinal de que o processo está velho: peça o `GET /openapi.json` e confira se uma mudança sua aparece
lá. Rota nova que responde `{"detail":"Not Found"}` é rota que não existe no processo em memória.

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
| Langfuse (opcional, sem integração) | <http://localhost:3001> | 3001 | — |
| Postgres / Redis / Ollama | host: 5433 / 6380 / 11435 | — | `pg_isready` (db) |

!!! note "Portas deslocadas de propósito"
    As portas do host (5433, 6380, 11435) evitam colisão com instâncias nativas de Postgres, Redis e
    Ollama e podem ser ajustadas por `DB_HOST_PORT`, `REDIS_HOST_PORT` e `OLLAMA_HOST_PORT`.

!!! note "Langfuse: só um ponto de partida"
    Nenhum código do projeto envia trace ao Langfuse hoje — não há SDK instalado nem chave
    configurada. O serviço sobe só com `--profile observability`, na porta 3001 (a 3000 é do painel do
    CRM; `LANGFUSE_HOST_PORT` muda) e só no loopback. Quem for integrá-lo define
    `LANGFUSE_NEXTAUTH_SECRET` e `LANGFUSE_SALT` no `local/.env`; os padrões são de desenvolvimento.

## Acesso de outro aparelho da rede

Toda porta do compose é publicada só em `127.0.0.1`. Sem isso o Docker publica em `0.0.0.0`, e no
Docker Desktop isso fura o firewall do Mac: qualquer um no mesmo Wi-Fi chegaria à API com o
`dev-token`, que é público. Para abrir de propósito — testar o site no celular, por exemplo:

1. Defina um `SDR_PAINEL_TOKEN` forte no `local/.env` (vazio, no perfil local, vale o `dev-token`).
2. No mesmo arquivo, `HOST_BIND=0.0.0.0`, e aplique com `cd local && docker compose up -d`.
3. Lembre que os front-ends falam com a API por `localhost` (`VITE_API_URL`, `VITE_WS_URL` no
   compose) e que o CORS da API só aceita as origens locais: no celular, o site abre, mas o chat e
   o catálogo só funcionam com essas URLs e `SDR_CORS_ORIGINS` apontando para o IP da máquina — as
   `VITE_*` estão fixas no `environment` dos serviços `web` e `dashboard`, então isso é edição no
   `docker-compose.yml`, não no `.env`.

`HOST_BIND` vale para API, canais, CRM e os três Vite. Postgres, Redis, Ollama e Langfuse ficam no
loopback sempre — dois deles não têm senha nenhuma. Volte a `127.0.0.1` (ou apague a linha) quando
terminar.

## LLM 100% local com Ollama

```bash
make local-ollama    # sobe o compose com o perfil ollama
make ollama-pull     # baixa o modelo de embeddings bge-m3
```

Depois de subir, siga para [Validando a instalação](validacao.md).
