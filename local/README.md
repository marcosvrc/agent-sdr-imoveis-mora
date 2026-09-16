# Perfil local

```bash
cd local && cp .env.example .env         # preencha o provedor de LLM e as credenciais da Meta
docker compose up --build                # + `--profile ollama` para LLM local, `--profile observability` para Langfuse
docker compose logs -f tunnel            # copie a URL https://xxxx.trycloudflare.com
# Meta for Developers → WhatsApp → Configuration → Webhook: https://xxxx.trycloudflare.com/webhook, token = SDR_WHATSAPP_VERIFY_TOKEN
docker compose exec agent python /app/scripts/gerar_imoveis.py 200   # 200 imóveis determinísticos
docker compose exec -w /app/services/ingestion agent python -m sdr_ingestion.ingest_imoveis /app/data/imoveis/imoveis.json
```

| URL | Serviço |
|---|---|
| http://localhost:5173 | Site vitrine (PWA) |
| http://localhost:5174 | Dashboard do corretor |
| http://localhost:8000/docs | API (OpenAPI) |
| ws://localhost:8001/ws | WebSocket do chat |
| http://localhost:3000 | Langfuse (opcional) |
| localhost:5433 / :6380 / :11435 | Postgres, Redis e Ollama do compose, vistos do host (`DB_HOST_PORT`, `REDIS_HOST_PORT`, `OLLAMA_HOST_PORT` no `.env`) |

Se usar Ollama: `docker compose exec ollama ollama pull llama3.1:8b && ollama pull bge-m3`.
Com Ollama, os embeddings têm 1024 dims (bge-m3) — mesma coluna `vector(1024)`; com nomic-embed-text (768) ajuste o schema.

## O que muda em relação à AWS (e o que NÃO muda)

| Peça | AWS | Local | Onde está a troca |
|---|---|---|---|
| Fila | SQS FIFO | Redis Streams | `shared/adapters/{aws,local}/broker.py` |
| Follow-up | EventBridge Scheduler | tabela + worker polling | `shared/adapters/{aws,local}/scheduler.py` |
| Embeddings | Titan v2 | Titan v2 (API) ou Ollama | `shared/adapters/{aws,local}/embeddings.py` |
| LLM | Bedrock | Bedrock / Anthropic API / Ollama | `shared/ports/factory.py` |
| RAG | Knowledge Base | pgvector direto (Caminho B) | `SDR_KNOWLEDGE_BASE_ID` vazio |
| Entrada HTTP/WS | API Gateway + Lambdas | FastAPI `services/channels/local` | reaproveita os mesmos handlers |
| Runtime | Lambda | processos no compose | `local_worker()` ao lado de cada `handler()` |
| Auth dashboard | Cognito | token estático | `services/api/src/api/auth.py` |
| Observabilidade | CloudWatch/X-Ray | Langfuse + logs | opcional |

**Não muda nada em:** grafo do agente, nós, prompts, tools, modelos, contratos, adapter do WhatsApp,
API REST, apps React. É o mesmo código com `SDR_PROFILE=local`.

## Busca por localidade (calibração do RAG)

O cliente escreve o lugar como quiser — "Pinheiros", "pinheiro", "Vila Madalena", "perto da Faria Lima",
"zona sul", "SP", "Osasco". `shared/sdr_shared/geo.py` resolve isso para bairro, região, cidade ou fora de
cobertura (tolerando acento, caixa, plural e erro de digitação), e a busca desce uma cascata
**bairro → vizinhos → região → cidade**, informando ao agente até onde precisou ir. Assim ele nunca
apresenta um bairro vizinho como se fosse o pedido, nem conclui que "não há imóveis" a partir de uma
lista filtrada. Editar o catálogo (novos bairros, apelidos, pontos de referência) exige `make seed` para
reindexar os embeddings.
