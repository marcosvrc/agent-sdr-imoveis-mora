---
title: Tecnologias
description: Stack completa do Mora por categoria, com versões obtidas dos arquivos do projeto.
---

# Tecnologias

Versões obtidas dos arquivos do projeto (`package.json`, `pyproject.toml`, `settings.py`,
`docker-compose.yml`, `.github/workflows/ci.yml`). Onde a versão não está fixada no repositório, a
coluna traz `—`.

## Frontend

| Categoria | Tecnologia | Versão | Finalidade |
|---|---|---:|---|
| Frontend | React | ^18.3.1 | Interface do site e do painel |
| Frontend | Vite | ^7.3 | Build e servidor de desenvolvimento (5 → 7 em 2026-09, advisory no dev server) |
| Frontend | TypeScript | ^5.5.3 | Tipagem estática (build estrito) |
| Frontend | Tailwind CSS | ^3.4.0 | Estilos |
| Frontend | TanStack React Query | ^5.51.0 | Cache e sincronização de dados |
| Frontend | Zustand | ^4.5.0 | Estado do chat (site) |
| Frontend | Recharts | ^2.12.0 | Gráficos do painel |
| Frontend | React Router | ^6.26.0 | Rotas do site e do painel |
| Frontend | vite-plugin-pwa | ^1.3 | PWA do site |
| Frontend | Playwright | ^1.63 | Verificação de acessibilidade (axe) e telas, fora do CI |

O painel não tem SDK de autenticação: a credencial é um token estático enviado no cabeçalho
`Authorization` (ADR-0008). O pacote de autenticação gerenciada que existia aqui saiu com a nuvem.

## Backend

| Categoria | Tecnologia | Versão | Finalidade |
|---|---|---:|---|
| Backend | Python | 3.12 | Linguagem dos serviços |
| Backend | FastAPI | >=0.115 | API REST e apps de canal |
| Backend | Uvicorn | — | Servidor ASGI da API e dos canais |
| Backend | psycopg | >=3.2 | Acesso ao Postgres (com pool) |
| Backend | Redis (cliente) | >=5.0 | Fila entre os workers (Streams) |
| Backend | SDK MCP (`mcp`) | >=1.2 | Servidor MCP do CRM; é por onde a Mora fala com ele |
| Backend | cryptography (Fernet) | >=42 | Cifra do refresh token do calendário em repouso (`seguranca/cofre.py`) |
| Backend | argon2-cffi | — | Hash de senha dos usuários do CRM |

## IA / LLM

| Categoria | Tecnologia | Versão | Finalidade |
|---|---|---:|---|
| LLM/IA | LangGraph | >=0.2 | Orquestração do grafo multiagente |
| LLM/IA | LangChain Core | >=0.3 | Abstrações de mensagens / modelos |
| LLM/IA | Claude Sonnet (API da Anthropic) | `claude-sonnet-4-5` (padrão, ajustável) | Conversa com o cliente |
| LLM/IA | Claude Haiku (API da Anthropic) | `claude-haiku-4-5` (padrão, ajustável) | Roteamento e extração |
| LLM/IA | Provedores aceitos | — | `anthropic` (padrão), `openai` e `ollama`, via `SDR_LLM_PROVIDER` |
| LLM/IA | faster-whisper | >=1.0 | Transcrição de voz in-process (extra `local`) |

## RAG / Embeddings

| Categoria | Tecnologia | Versão | Finalidade |
|---|---|---:|---|
| RAG | Ollama `bge-m3` | 1024 dims | Embeddings locais (padrão, `SDR_EMBEDDINGS_PROVIDER=ollama`) |
| RAG | OpenAI `text-embedding-3-small` | `dimensions=1024` | Embeddings hospedados, alternativa sem container |
| RAG | pgvector (HNSW, cosseno) | — | Recuperação vetorial no mesmo Postgres (ADR-0001) |
| RAG | `tsvector` do Postgres (`portuguese`) | — | Fusão léxica (RRF), implementada e desligada por padrão (`SDR_RAG_LEXICO`) |

## Dados

| Categoria | Tecnologia | Versão | Finalidade |
|---|---|---:|---|
| Dados | PostgreSQL + pgvector | `pgvector/pgvector:pg16` | Dados relacionais + vetores; um servidor, dois bancos (`sdr` da Mora e `crm` do CRM — D-01) |
| Fila | Redis Streams | `redis:7-alpine` | Mensageria entre os workers |
| Agendamento | Tabela `followups_agendados` + worker `scheduler` | — | Follow-up automático, sem serviço externo |
| Armazenamento de fotos | Disco, servido pela API em `/fotos/...` | — | Diretório `SDR_FOTOS_DIR` |

## Infraestrutura

| Categoria | Tecnologia | Versão | Finalidade |
|---|---|---:|---|
| Autenticação | Token estático `SDR_PAINEL_TOKEN` | — | Acesso ao painel, fail-closed (ADR-0008) |
| Containers | Docker + Docker Compose | — | `local/docker-compose.yml` é a entrega inteira |
| CI | GitHub Actions | — | Dois jobs: `python` (ruff, pyright básico, cobertura, eval com dublês, OpenAPI) e `frontend` (build e eslint de `web`, `dashboard` e `crm`) |
| Análise estática | ruff + pyright (modo básico) | — | `make lint` e `make tipos`; `pyrightconfig.json` |

Não há infraestrutura como código: as stacks em nuvem foram removidas do repositório, e nada está
implantado — a entrega roda na máquina de quem avalia.

## Observabilidade e testes

| Categoria | Tecnologia | Versão | Finalidade |
|---|---|---:|---|
| Observabilidade | Postgres (tabelas de saúde) + `/health` + logs JSON | — | Observabilidade leve (ADR-0011) |
| Observabilidade | Langfuse | `langfuse/langfuse:2` | Tracing de LLM (opcional, perfil local) |
| Testes | pytest | — | Testes de backend |
