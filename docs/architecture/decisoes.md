---
title: Decisões arquiteturais (ADRs)
description: Índice dos 12 Architecture Decision Records do Mora, com problema, justificativa e trade-offs.
---

# Decisões arquiteturais (ADRs)

Cada decisão está registrada como ADR (Architecture Decision Record, registro de decisão
arquitetural) em `docs/adr`. Os ADRs completos estão disponíveis neste portal, no submenu
**Decisões arquiteturais (ADRs)** — este índice resume e aponta para cada um.

## Principais decisões

### RAG com Knowledge Base + Aurora pgvector, com fallback pgvector direto
- **Problema.** RAG confiável sem amarrar a POC a um serviço gerenciado indisponível no local.
- **Decisão.** Usar Knowledge Base quando disponível; se `SDR_KNOWLEDGE_BASE_ID` estiver vazio, cair
  para busca vetorial direta no Postgres.
- **Trade-off.** O caminho gerenciado não é testado localmente.
- [ADR-0001](../adr/0001-rag-knowledge-base-com-aurora-pgvector.md)

### Agente em Lambda container consumindo SQS
- **Justificativa.** Maximiza serverless; as Lambdas são imagens de container porque dependem de
  `shared`, `psycopg` e `httpx`.
- [ADR-0002](../adr/0002-agente-em-lambda-container.md)

### Canais como adaptadores sem lógica
- **Benefício.** Permite trocar ou adicionar canal sem tocar no agente.
- [ADR-0003](../adr/0003-canais-como-adaptadores.md)

### Aurora Serverless v2 (Postgres) em vez de DynamoDB
- **Justificativa.** SQL para o painel e vetores na mesma base; escala a zero.
- **Trade-off.** Exige VPC / NAT (custo).
- [ADR-0004](../adr/0004-aurora-em-vez-de-dynamodb.md)

### Telegram em vez de WhatsApp como canal ativo
- **Justificativa.** Bot criado sem verificação de negócio; o adapter de WhatsApp fica pronto para
  religar.
- [ADR-0007](../adr/0007-telegram-em-vez-de-whatsapp.md)

### Modelo por nível, editável no painel
- **Decisão.** Sonnet na conversa, Haiku em roteamento/extração; ajustável sem redeploy.
- [ADR-0010](../adr/0010-modelo-por-nivel-e-troca-pelo-painel.md)

### Observabilidade leve no Postgres
- **Decisão.** Três tabelas no Postgres, `/health` real e logs JSON — que **revogaram** a stack
  OpenTelemetry + Grafana (ADR-0005) por consumo de recursos na máquina de desenvolvimento.
- [ADR-0011](../adr/0011-observabilidade-leve-no-postgres.md)

## Índice completo

| ADR | Assunto |
|---|---|
| [0001](../adr/0001-rag-knowledge-base-com-aurora-pgvector.md) | RAG com Knowledge Base + Aurora pgvector |
| [0002](../adr/0002-agente-em-lambda-container.md) | Agente em Lambda container |
| [0003](../adr/0003-canais-como-adaptadores.md) | Canais como adaptadores |
| [0004](../adr/0004-aurora-em-vez-de-dynamodb.md) | Aurora em vez de DynamoDB |
| [0005](../adr/0005-observabilidade-com-opentelemetry-e-grafana.md) | Observabilidade com OpenTelemetry + Grafana (revogado) |
| [0006](../adr/0006-site-vitrine-com-agente-embutido.md) | Site vitrine com agente embutido |
| [0007](../adr/0007-telegram-em-vez-de-whatsapp.md) | Telegram em vez de WhatsApp |
| [0008](../adr/0008-portoes-de-autenticacao-fora-do-api-gateway.md) | Portões de autenticação fora do API Gateway |
| [0009](../adr/0009-gateway-de-llm-litellm-openrouter-ou-nada.md) | Gateway de LLM: LiteLLM, OpenRouter ou nada |
| [0010](../adr/0010-modelo-por-nivel-e-troca-pelo-painel.md) | Modelo por nível e troca pelo painel |
| [0011](../adr/0011-observabilidade-leve-no-postgres.md) | Observabilidade leve no Postgres |
| [0012](../adr/0012-vitrine-encontravel-e-acessivel.md) | Vitrine encontrável e acessível |

!!! tip "Novos ADRs"
    Ao registrar uma nova decisão, adicione um arquivo em `docs/adr/` seguindo a numeração e o formato
    dos existentes, e inclua uma linha nesta tabela.
