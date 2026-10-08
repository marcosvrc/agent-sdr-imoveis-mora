# Perfil local

```bash
cd local && cp -n .env.example .env      # preencha o provedor de LLM (e CRM_MCP_TOKEN, se for usar o CRM)
docker compose up --build                # + `--profile ollama` para LLM/embeddings locais
docker compose exec agent python /app/scripts/gerar_imoveis.py 200   # 200 imóveis determinísticos
docker compose exec -w /app/services/ingestion agent python -m sdr_ingestion.ingest_imoveis /app/data/imoveis/imoveis.json
```

A ordem completa, com CRM, está em `make` (alvo `ajuda`) e em `docs/getting-started/docker.md`.

| URL | Serviço |
|---|---|
| http://localhost:5173 | Site vitrine (PWA) |
| http://localhost:5174 | Dashboard do corretor |
| http://localhost:8000/docs | API (OpenAPI) |
| ws://localhost:8001/ws | WebSocket do chat |
| http://localhost:3000 | Painel do CRM |
| http://localhost:8100 · :8200/mcp | API e servidor MCP do CRM |
| http://localhost:3001 | Langfuse (`--profile observability`; nenhum código envia trace a ele ainda) |
| localhost:5433 / :6380 / :11435 | Postgres, Redis e Ollama do compose, vistos do host (`DB_HOST_PORT`, `REDIS_HOST_PORT`, `OLLAMA_HOST_PORT` no `.env`) |

Tudo publicado só em `127.0.0.1`. Para outro aparelho da rede alcançar API, canais, CRM e
front-ends, `HOST_BIND=0.0.0.0` no `.env` — com um `SDR_PAINEL_TOKEN` forte definido antes.

Se usar Ollama: `docker compose exec ollama ollama pull bge-m3` (ou `make ollama-pull`), e
`ollama pull llama3.1:8b` se ele também for o LLM. Os embeddings têm 1024 dimensões em qualquer
provedor (`bge-m3` no Ollama, `text-embedding-3-small` reduzido na OpenAI/OpenRouter) — a mesma
coluna `vector(1024)`; um modelo de outra dimensão exige ajustar o schema e reindexar.

## Onde está cada peça

Não há segundo ambiente: o compose é a entrega (ADR-0002, revisado — a nuvem saiu do projeto junto
com os adaptadores e a infraestrutura como código).

| Peça | Implementação | Onde |
|---|---|---|
| Fila | Redis Streams, com AOF em volume próprio | `shared/sdr_shared/adapters/local/broker.py` |
| Follow-up | tabela + worker em laço | `shared/sdr_shared/adapters/local/scheduler.py`, `services/scheduler` |
| Embeddings | Ollama (`bge-m3`), OpenAI ou OpenRouter | `shared/sdr_shared/adapters/{local,hospedados}/embeddings.py` |
| LLM | Anthropic, OpenAI, OpenRouter ou Ollama | `shared/sdr_shared/ports/factory.py` |
| RAG | pgvector direto | `services/ingestion`, `shared/sdr_shared/db` |
| Entrada HTTP/WS | FastAPI | `services/channels/local` |
| Runtime | um processo por serviço no compose, com `restart` | `local_worker()` de cada serviço |
| Auth do painel | token estático `SDR_PAINEL_TOKEN` | `services/api/src/api/auth.py` |
| Observabilidade | tabelas no Postgres + logs (ADR-0011) | `shared/sdr_shared/db/monitoramento.py` |

## Busca por localidade (calibração do RAG)

O cliente escreve o lugar como quiser — "Pinheiros", "pinheiro", "Vila Madalena", "perto da Faria Lima",
"zona sul", "SP", "Osasco". `shared/sdr_shared/geo.py` resolve isso para bairro, região, cidade ou fora de
cobertura (tolerando acento, caixa, plural e erro de digitação), e a busca desce uma cascata
**bairro → vizinhos → região → cidade**, informando ao agente até onde precisou ir. Assim ele nunca
apresenta um bairro vizinho como se fosse o pedido, nem conclui que "não há imóveis" a partir de uma
lista filtrada. Editar o catálogo (novos bairros, apelidos, pontos de referência) exige `make seed` para
reindexar os embeddings.
