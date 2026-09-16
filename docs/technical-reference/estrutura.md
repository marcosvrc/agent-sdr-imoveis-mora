---
title: Estrutura do repositório
description: Organização do monorepo Mora, regras de dependência e convenções relevantes.
---

# Estrutura do repositório

```text
agent-sdr-morai/
├── apps/
│   ├── web/          Site vitrine (React + Vite + PWA) com widget de chat
│   └── dashboard/    Painel do corretor (funil, conversas, governança, auditoria)
├── services/
│   ├── agent/        Grafo multiagente (LangGraph) — o cérebro; único que fala com o LLM
│   ├── channels/     Adaptadores de canal (telegram, web, whatsapp, local)
│   ├── api/          API REST (FastAPI): imóveis, leads, dashboard, handoff, governança
│   ├── scheduler/    Follow-up automático
│   └── ingestion/    Carga de imóveis + embeddings
├── shared/           Pacote Python comum: modelos, contratos, DB, config, ports/adapters
├── infra/            AWS CDK (Python) — uma stack por domínio
├── local/            Perfil local: docker compose (Postgres+pgvector, Redis, canais, apps)
├── data/             Base simulada de imóveis e documentos institucionais
├── scripts/          Utilitários de dev (seed, check_env, simular webhook, aplicar schema)
├── docs/             Arquitetura, ADRs, observabilidade e este portal
└── .github/          CI/CD (GitHub Actions)
```

## Regras de dependência

- `shared/` é a **única ponte** entre serviços.
- Canais só traduzem mensagens e nunca chamam o LLM.
- O agente produz respostas neutras (`texto`, `opcoes`, `imoveis`, `acao`) e não sabe qual canal
  respondeu.

## Convenções relevantes

- Cada serviço expõe um pacote com nome próprio (`agent`, `api`, `canal_whatsapp`, `canal_telegram`,
  `sdr_scheduler`, `sdr_ingestion`) — nunca `src` — para evitar colisão no `sys.path`.
- As imagens Docker são construídas **a partir da raiz do repositório** (dependem de `shared/`):
  `docker build -f services/<serviço>/Dockerfile .`.

!!! note "Material descartável"
    A pasta `_to_delete/` e os arquivos `*.tgz` na raiz são material de trabalho descartável e não
    fazem parte da aplicação.
