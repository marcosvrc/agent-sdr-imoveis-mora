---
title: Pré-requisitos
description: O que instalar para rodar o Mora no perfil local, executar os testes ou fazer deploy na AWS.
---

# Pré-requisitos

## Perfil local (recomendado para começar)

- Git.
- Docker e Docker Compose.
- Credenciais do provedor de LLM escolhido (Amazon Bedrock ou Anthropic API) — ou Ollama para rodar
  100% local, sem custo.
- (Opcional) Token de bot do Telegram, obtido no `@BotFather`, para exercitar o canal externo.

## Rodar os testes de backend ou executar serviços manualmente

- Python **3.12** (versão usada em produção e na CI).
- `pip` ou [`uv`](https://docs.astral.sh/uv/) como gerenciador de pacotes (o `Makefile` usa `uv`).
- Node.js **20** para os front-ends.

## Deploy AWS

- Conta AWS com acesso ao Amazon Bedrock na região escolhida.
- AWS CLI configurada e AWS CDK (`npm i -g aws-cdk`).
- Python 3.12 e as dependências de `infra/requirements.txt`.

!!! warning "Requisitos de hardware — a confirmar"
    Os requisitos de hardware mínimo e recomendado não estão documentados no repositório
    (`A confirmar`). O uso de Ollama local aumenta bastante o consumo de CPU e RAM.
