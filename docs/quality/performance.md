---
title: Performance
description: Estratégias de performance observadas no código do Mora e um procedimento reprodutível para benchmarks.
---

# Performance

Estratégias observadas no código e na configuração:

- **Roteamento econômico.** Roteamento e extração usam Haiku; a conversa usa Sonnet (ADR-0010) — reduz
  custo e latência por turno.
- **Roteamento determinístico primeiro.** O supervisor decide por regra e só chama o LLM na ambiguidade.
- **RAG híbrido com cascata por localidade.** Evita buscas amplas desnecessárias.
- **Timeout de LLM.** `SDR_LLM_TIMEOUT_S` (padrão 45s); ao estourar, o cliente recebe fallback e o lead
  é encaminhado ao corretor.
- **Provedor de fallback.** `SDR_LLM_PROVIDER_FALLBACK` assume quando o primário falha.
- **Governança de orçamento.** Ao estourar o limite, o agente degrada (modelo econômico) ou bloqueia
  (encaminha ao corretor).
- **Rate limiting por lead.** 5 mensagens / 10s e 60 mensagens / hora (`guardrails/vazao.py`).
- **Cache de dados no front-end.** TanStack React Query.
- **Cache HTTP de imagens.** `Cache-Control: public, max-age=86400` nas fotos.
- **Paginação / limite.** Endpoints de listagem aceitam `limite` com teto (ex.: imóveis até 200).
- **Aurora Serverless v2** escala a zero quando ocioso (perfil AWS).

## Benchmarks

!!! warning "Sem benchmarks versionados"
    Não há benchmarks de desempenho medidos e versionados no repositório.

Procedimento reprodutível sugerido para obtê-los:

1. Subir o perfil local e popular o catálogo (`make local && make seed`).
2. Medir a latência ponta a ponta de um turno com um provedor fixo (ex.: Anthropic API), capturando o
   `duracao_ms` já registrado nos logs do agente e na tabela de saúde (ADR-0011).
3. Repetir por cenário (qualificação, consulta com RAG, agendamento) e registrar p50 / p95.

| Cenário | Métrica | Resultado | Ambiente |
|---|---|---:|---|
| — | — | A confirmar | A confirmar |
