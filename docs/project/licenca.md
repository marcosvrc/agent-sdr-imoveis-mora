---
title: Licença
description: Termos de uso do código do Mora e o que se aplica aos dados de demonstração.
---

# Licença

O código deste repositório está sob a **licença MIT** — veja o arquivo
[`LICENSE`](https://github.com/marcosvrc/agent-sdr-imoveis-mora/blob/master/LICENSE) na raiz.

Na prática: qualquer pessoa pode usar, copiar, modificar e redistribuir, inclusive
comercialmente, desde que mantenha o aviso de copyright. O software é fornecido "como está",
sem garantia.

**Copyright (c) 2026 Marcos Ramos.**

## O que a licença NÃO cobre

- **Dados de demonstração.** O catálogo de 200 imóveis em `data/imoveis/` é gerado por script e
  fictício. Preços, endereços e descrições não correspondem a imóveis reais.
- **Dados institucionais da Vértice Imóveis.** CRECI, CNPJ, endereço e telefone exibidos no site são
  exemplos marcados como tal na interface (ver `apps/web/src/lib/imobiliaria.ts`). A Vértice Imóveis
  é uma imobiliária fictícia criada para esta POC.
- **Dependências de terceiros.** Cada biblioteca mantém a sua própria licença; nada aqui altera
  esses termos.
- **Serviços externos.** Anthropic, AWS Bedrock, Google Calendar e Telegram têm termos próprios de
  uso, e a licença deste código não concede direito algum sobre eles.

## Uso acadêmico

Trabalho desenvolvido para a fase 5 da FIAP. Se este repositório for útil como referência em outro
trabalho, a licença permite — e a citação da fonte, embora não obrigatória pela MIT, é bem-vinda.
