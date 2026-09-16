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
| Agente responde fallback sempre | LLM inacessível, credenciais ou timeout | Confira `SDR_LLM_PROVIDER` / credenciais e `SDR_LLM_TIMEOUT_S`; veja os logs do `agent` |
| Painel retorna 401 | Token ausente / incorreto | Envie `Authorization: Bearer <SDR_PAINEL_TOKEN>` (ou `dev-token` no local) |
| Porta 5432 / 6379 / 11434 ocupada | Instância nativa em conflito | Ajuste `DB_HOST_PORT` / `REDIS_HOST_PORT` / `OLLAMA_HOST_PORT` |
| Resultados de busca "errados" após editar bairros | Embeddings desatualizados | Reindexe com `make seed` |
| `make test` recusa rodar | Banco sem "test" no nome | Use o `sdr_test`; em último caso `SDR_TEST_ALLOW_WIPE=1` |

## Onde olhar

- **Logs por serviço:** `docker compose logs -f <serviço>` (JSON estruturado).
- **Saúde:** `GET /health` na API e nos canais.
- **Consumo de IA:** aba de Governança do painel.

Se o problema persistir, veja [Observabilidade](observabilidade.md) e
[Configuração](../getting-started/configuracao.md).
