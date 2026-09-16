---
title: Como contribuir
description: Fluxo de contribuição inferido do CI e das convenções do Mora, com as validações obrigatórias.
---

# Como contribuir

!!! note "Sem `CONTRIBUTING.md` formal"
    Não há um `CONTRIBUTING.md` no repositório. As práticas abaixo são **inferidas** do fluxo de CI e
    das convenções do projeto.

## Fluxo sugerido

1. **Branches (inferido).** Crie uma branch a partir da principal para cada mudança (ex.:
   `feat/nome-curto`, `fix/nome-curto`).
2. **Commits e Pull Requests (inferido).** Descreva o que muda e por quê; mantenha PRs focados.
3. **Antes de tocar em um serviço.** Leia a
   [Referência completa (ARCHITECTURE.md)](../ARCHITECTURE.md)
   e respeite as [regras de dependência](../technical-reference/estrutura.md#regras-de-dependencia)
   entre camadas.

## Validações obrigatórias

O PR precisa passar na CI. Rode localmente antes de abrir:

```bash
make test                       # backend
cd apps/web && npm run build     # front-end web
cd apps/dashboard && npm run build   # front-end painel
cd infra && cdk synth            # infraestrutura
```

## Contribuir com a documentação

Este portal é feito em Markdown, sob `docs/`. Para editar:

```bash
pip install mkdocs-material
mkdocs serve                     # pré-visualização em http://127.0.0.1:8000
```

Cada página tem um link **"Editar"** no topo (aponta para o GitHub). A publicação é automática ao
mesclar na branch principal — veja o workflow em
[`.github/workflows/docs.yml`](https://github.com/exemplo/agent-sdr-morai/blob/main/.github/workflows/docs.yml).


!!! info "A confirmar"
    Convenção de commits, template de PR e processo de revisão formais ainda não estão definidos.
