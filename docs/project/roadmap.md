---
title: Roadmap e limitações
description: O que não está pronto no Mora — limitações conhecidas, débitos técnicos e dependências externas.
---

# Roadmap e limitações

Esta página lista o que **não** está pronto — separada das
[Funcionalidades implementadas](../overview/funcionalidades.md).

## Limitações conhecidas

- **Um canal externo só: o Telegram.** O WhatsApp foi removido do código — o webhook da Cloud API
  exige URL pública e número de negócio verificado, que a entrega local não tem (ADR-0007). Voltar
  significa escrever o adaptador de novo.
- **Nada está implantado.** Não há URL para mandar a alguém: a entrega inteira é o
  `local/docker-compose.yml`, rodando na máquina de quem avalia. Isso é escolha, não pendência —
  veja [Execução e custo](../ARCHITECTURE.md#10-execucao-e-custo).
- **Fusão léxica do RAG desligada por padrão.** Implementada e medida atrás de `SDR_RAG_LEXICO`; o
  A/B piorou o recall (31,9% → 29,8%), então o padrão continua sendo só o vetorial.
- Rate limiting é **por processo**, não distribuído entre múltiplos workers.
- **Sem benchmarks** de performance versionados.
- Não há teste de comportamento de front-end (o front é coberto por build estrito, lint e
  verificação de acessibilidade).

## Débitos técnicos / itens em aberto

- Análise de dependências não está no CI (a cobertura está, com piso).
- Instrumentação de observabilidade de sistema (OpenTelemetry / Grafana) foi revogada; existe apenas a
  leve (ADR-0011).
- Papéis / permissões granulares por usuário no painel: **a definir**.
- Política formal de retenção e exclusão de dados (LGPD).

## Riscos e dependências externas

- Disponibilidade e cota do provedor de LLM (`SDR_LLM_PROVIDER`). O reserva
  (`SDR_LLM_PROVIDER_FALLBACK`) reduz o risco, não o elimina.
- API do Telegram (canal externo) e API do Google Agenda, quando configurada — esta degrada para a
  grade interna, aquela não tem substituto.
- Custo variável: só as chamadas ao modelo. Embeddings, transcrição e banco rodam na máquina, sem
  cobrança (ver [Execução e custo](../ARCHITECTURE.md#10-execucao-e-custo)).

!!! tip "Transformar pendências em issues"
    A sugestão do projeto é converter estes itens e as [Pendências de documentação](pendencias.md) em
    issues, atualizando as páginas correspondentes quando resolvidas.
