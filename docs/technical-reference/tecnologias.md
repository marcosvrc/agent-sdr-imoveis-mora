---
title: Tecnologias
description: Stack completa do Mora por categoria, com versões obtidas dos arquivos do projeto.
---

# Tecnologias

Versões obtidas dos arquivos do projeto (`package.json`, `pyproject.toml`, `settings.py`,
`docker-compose.yml`, `.github/workflows/ci.yml`). Onde a versão não está fixada no repositório, consta
`A confirmar`.

## Frontend

| Categoria | Tecnologia | Versão | Finalidade |
|---|---|---:|---|
| Frontend | React | ^18.3.1 | Interface do site e do painel |
| Frontend | Vite | ^5.4.0 | Build e servidor de desenvolvimento |
| Frontend | TypeScript | ^5.5.3 | Tipagem estática (build estrito) |
| Frontend | Tailwind CSS | ^3.4.0 | Estilos |
| Frontend | TanStack React Query | ^5.51.0 | Cache e sincronização de dados |
| Frontend | Zustand | ^4.5.0 | Estado do chat (site) |
| Frontend | Recharts | ^2.12.0 | Gráficos do painel |
| Frontend | AWS Amplify | ^6.5.0 | Autenticação Cognito no painel (perfil AWS) |
| Frontend | vite-plugin-pwa | ^0.20.0 | PWA do site |

## Backend

| Categoria | Tecnologia | Versão | Finalidade |
|---|---|---:|---|
| Backend | Python | 3.12 | Linguagem dos serviços |
| Backend | FastAPI | >=0.115 | API REST e apps de canal |
| Backend | Mangum | A confirmar | Adaptador FastAPI → AWS Lambda |

## IA / LLM

| Categoria | Tecnologia | Versão | Finalidade |
|---|---|---:|---|
| LLM/IA | LangGraph | >=0.2 | Orquestração do grafo multiagente |
| LLM/IA | LangChain Core | >=0.3 | Abstrações de mensagens / modelos |
| LLM/IA | Bedrock — Claude Sonnet | `anthropic.claude-sonnet-4-5` (padrão, ajustável) | Conversa com o cliente |
| LLM/IA | Bedrock — Claude Haiku | `anthropic.claude-haiku-4-5` (padrão, ajustável) | Roteamento e extração |
| LLM/IA | Provedores alternativos | — | `anthropic` (API) e `ollama` (local), via `SDR_LLM_PROVIDER` |

## RAG / Embeddings

| Categoria | Tecnologia | Versão | Finalidade |
|---|---|---:|---|
| RAG | Amazon Titan Embeddings v2 | `amazon.titan-embed-text-v2:0` | Embeddings (perfil AWS) |
| RAG | Ollama bge-m3 | 1024 dims | Embeddings locais (opcional) |
| RAG | Bedrock Knowledge Base | — | RAG gerenciado; fallback pgvector direto (ADR-0001) |

## Dados

| Categoria | Tecnologia | Versão | Finalidade |
|---|---|---:|---|
| Dados | PostgreSQL + pgvector | `pgvector/pgvector:pg16` | Dados relacionais + vetores |
| Dados (AWS) | Aurora Serverless v2 (Postgres 16) | — | Mesma base, gerenciada (ADR-0004) |
| Fila (AWS) | Amazon SQS + EventBridge Scheduler | — | Mensageria e follow-up |
| Fila (local) | Redis Streams | `redis:7-alpine` | Substitui SQS/EventBridge no compose |
| Armazenamento (AWS) | Amazon S3 + CloudFront | — | Fotos e documentos |

## Infraestrutura

| Categoria | Tecnologia | Versão | Finalidade |
|---|---|---:|---|
| Autenticação | Amazon Cognito (AWS) / token estático (local) | — | Acesso ao painel (ADR-0008) |
| Infraestrutura | AWS CDK (Python) | ver `infra/requirements.txt` | IaC, 10 stacks |
| Containers | Docker + Docker Compose | — | Perfil local e imagens de deploy |
| CI/CD | GitHub Actions | — | Testes, build de front-ends, `cdk synth` |

## Observabilidade e testes

| Categoria | Tecnologia | Versão | Finalidade |
|---|---|---:|---|
| Observabilidade | Postgres (tabelas de saúde) + `/health` + logs JSON | — | Observabilidade leve (ADR-0011) |
| Observabilidade | Langfuse | `langfuse/langfuse:2` | Tracing de LLM (opcional, perfil local) |
| Testes | pytest | — | Testes de backend |
