---
title: Estrutura do repositório
description: Organização do monorepo Mora, regras de dependência e convenções relevantes.
---

# Estrutura do repositório

```text
agent-sdr-morai/
├── apps/
│   ├── web/          Site vitrine (React + Vite + PWA) com widget de chat
│   ├── dashboard/    Painel do corretor (funil, conversas, governança, auditoria)
│   └── crm/          Painel do CRM da imobiliária (React) — sistema à parte
├── services/
│   ├── agent/        Grafo multiagente (LangGraph) — o cérebro; único que fala com o LLM
│   ├── channels/     Adaptadores de canal: `telegram/` e `local/` (WebSocket do site e CLI)
│   ├── api/          API REST (FastAPI): imóveis, leads, dashboard, handoff, governança
│   ├── crm/          CRM da imobiliária: API REST, servidor MCP e banco próprios
│   ├── scheduler/    Follow-up automático
│   └── ingestion/    Carga de imóveis + embeddings
├── shared/           Pacote Python comum: modelos, contratos, DB, config, ports/adapters
├── local/            A entrega: docker compose (Postgres+pgvector, Redis, workers, apps, CRM)
│                     e a única imagem Python, `Dockerfile.python`, usada por todos os serviços
├── data/             Base simulada de imóveis e documentos institucionais
├── scripts/          Utilitários de dev (`check_env.py`, `gerar_imoveis.py`, `gerar_openapi.py`)
├── tests/            Suíte da raiz (hoje, a do `check_env`)
├── docs/             Arquitetura, ADRs, observabilidade e este portal
└── .github/          CI (GitHub Actions)
```

Não há diretório de infraestrutura como código: as stacks em nuvem foram removidas do repositório
quando a entrega passou a ser só o `docker compose` de `local/`.

## Regras de dependência

- `shared/` é a **única ponte** entre serviços.
- Canais só traduzem mensagens e nunca chamam o LLM.
- O agente produz respostas neutras (`texto`, `opcoes`, `imoveis`, `acao`) e não sabe qual canal
  respondeu.

## Convenções relevantes

- Cada serviço expõe um pacote com nome próprio (`agent`, `api`, `canal_telegram`, `sdr_scheduler`,
  `sdr_ingestion`, `sdr_crm`) — nunca `src` — para evitar colisão no `sys.path`.
- Há **uma** imagem Python para todos os serviços (`local/Dockerfile.python`), construída **a partir
  da raiz do repositório** porque todos dependem de `shared/`; o que muda entre os containers é o
  `command` do `local/docker-compose.yml`, não a imagem. Os Dockerfiles por serviço existiam para
  empacotar funções hospedadas e saíram junto com elas.

!!! note "Material descartável"
    A pasta `_to_delete/` e os arquivos `*.tgz` na raiz são material de trabalho descartável e não
    fazem parte da aplicação.
