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
  fictício. Preços, endereços e descrições não correspondem a imóveis reais. É o mesmo arquivo que
  popula o acervo do CRM, então a ficção vale para os dois sistemas.
- **Massa do CRM.** Clientes, oportunidades, interações, visitas e tarefas do CRM são gerados pelo
  seed determinístico (`services/crm/sdr_crm/seed/`) e marcados com `synthetic = true` no banco.
  Nenhuma pessoa, conversa ou negociação ali corresponde a alguém real. O reset se recusa a rodar
  se encontrar qualquer registro sem essa marca — é a proteção contra apontar a ferramenta para uma
  base de verdade por engano.
- **Documentos institucionais.** Os arquivos em `data/documentos/` — política de visitas, garantias
  de locação, taxas e prazos — são exemplos escritos para esta POC, marcados como fictícios no
  próprio texto. São a base do RAG institucional: o que o agente responde sobre "como a imobiliária
  trabalha" sai dali, e portanto é ficção coerente, não política de empresa nenhuma.
- **Dados institucionais da Vértice Imóveis.** CRECI, CNPJ, endereço e telefone exibidos no site são
  exemplos marcados como tal na interface (ver `apps/web/src/lib/imobiliaria.ts`). A Vértice Imóveis
  é uma imobiliária fictícia criada para esta POC. Onde um número de registro real seria exigido por
  lei, o campo foi deixado **em branco** de propósito: inventar um CRECI ou um CNPJ que possa
  pertencer a alguém é pior que não ter nenhum, e nenhum deles entra em dado estruturado
  (JSON-LD) — um buscador não deve ser convidado a indexar credencial inventada.
- **Dependências de terceiros.** Cada biblioteca mantém a sua própria licença; nada aqui altera
  esses termos.
- **Serviços externos.** Anthropic, AWS Bedrock, Google Calendar e Telegram têm termos próprios de
  uso, e a licença deste código não concede direito algum sobre eles.

## Uso acadêmico

Trabalho desenvolvido para a fase 5 da FIAP. Se este repositório for útil como referência em outro
trabalho, a licença permite — e a citação da fonte, embora não obrigatória pela MIT, é bem-vinda.
