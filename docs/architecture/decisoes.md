---
title: Decisões arquiteturais (ADRs)
description: Índice dos 12 Architecture Decision Records do Mora, com problema, justificativa e trade-offs.
---

# Decisões arquiteturais (ADRs)

Cada decisão está registrada como ADR (Architecture Decision Record, registro de decisão
arquitetural) em `docs/adr`. Os ADRs completos estão disponíveis neste portal, no submenu
**Decisões arquiteturais (ADRs)** — este índice resume e aponta para cada um.

## Principais decisões

### RAG sobre Postgres + pgvector, com fusão de ranking
- **Problema.** RAG confiável sem depender de um serviço gerenciado que não roda na máquina de quem
  avalia.
- **Decisão.** Um Postgres com pgvector serve imóvel e documento institucional, no mesmo banco que o
  painel consulta, com piso de similaridade e reescrita de consulta.
- **Trade-off.** A fusão léxica (RRF) está implementada mas desligada por padrão
  (`SDR_RAG_LEXICO`): o A/B piorou o recall (31,9% → 29,8%).
- [ADR-0001](../adr/0001-rag-com-postgres-pgvector.md)

### Runtime do agente: container local consumindo uma fila
- **Justificativa.** Um turno leva de 20 a 40 segundos e não cabe no fio da requisição HTTP; o
  agente é um worker que consome o tópico `inbound` e publica na saída do canal.
- **Trade-off.** Não há nada implantado: agente, resumidor, scheduler e canais são containers do
  `local/docker-compose.yml`, com Redis fazendo a fila.
- [ADR-0002](../adr/0002-runtime-do-agente-em-container.md)

### Canais como adaptadores sem lógica
- **Benefício.** Permite trocar ou adicionar canal sem tocar no agente.
- [ADR-0003](../adr/0003-canais-como-adaptadores.md)

### Um Postgres para tudo, em vez de um banco por finalidade
- **Justificativa.** Registro transacional, busca vetorial, agregação do painel e estado do grafo
  cabem no mesmo PostgreSQL com pgvector.
- **Trade-off.** Um banco só concentra cargas de perfis diferentes.
- [ADR-0004](../adr/0004-postgres-como-banco-unico.md)

### Telegram em vez de WhatsApp como canal externo
- **Justificativa.** Bot criado na hora pelo @BotFather, sem verificação de negócio, e por long
  polling (`getUpdates`) — sem webhook e sem URL pública.
- **Trade-off.** O WhatsApp saiu do código: adaptador e worker foram removidos, e voltar significa
  escrevê-los de novo.
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
| [0001](../adr/0001-rag-com-postgres-pgvector.md) | RAG sobre Postgres + pgvector, com fusão de ranking |
| [0002](../adr/0002-runtime-do-agente-em-container.md) | Runtime do agente: container local consumindo uma fila |
| [0003](../adr/0003-canais-como-adaptadores.md) | Canais como adaptadores |
| [0004](../adr/0004-postgres-como-banco-unico.md) | Um Postgres para tudo, em vez de um banco por finalidade |
| [0005](../adr/0005-observabilidade-com-opentelemetry-e-grafana.md) | Observabilidade com OpenTelemetry + Grafana (revogado) |
| [0006](../adr/0006-site-vitrine-com-agente-embutido.md) | Site vitrine com agente embutido |
| [0007](../adr/0007-telegram-em-vez-de-whatsapp.md) | Telegram em vez de WhatsApp |
| [0008](../adr/0008-portoes-de-autenticacao-proprios.md) | Cada porta privada carrega o seu próprio portão |
| [0009](../adr/0009-gateway-de-llm-litellm-openrouter-ou-nada.md) | Gateway de LLM: LiteLLM, OpenRouter ou nada |
| [0010](../adr/0010-modelo-por-nivel-e-troca-pelo-painel.md) | Modelo por nível e troca pelo painel |
| [0011](../adr/0011-observabilidade-leve-no-postgres.md) | Observabilidade leve no Postgres |
| [0012](../adr/0012-vitrine-encontravel-e-acessivel.md) | Vitrine encontrável e acessível |

!!! tip "Novos ADRs"
    Ao registrar uma nova decisão, adicione um arquivo em `docs/adr/` seguindo a numeração e o formato
    dos existentes, e inclua uma linha nesta tabela.
