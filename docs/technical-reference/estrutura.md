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
├── data/             Massa de demonstração: acervo (400 imóveis), equipe (20 corretores),
│                  fotos do acervo e documentos institucionais do RAG
├── scripts/          Utilitários de dev (`check_env.py`, `gerar_imoveis.py`,
│                  `semear_corretores.py`, `indexar_fotos.py`, `gerar_openapi.py`)
├── tests/            Suíte da raiz (hoje, a do `check_env`)
├── docs/             Arquitetura, ADRs, observabilidade e este portal
└── .github/          CI (GitHub Actions)
```

Não há diretório de infraestrutura como código: as stacks em nuvem foram removidas do repositório
quando a entrega passou a ser só o `docker compose` de `local/`.

## Scripts (`scripts/`)

| Script | Alvo do `make` | Opções |
| --- | --- | --- |
| `check_env.py` | `check-env`; `local` e `local-ollama` com `--gerar-segredo` | `[arquivo]` (padrão `local/.env`); `--gerar-segredo` grava um `SDR_SESSAO_SECRET` quando falta ou é o de exemplo |
| `checar_segredos.py` | `segredos` | `--env` (arquivo com os segredos reais, padrão `local/.env`), `--desde` (de onde varrer os commits, padrão `origin/master`) |
| `gerar_imoveis.py` | — | posicionais `[residenciais=250] [comerciais=150] [seed=42]`; determinístico |
| `indexar_fotos.py` | — | `--largura` (padrão 1200 px) e `--qualidade` (JPEG, padrão 78) das fotos do acervo |
| `semear_corretores.py` | `corretores` (com `--vincular-crm`) | `--vincular-crm` casa cada corretor com o usuário do CRM pelo e-mail; `--listar` só mostra o cadastro |
| `gerar_openapi.py` | `openapi` | `--verificar` falha se `docs/assets/openapi.json` estiver desatualizado (é o que a CI roda) |

Outros alvos úteis: `make docs` (instala `docs-requirements.txt` e sobe o portal com `mkdocs serve`),
`make docs-secos` (lista os documentos que o `make docs-kb` indexaria, com `--seco`, sem tocar no
banco), `make test-db` (só prepara os bancos de teste) e `make diagramas` (regera os SVG).

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
