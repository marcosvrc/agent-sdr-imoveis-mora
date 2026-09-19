---
title: Quick Start
description: Suba o Mora no perfil local em poucos comandos com Docker Compose.
---

# Quick Start

O caminho mais rápido é o **perfil local** com Docker Compose. Para os detalhes de cada etapa, veja
[Primeiros passos](../getting-started/pre-requisitos.md).

## Pré-requisitos mínimos

- Git
- Docker e Docker Compose
- Credenciais de um provedor de LLM (Amazon Bedrock ou Anthropic API) — **ou** Ollama para rodar 100%
  local, sem custo.

## Subir em 4 passos

```bash
# 1. Clonar e entrar no diretório
git clone <url-do-repositorio>
cd agent-sdr-morai

# 2. Configurar o ambiente do perfil local
cp -n local/.env.example local/.env
# edite local/.env: escolha o provedor de LLM e, se for usar o Telegram, o token do bot

# 3. Subir tudo (adicione --profile ollama para LLM local)
make local

# 4. Popular o catálogo (200 imóveis determinísticos + embeddings)
make seed
```

O `make local` executa `scripts/check_env.py` antes de subir e aplica o schema do banco
automaticamente na inicialização do container `db`.

## Validar

```bash
curl -s http://localhost:8000/health       # {"ok": true, "agente": "Mora", ...}
curl -s "http://localhost:8000/imoveis?limite=3"
```

Abra o site em <http://localhost:5173> e o painel em <http://localhost:5174>.

## Encerrar

```bash
cd local && docker compose down             # use down -v para apagar também os volumes
```

!!! tip "Próximo passo"
    Para a execução manual (sem Docker), a lista completa de portas e o deploy AWS, siga para
    [Executando com Docker](../getting-started/docker.md) e
    [Executando manualmente](../getting-started/manual.md).
