---
title: Contexto do projeto
description: Problema, público-alvo, objetivos, proposta de valor, escopo e estágio atual do Mora.
---

# Contexto do projeto

## Problema

No mercado imobiliário, o primeiro atendimento a um lead costuma ser lento e manual. O corretor perde
tempo qualificando contatos que ainda não estão prontos e demora a responder quem já está. A proposta é
automatizar a primeira etapa do funil (qualificação e recomendação) com uma assistente virtual,
entregando ao corretor apenas leads já qualificados, com um resumo pronto.

## Público-alvo

Imobiliárias de pequeno e médio porte — o desenho assume **escritório único** — e seus corretores, que
usam o painel administrativo. O cliente final conversa com a Mora pelo site ou pelo Telegram.

## Objetivos principais

- Qualificar o lead em uma conversa natural (intenção, região, faixa de preço, quartos, urgência).
- Recomendar imóveis do catálogo por busca semântica (RAG) calibrada por localidade.
- Agendar visitas e encaminhar o lead qualificado ao corretor (handoff), com briefing automático.
- Dar ao corretor visibilidade do funil, das conversas e do custo de IA por meio de um painel.

## Proposta de valor

Resposta imediata 24 horas por dia, qualificação consistente e um painel que mostra o funil e a
governança de consumo de LLM (Large Language Model, modelo de linguagem).

## Escopo atual (POC)

Agente multiagente, site vitrine com chat, painel do corretor, canal Telegram, API REST, RAG híbrido,
follow-up automático, governança de IA e uma camada de segurança determinística contra abuso de prompt.

## Fora do escopo (avaliado e cortado)

- Aplicativo nativo — o PWA cobre o caso.
- CRM real — simulado no banco, com endpoint `/leads/crm/sync`.
- Voice AI em tempo real.
- Multi-tenant.
- WhatsApp Business verificado da empresa.

O raciocínio completo está na [Referência completa (ARCHITECTURE.md)](../ARCHITECTURE.md).

## Estágio atual

Prova de conceito (POC). O núcleo está implementado e testado nos perfis local e AWS; alguns itens
dependentes de serviços AWS estão escritos, mas não testados. O estado item a item está em
[Funcionalidades](funcionalidades.md).

!!! info "Contexto acadêmico"
    O caminho do projeto sugere um trabalho acadêmico (FIAP, fase 5). Essa informação é **inferida** e
    não confirmada por nenhum arquivo do repositório. Veja [Pendências](../project/pendencias.md).
