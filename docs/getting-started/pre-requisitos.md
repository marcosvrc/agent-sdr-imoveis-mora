---
title: Pré-requisitos
description: O que instalar para rodar o Mora com docker compose ou executar os testes.
---

# Pré-requisitos

A entrega roda inteira na sua máquina, com `docker compose`. Não há conta de nuvem para criar nem
nada implantado em servidor.

## Para rodar (recomendado para começar)

- Git.
- Docker e Docker Compose v2 — no Mac, o Docker Desktop. O compose usa `start_interval` nos
  healthchecks, que exige Docker Engine 25 ou mais novo (Docker Desktop 4.27+).
- Uma chave do provedor de LLM escolhido (`ANTHROPIC_API_KEY` ou `OPENAI_API_KEY`) — ou Ollama,
  que já sobe no compose, para rodar sem custo e sem chave nenhuma.
- (Opcional) Token de bot do Telegram, obtido no `@BotFather`, para exercitar o canal externo.
- (Opcional) `CRM_MCP_TOKEN`, se quiser a ponte com o CRM. Sem ele a Mora roda sozinha.

## Rodar os testes de backend ou executar serviços manualmente

- Python **3.12** (a versão usada na CI).
- `pip` ou [`uv`](https://docs.astral.sh/uv/) como gerenciador de pacotes. O `make setup` usa o
  `uv` quando ele existe e o `pip` quando não — e para na primeira falha, com a mensagem dela.
- Node.js **20** para os front-ends (`make setup` instala os três: `web`, `dashboard` e `crm`).

!!! warning "Requisitos de hardware — a confirmar"
    Os requisitos de hardware mínimo e recomendado não estão documentados no repositório
    (`A confirmar`). O uso de Ollama local aumenta bastante o consumo de CPU e RAM.
