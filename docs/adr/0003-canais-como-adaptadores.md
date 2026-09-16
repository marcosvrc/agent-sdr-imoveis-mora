# ADR-0003 — Canais são adaptadores sem lógica de negócio

**Status:** aceito · **Data:** 2026-09-08

## Decisão
`services/channels/*` só traduz eventos do provedor para `MensagemNormalizada` e `RespostaAgente`
para o formato do canal (botões, listas, cards, JSON WebSocket). Nunca chamam Bedrock nem leem o
cartão do lead. Um lead pode ter N canais (`tabela canais`), com um único histórico.

## Consequências
- Adicionar canal (Instagram, voz) = uma pasta nova em `channels/`.
- Handoff humano: o roteador entrega a mensagem ao painel em vez do agente; o canal não muda.
- Migração web → WhatsApp preserva histórico via `lead_id`.
