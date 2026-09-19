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
- Uma chave de LLM (`ANTHROPIC_API_KEY` ou `OPENAI_API_KEY`) — **ou** Ollama, que sobe no próprio
  compose, para rodar sem custo e sem chave.

## Subir

`make` sozinho imprime esta mesma ordem.

```bash
# 1. Clonar e entrar no diretório
git clone <url-do-repositorio>
cd agent-sdr-morai

# 2. Configurar o ambiente do perfil local
cp -n local/.env.example local/.env
# edite local/.env: ANTHROPIC_API_KEY e, se for usar o Telegram, o token do bot

# 3. Conferir o .env
make check-env

# 4. Subir tudo (fica em primeiro plano; siga noutro terminal)
make local-ollama

# 5. Baixar o modelo de embeddings (demora, uma vez só)
make ollama-pull

# 6. Popular o catálogo (200 imóveis determinísticos + embeddings) e os documentos institucionais
make seed && make docs-kb
```

Para a massa do CRM, acrescente `make preparar` e `make crm-token` entre os passos 4 e 5 — o
[roteiro de demonstração](roteiro-demonstracao.md) detalha. Sem CRM a Mora roda sozinha.

## Validar

```bash
curl -s http://localhost:8000/health       # {"ok": true, "agente": "Mora", ...}
curl -s "http://localhost:8000/imoveis?limite=3"
```

Abra o site em <http://localhost:5173> e o painel em <http://localhost:5174>. O painel pede o token
`SDR_PAINEL_TOKEN`; com ele em branco no `local/.env`, vale `dev-token`.

## Encerrar

```bash
cd local && docker compose down             # use down -v para apagar também os volumes
```

!!! tip "Próximo passo"
    Para a lista completa de portas e para a execução manual (sem Docker), siga para
    [Executando com Docker](../getting-started/docker.md) e
    [Executando manualmente](../getting-started/manual.md).
