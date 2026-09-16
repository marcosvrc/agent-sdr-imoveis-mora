---
title: Roadmap e limitações
description: O que não está pronto no Mora — limitações conhecidas, débitos técnicos e dependências externas.
---

# Roadmap e limitações

Esta página lista o que **não** está pronto — separada das
[Funcionalidades implementadas](../overview/funcionalidades.md).

## Limitações conhecidas

- Canal WhatsApp implementado, mas **desativado** (depende de número de negócio verificado — ADR-0007).
- Knowledge Base e transcrição de áudio escritas, mas **não testadas** (exigem AWS).
- Rate limiting é **por processo**, não distribuído entre múltiplos workers.
- **Sem benchmarks** de performance versionados.
- CRM é **simulado** (`/leads/crm/sync`), não integrado a um sistema real.

## Débitos técnicos / itens em aberto

- Análise de dependências e cobertura de testes não estão no CI.
- Instrumentação de observabilidade de sistema (OpenTelemetry / Grafana) foi revogada; existe apenas a
  leve (ADR-0011).
- Papéis / permissões granulares por usuário no painel: **a definir**.

## Riscos e dependências externas

- Disponibilidade e cota do provedor de LLM (Bedrock / Anthropic).
- Custo de infraestrutura AWS dominado pelo NAT Gateway (ver estimativas na
  [Referência completa (ARCHITECTURE.md)](../ARCHITECTURE.md#10-perfis-de-execucao-e-custo)).

!!! tip "Transformar pendências em issues"
    A sugestão do projeto é converter estes itens e as [Pendências de documentação](pendencias.md) em
    issues, atualizando as páginas correspondentes quando resolvidas.
