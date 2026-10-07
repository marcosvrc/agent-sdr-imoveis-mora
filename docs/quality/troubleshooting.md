---
title: Troubleshooting
description: Problemas comuns do Mora no perfil local e como resolvê-los.
---

# Troubleshooting

| Problema | Possível causa | Solução |
|---|---|---|
| `docker compose ps` mostra `channels` como `unhealthy` | Redis fora do ar | Verifique o container `redis`; o `/health` do canal devolve 503 sem Redis |
| Chat do site "sem conexão" | Canais (`:8001`) ou WebSocket indisponível | Confira `docker compose logs -f channels` e a variável `VITE_WS_URL` |
| Catálogo vazio no site | Seed não executado | Rode `make seed` |
| `PoolTimeout` no `/health` da API e catálogo vazio, logo depois de recriar containers | Um serviço declarou `environment:` próprio e perdeu o mapa herdado de `<<: *py` (o YAML substitui, não mescla) — o DSN some e o processo procura o banco em `localhost:5432` | Em `local/docker-compose.yml`, acrescente variáveis mesclando o anchor `x-pyenv` explicitamente, como faz a `api` (`environment: { <<: *pyenv, … }`) |
| Recarreguei o site e a conversa começou do zero | `SDR_CHAT_NOVA_CONVERSA=true` no `local/.env` (modo de teste), ou aba anônima/fechada | Ponha `false` e rode `cd local && docker compose up -d web`; com o modo desligado, a conversa é redesenhada pelo `POST /historico` |
| Aba Saúde: "scheduler sem dar sinal há …" | O processo do scheduler caiu ou travou | Hoje um ciclo com erro (ex.: banco reiniciando) é registrado e o laço segue; se o batimento parou, veja `docker compose logs scheduler` e reinicie o serviço |
| **Mudei o código (ou as fotos do acervo) e nada mudou na tela** | O processo no container é o de antes. O `--reload` do uvicorn depende de inotify, que não atravessa bind mount de forma confiável no Docker Desktop do macOS | `cd local && docker compose up -d api crm-api channels` (recria com `WATCHFILES_FORCE_POLLING`). Os **workers** (`agent`, `scheduler`, `telegram-*`, `resumidor`, `reativador`) não recarregam nunca — mudou o código deles, reinicie-os |
| Foto de imóvel some (quadro cinza no card) | A rota `/acervo/...` não existe no processo em memória — resposta é o 404 padrão, `{"detail":"Not Found"}` | Mesmo caso acima: recrie a `api`. Para confirmar, `curl -s localhost:8000/openapi.json \| grep -o '"maximum":[0-9]*'` — se o `limite` de `/imoveis` ainda diz 200, o processo é velho |
| Agente responde fallback sempre | LLM inacessível, credenciais ou timeout | Confira `SDR_LLM_PROVIDER` / credenciais e `SDR_LLM_TIMEOUT_S`; veja os logs do `agent` |
| Painel retorna 401 | Token ausente / incorreto | Envie `Authorization: Bearer <SDR_PAINEL_TOKEN>` (ou `dev-token` no local) |
| Porta 5432 / 6379 / 11434 ocupada | Instância nativa em conflito | Ajuste `DB_HOST_PORT` / `REDIS_HOST_PORT` / `OLLAMA_HOST_PORT` |
| Resultados de busca "errados" após editar bairros | Embeddings desatualizados | Reindexe com `make seed` |
| `make test` recusa rodar | Banco sem "test" no nome | Use o `sdr_test`; em último caso `SDR_TEST_ALLOW_WIPE=1` |
| `crm-api` em laço: `FATAL: database "crm" does not exist` | Volume do Postgres criado antes de o CRM entrar no projeto: os scripts de `docker-entrypoint-initdb.d` só rodam em volume novo | Suba de novo — o serviço `db-init` do compose cria o banco antes de qualquer serviço Python. Com o ambiente já no ar: `make crm-migrate && cd local && docker compose up -d crm-api` |
| `relation "<tabela>" does not exist` logo após um `git pull` | Schema novo, volume antigo | `make migrate` (banco da Mora) ou `make crm-migrate` (CRM); os dois são idempotentes |
| `expected 1024 dimensions` ao indexar | Provedor de embeddings trocado sem reindexar, ou `SDR_EMBEDDINGS_DIMENSOES` fora do schema | Volte o provedor ou rode `make seed` e `make docs-kb` inteiros — vetor de modelo diferente não se compara |
| Busca traz imóvel errado depois de trocar o provedor de embeddings | Índice com vetores de dois modelos misturados | Reindexe tudo: `make seed && make docs-kb`. Não há migração parcial |

## Onde olhar

- **Logs por serviço:** `docker compose logs -f <serviço>` (JSON estruturado).
- **Saúde:** `GET /health` na API e nos canais.
- **Consumo de IA:** aba de Governança do painel.

Se o problema persistir, veja [Observabilidade](observabilidade.md) e
[Configuração](../getting-started/configuracao.md).
