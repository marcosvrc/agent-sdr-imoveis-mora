# Mora — Agente SDR Imobiliário da Vértice Imóveis

Prova de conceito (POC) de um SDR (Sales Development Representative) imobiliário com IA
generativa. A agente virtual **Mora** atende o cliente, entende o que ele procura, recomenda
imóveis do catálogo, agenda visitas e passa o lead qualificado para um corretor humano.

O repositório é um monorepo: cada componente vive na sua pasta, com dependências, testes e deploy
independentes, comunicando-se apenas por contratos definidos em `shared/`.

**Status:** POC (prova de conceito). A entrega roda inteira na máquina de quem avalia, por
`docker compose`; **nada está implantado**, e isso é escolha, não pendência — quem abre o
repositório sobe o sistema todo sem conta em provedor nenhum. Ver
[Funcionalidades](#4-funcionalidades-implementadas).

**CI:** GitHub Actions — testes de backend com cobertura (Python 3.12 + Postgres pgvector), harness
de avaliação com dublês e build + `eslint` dos front-ends (`web` e `dashboard`). Ver
[`.github/workflows/ci.yml`](.github/workflows/ci.yml).

> ## 📖 Documentação completa (portal)
>
> A documentação detalhada — arquitetura, manuais do agente/site/painel, referência da API, segurança,
> performance e operação — vive em um **portal publicado no GitHub Pages**:
>
> **➡️ https://<usuario-ou-organizacao>.github.io/agent-sdr-morai/** *(ajuste para o dono real do repositório)*
>
> Este `README` é o **guia rápido**; o portal é a fonte principal da documentação. O conteúdo do portal
> fica em [`docs/`](docs) e é construído com MkDocs Material (ver [`mkdocs.yml`](mkdocs.yml) e o workflow
> [`.github/workflows/docs.yml`](.github/workflows/docs.yml)).

**Documentação complementar:**
[Portal (GitHub Pages)](https://marcosvrc.github.io/agent-sdr-imoveis-mora/) · [Arquitetura](docs/ARCHITECTURE.md) · [ADRs](docs/adr) · [Ambiente local](local/README.md) · [Observabilidade](docs/quality/observabilidade.md) · [Como contribuir](docs/project/contribuir.md)

---

## Sumário

1. [Contexto do projeto](#3-contexto-do-projeto)
2. [Funcionalidades implementadas](#4-funcionalidades-implementadas)
3. [Tecnologias utilizadas](#5-tecnologias-utilizadas)
4. [Arquitetura da solução](#6-arquitetura-da-solução)
5. [Decisões tecnológicas](#7-decisões-tecnológicas)
6. [Pré-requisitos](#8-pré-requisitos)
7. [Configuração das variáveis de ambiente](#9-configuração-das-variáveis-de-ambiente)
8. [Como executar localmente](#10-como-executar-localmente)
9. [Manual de uso](#11-manual-de-uso)
10. [API](#12-api)
11. [Performance](#13-performance)
12. [Segurança e privacidade](#14-segurança-e-privacidade)
13. [Testes e qualidade](#15-testes-e-qualidade)
14. [Observabilidade e troubleshooting](#16-observabilidade-e-troubleshooting)
15. [Estrutura do repositório](#17-estrutura-do-repositório)
16. [Roadmap e limitações](#18-roadmap-e-limitações)
17. [Contribuição](#19-contribuição)
18. [Licença e responsáveis](#20-licença-e-responsáveis)
19. [Pendências de documentação](#21-pendências-de-documentação)

---

## 3. Contexto do projeto

**Problema.** No mercado imobiliário, o primeiro atendimento a um lead costuma ser lento e manual.
O corretor perde tempo qualificando contatos que ainda não estão prontos e demora a responder quem
já está. A proposta é automatizar a primeira etapa do funil (qualificação e recomendação) com uma
assistente virtual, entregando ao corretor apenas leads já qualificados, com um resumo pronto.

**Público-alvo.** Imobiliárias de pequeno e médio porte (o desenho assume escritório único) e seus
corretores, que usam o painel administrativo. O cliente final conversa com a Mora pelo site ou pelo
Telegram.

**Objetivos principais.**
- Qualificar o lead em uma conversa natural (intenção, região, faixa de preço, quartos, urgência).
- Recomendar imóveis do catálogo por busca semântica (RAG) calibrada por localidade.
- Agendar visitas e encaminhar o lead qualificado ao corretor (handoff), com briefing automático.
- Dar ao corretor visibilidade do funil, das conversas e do custo de IA por meio de um painel.

**Proposta de valor.** Resposta imediata 24h, qualificação consistente e um painel que mostra o
funil e a governança de consumo de LLM (Large Language Model, modelo de linguagem).

**Escopo atual (POC).** Agente multiagente, site vitrine com chat, painel do corretor, canal
Telegram, API REST, RAG híbrido, follow-up automático, governança de IA e uma camada de segurança
determinística contra abuso de prompt.

**Fora do escopo (avaliado e cortado — ver [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#8-o-que-ficou-fora-avaliado-e-cortado)).**
App nativo (o PWA cobre), Voice AI em tempo real, multi-tenant e o canal WhatsApp — que exigia
número de negócio verificado e webhook com URL pública, e por isso foi removido do código em favor
do Telegram ([ADR-0007](docs/adr/0007-telegram-em-vez-de-whatsapp.md)).

---

## 4. Funcionalidades implementadas

A tabela abaixo reflete o estado descrito no repositório. Legenda: **Concluída** (implementada e com
teste ou build associado), **Parcial** (escrita, mas sem teste automatizado ou dependente de serviço
externo), **Planejada** (prevista, não implementada).

### Agente de IA (`services/agent`)
| Funcionalidade | Estado | Evidência |
|---|---|---|
| Grafo multiagente (supervisor, qualificador, consultor, agendador, follow-up, handoff, resumidor, reativador) | Concluída | `tests/test_cenarios.py` |
| Reativação proativa: imóvel novo → leads adormecidos, com motivo, cadência e opt-out | Concluída | ADR-0013, `tests/test_reativacao_fluxo.py` |
| RAG híbrido de imóveis com cascata por localidade (bairro → vizinhos → região → cidade) | Concluída | `tools/buscar_imoveis.py`, `test_cenarios.py` |
| Agendamento de visita em dois turnos (oferta de horários → confirmação) | Concluída | `nodes/agendador.py` |
| Scoring de temperatura do lead (quente/morno/frio) | Concluída | `test_cenarios.py` |
| Guardrails de escopo, saneamento de saída e rate limiting | Concluída | `tests/test_seguranca.py` |
| Governança de LLM: registro por chamada, custo por modelo, orçamento com degradação | Concluída | `tests/test_governanca.py` |
| Transcrição de voz do Telegram com `faster-whisper` no próprio processo | Concluída | `tools/transcricao.py`, `tests/test_transcricao.py` |
| RAG institucional sobre pgvector (piso de similaridade, reescrita de consulta) | Concluída | `shared/sdr_shared/conhecimento.py`, `tools/conhecimento.py` |
| Fusão léxica (RRF) no RAG institucional | Parcial | implementada e testada, **desligada** por padrão atrás de `SDR_RAG_LEXICO`: o A/B piorou o recall (31,9% → 29,8%) |

### Site (`apps/web`)
| Funcionalidade | Estado | Evidência |
|---|---|---|
| Landing com widget de chat, listagem, detalhe do imóvel, busca e filtros | Concluída | `npm run build` (TypeScript estrito) |
| PWA, tracking de navegação, SEO/acessibilidade | Concluída | ADR-0012, `vite-plugin-pwa` |
| CTA de continuidade no Telegram (mantém histórico) | Concluída | ADR-0006 |

### Painel administrativo (`apps/dashboard`)
| Funcionalidade | Estado | Evidência |
|---|---|---|
| Visão geral, leads, conversas ao vivo, agenda, imóveis, corretores | Concluída | `npm run build` |
| Configurações do agente e governança de IA (tokens, custos, limites) | Concluída | `routers/config.py`, `routers/governanca.py` |
| Auditoria e aba de saúde do sistema (observabilidade leve) | Concluída | ADR-0011, `routers/auditoria.py`, `routers/dashboard.py` |

### Backend, integrações e execução
| Funcionalidade | Estado | Evidência |
|---|---|---|
| API REST (imóveis públicos, leads, dashboard, handoff, eventos, config, governança, auditoria) | Concluída | `services/api`, `tests/test_api.py` |
| Canal Telegram (long polling, `getUpdates`) | Concluída | `services/channels/telegram` |
| Canal Web (WebSocket) | Concluída | `services/channels/local` |
| Follow-up automático e ingestão de imóveis | Concluída | `services/scheduler`, `services/ingestion` |
| Ponte com o CRM por MCP sobre HTTP | Concluída | `services/crm`, `shared/sdr_shared/adapters/crm/via_mcp.py` |
| Integração Google Agenda do corretor | Parcial | `tools/agenda.py`, `adapters/google/calendario.py`; opcional, degrada para a agenda do próprio banco |
| Ambiente completo em `docker compose` (banco, fila, workers, canais, API, front-ends e CRM) | Concluída | [`local/docker-compose.yml`](local/docker-compose.yml) |

> As funcionalidades marcadas como **Parcial** não devem ser tratadas como prontas para produção.

---

## 5. Tecnologias utilizadas

Versões obtidas dos arquivos do projeto (`package.json`, `pyproject.toml`, `settings.py`,
`local/docker-compose.yml`, `.github/workflows/ci.yml`). Onde a versão não está fixada no
repositório, consta `A confirmar`.

| Categoria | Tecnologia | Versão | Finalidade |
|---|---|---:|---|
| Frontend | React | ^18.3.1 | Interface do site e do painel |
| Frontend | Vite | ^5.4.0 | Build e servidor de desenvolvimento |
| Frontend | TypeScript | ^5.5.3 | Tipagem estática (build estrito) |
| Frontend | Tailwind CSS | ^3.4.0 | Estilos |
| Frontend | TanStack React Query | ^5.51.0 | Cache e sincronização de dados |
| Frontend | Zustand | ^4.5.0 | Estado do chat (site) |
| Frontend | Recharts | ^2.12.0 | Gráficos do painel |
| Frontend | vite-plugin-pwa | ^0.20.0 | PWA do site |
| Backend | Python | 3.12 | Linguagem dos serviços |
| Backend | FastAPI | >=0.115 | API REST e app de canal (HTTP + WebSocket) |
| LLM/IA | LangGraph | >=0.2 | Orquestração do grafo multiagente |
| LLM/IA | LangChain Core | >=0.3 | Abstrações de mensagens/modelos |
| LLM/IA | Anthropic — Claude Sonnet | `claude-sonnet-4-5` (padrão, ajustável) | Conversa com o cliente |
| LLM/IA | Anthropic — Claude Haiku | `claude-haiku-4-5` (padrão, ajustável) | Roteamento e extração |
| LLM/IA | Provedores aceitos | — | `anthropic` (padrão), `openai` e `ollama`, via `SDR_LLM_PROVIDER`; reserva em `SDR_LLM_PROVIDER_FALLBACK` |
| RAG/Embeddings | Ollama bge-m3 | 1024 dims | Provedor único de embeddings — é o que dá as dimensões que o schema espera |
| RAG | pgvector no mesmo Postgres | — | Imóveis e documentos institucionais (ADR-0001) |
| Áudio | faster-whisper | in-process | Transcreve a voz do Telegram; `SDR_TRANSCRICAO_PROVIDER` |
| Banco de dados | PostgreSQL + pgvector | `pgvector/pgvector:pg16` | Dados relacionais + vetores, na mesma base (ADR-0004) |
| Fila / assíncrono | Redis Streams | `redis:7-alpine` | Tópicos e locks entre canais, agente e scheduler |
| Autenticação | Token estático `SDR_PAINEL_TOKEN` | — | Acesso ao painel e ao WebSocket `papel=dashboard` (ADR-0008) |
| Integração | MCP sobre HTTP | `services/crm` | Ponte da Mora com o CRM da imobiliária |
| Containers | Docker + Docker Compose | — | Todo o ambiente de execução |
| CI/CD | GitHub Actions | — | `ruff`, cobertura, harness com dublês, build + `eslint` dos front-ends |
| Observabilidade | Postgres (tabelas de saúde) + `/health` + logs JSON | — | Observabilidade leve (ADR-0011) |
| Observabilidade | Langfuse | `langfuse/langfuse:2` | Tracing de LLM (opcional, `--profile observability`) |
| Testes | pytest | — | Testes de backend |

---

## 6. Arquitetura da solução

### Visão geral

O sistema separa o **cérebro** (o agente) dos **canais** (Telegram, web, CLI). O agente não sabe por
qual canal a mensagem chegou: cada canal traduz `evento do provedor → MensagemNormalizada` e
`RespostaAgente → formato do canal`. A única dependência cruzada permitida é o pacote `shared/`.

Tudo roda como container no [`local/docker-compose.yml`](local/docker-compose.yml). Cada dependência
externa entra por uma porta (`shared/sdr_shared/ports`), resolvida por
`shared/sdr_shared/adapters/`; hoje broker, scheduler e embeddings têm uma implementação cada, e
`SDR_PROFILE` decide apenas se o token estático de desenvolvimento vale.

```mermaid
flowchart LR
  subgraph Entrada["Porta de entrada"]
    SITE["apps/web<br/>site vitrine + chat (:5173)"]
    TG["Telegram<br/>Bot API (long polling)"]
  end

  subgraph Canais["services/channels"]
    CH["channels :8001<br/>HTTP + WebSocket (local)"]
    TGW["telegram-in / telegram-out"]
  end

  Q[["Redis Streams<br/>tópicos e locks"]]

  subgraph Agente["services/agent — grafo LangGraph"]
    SUP["Supervisor"]
    NODES["Qualificador · Consultor<br/>Agendador · Follow-up<br/>Handoff · Resumidor<br/>Reativador"]
    SUP --> NODES
  end

  LLM["LLM<br/>Anthropic · OpenAI · Ollama"]
  DB[("Postgres 16 + pgvector<br/>container db")]
  CRM["crm-mcp :8200<br/>servidor MCP do CRM"]
  API["services/api :8000<br/>FastAPI"]
  DASH["apps/dashboard :5174<br/>painel do corretor"]

  SITE --> CH
  TG --> TGW
  CH --> Q
  TGW --> Q
  Q --> Agente
  Agente --> LLM
  Agente --> DB
  Agente --> CRM
  Agente -->|resposta neutra| Q
  Q --> CH
  Q --> TGW
  API --> DB
  DASH --> API
  DASH -->|tempo real| CH
```

**Componentes e responsabilidades.**
- **`apps/web`** — site vitrine, catálogo e widget de chat; porta de entrada do cliente.
- **`apps/dashboard`** — painel do corretor (funil, conversas, agenda, imóveis, governança, auditoria).
- **`services/channels/local`** — chat do site: HTTP + WebSocket (`:8001`).
- **`services/channels/telegram`** — long polling de entrada e worker de saída.
- **`services/agent`** — grafo multiagente; único componente que fala com o LLM.
- **`services/api`** — API REST (imóveis públicos, leads, dashboard, handoff, config, governança).
- **`services/scheduler`** — follow-up automático (agenda e cancela por lead).
- **`services/ingestion`** — carga de imóveis e documentos, e geração de embeddings.
- **`services/crm`** — o CRM da imobiliária: sistema à parte, com banco próprio, API REST e o
  servidor MCP por onde a Mora entra.
- **`shared/`** — modelos, contratos, repositórios (SQL + pgvector), portas e adaptadores.
- **`local/`** — o `docker-compose.yml` que sobe tudo isso.

### Fluxo principal de atendimento (máquina de estados do lead)

```mermaid
stateDiagram-v2
  [*] --> Novo: primeira mensagem / navegação no site
  Novo --> Qualificando: intenção identificada
  Qualificando --> Qualificando: preenche cartão (região, preço, quartos, urgência)
  Qualificando --> Inativo: sem resposta (2h / 24h / 72h)
  Inativo --> Qualificando: follow-up respondido
  Inativo --> Frio: 3 follow-ups sem resposta
  Qualificando --> Qualificado: cartão completo + score
  Qualificado --> Agendado: visita marcada
  Qualificado --> Handoff: corretor assume
  Agendado --> Handoff: resumo gerado para o corretor
  Handoff --> [*]
```

O **cartão de qualificação** (`shared/sdr_shared/models/lead.py`) é a fonte da verdade: a cada turno o
qualificador recebe a lista de campos faltantes e conduz a conversa para preenchê-los. O score de
temperatura deriva do cartão mais sinais de comportamento (tempo de resposta, pediu visita, abriu
imóveis no site).

### Fluxo do agente / LLM

```mermaid
flowchart TD
  MSG["MensagemNormalizada"] --> ESCOPO{"Guardrail de escopo<br/>(determinístico)"}
  ESCOPO -->|fora do escopo / injeção| RECUSA["Recusa (texto fixo)<br/>sem chamar o LLM"]
  ESCOPO -->|ok| SUP{"Supervisor<br/>roteamento"}
  SUP -->|regra determinística| NODE["Nó especialista"]
  SUP -->|ambíguo| HAIKU["Haiku decide<br/>(saída restrita a 4 nós)"]
  HAIKU --> NODE
  NODE --> RAG["RAG de imóveis<br/>(quando consultor)"]
  NODE --> LLMCALL["Chamada ao LLM<br/>com persona + blindagem"]
  LLMCALL --> SANEAR["Saneamento de saída<br/>(vazamento, PII, links)"]
  SANEAR --> RESP["RespostaAgente"]
```

O texto do cliente nunca é concatenado cru no prompt: entra em um bloco delimitado por sentinela
aleatória, com um cabeçalho de blindagem que instrui o modelo a tratá-lo como dado, não instrução. A
resposta do modelo passa por um saneamento final antes de virar mensagem. Detalhes em
[Segurança e privacidade](#14-segurança-e-privacidade).

### Diagrama de execução (docker compose)

```mermaid
flowchart TB
  subgraph Host["Máquina de quem avalia (docker compose)"]
    subgraph Front["Front-ends (Vite)"]
      W["web :5173"]
      D["dashboard :5174"]
      CW["crm-web :3000"]
    end
    A["api :8000"]
    C["channels :8001 (HTTP + WS)"]
    AG["agent (worker)"]
    RS["resumidor (worker)"]
    RT["reativador (worker)"]
    SC["scheduler (worker)"]
    TI["telegram-in / telegram-out<br/>(long polling)"]
    CA["crm-api :8100"]
    CM["crm-mcp :8200"]
    PG[("db :5433 → 5432<br/>Postgres + pgvector<br/>bancos sdr e crm")]
    RD[("redis :6380 → 6379")]
    OL[("ollama :11435<br/>--profile ollama")]
    LF["langfuse :3000<br/>--profile observability"]
  end
  W --> A
  W --> C
  D --> A
  D --> C
  CW --> CA
  A --> PG
  C --> RD
  AG --> RD
  AG --> PG
  AG --> OL
  AG --> CM
  RS --> RD
  RT --> RD
  SC --> RD
  SC --> PG
  TI --> RD
  CM --> CA
  CA --> PG
```

As portas do host (5433, 6380, 11435) são deslocadas para não colidir com instâncias nativas de
Postgres, Redis e Ollama e podem ser ajustadas por `DB_HOST_PORT`, `REDIS_HOST_PORT` e
`OLLAMA_HOST_PORT`. O `crm-web` e o Langfuse disputam a porta 3000 — não suba os dois ao mesmo
tempo. Ver [`local/README.md`](local/README.md).

---

## 7. Decisões tecnológicas

Cada decisão está registrada como ADR (Architecture Decision Record) em [`docs/adr`](docs/adr).
Resumo das principais:

- **RAG sobre Postgres + pgvector, com fusão de ranking** ([ADR-0001](docs/adr/0001-rag-com-postgres-pgvector.md)).
  Imóvel e documento institucional no mesmo banco que o painel consulta, com piso de similaridade
  (0,35) e reescrita de consulta. **Trade-off:** a fusão léxica (RRF) está implementada mas
  desligada por padrão (`SDR_RAG_LEXICO`) — o A/B piorou o recall (31,9% → 29,8%).
- **Runtime do agente: container local consumindo uma fila** ([ADR-0002](docs/adr/0002-runtime-do-agente-em-container.md)).
  Um turno leva de 20 a 40 segundos e não cabe no fio da requisição HTTP; o agente é um worker que
  consome o tópico `inbound` e publica na saída do canal.
- **Canais como adaptadores sem lógica** ([ADR-0003](docs/adr/0003-canais-como-adaptadores.md)).
  Permite trocar/adicionar canal sem tocar no agente.
- **Um Postgres para tudo, em vez de um banco por finalidade** ([ADR-0004](docs/adr/0004-postgres-como-banco-unico.md)).
  Registro transacional, vetores, agregação do painel e o checkpointer do grafo na mesma base.
- **Telegram em vez de WhatsApp como canal externo** ([ADR-0007](docs/adr/0007-telegram-em-vez-de-whatsapp.md)).
  Bot criado na hora pelo `@BotFather` e long polling, sem verificação de negócio e sem URL
  pública. O WhatsApp saiu do código: voltar significa escrever o adaptador de novo.
- **Cada porta privada carrega o seu próprio portão** ([ADR-0008](docs/adr/0008-portoes-de-autenticacao-proprios.md)).
  Sem gateway único na frente, cada porta privada (API e WebSocket do painel) confere a credencial
  por conta própria.
- **Modelo por nível, editável no painel** ([ADR-0010](docs/adr/0010-modelo-por-nivel-e-troca-pelo-painel.md)).
  Sonnet na conversa, Haiku em roteamento/extração; ajustável sem redeploy.
- **Observabilidade leve no Postgres** ([ADR-0011](docs/adr/0011-observabilidade-leve-no-postgres.md)),
  que **revogou** a stack OpenTelemetry+Grafana ([ADR-0005](docs/adr/0005-observabilidade-com-opentelemetry-e-grafana.md))
  por consumo de recursos na máquina de desenvolvimento.

---

## 8. Pré-requisitos

**Para subir o ambiente (é o único caminho — não há nada implantado):**
- Git.
- Docker e Docker Compose.
- Chave do provedor de LLM escolhido (`ANTHROPIC_API_KEY` ou `OPENAI_API_KEY`) — ou Ollama, para
  rodar 100% local e sem custo, aceitando qualidade de conversa menor.
- (Opcional) Token de bot do Telegram, obtido no `@BotFather`, para exercitar o canal externo. Sem
  ele a Mora ainda atende pelo chat do site e pela CLI.

**Para rodar os testes de backend ou executar serviços fora do compose:**
- Python **3.12** (a versão da CI).
- `pip` ou [`uv`](https://docs.astral.sh/uv/) como gerenciador de pacotes (o `Makefile` usa `uv`).
- Node.js **20** para os front-ends.

> Requisitos de hardware mínimo/recomendado: `A confirmar`. O uso de Ollama local aumenta bastante o
> consumo de CPU/RAM (ver [`docs/quality/observabilidade.md`](docs/quality/observabilidade.md)).

---

## 9. Configuração das variáveis de ambiente

As variáveis do agente usam o prefixo `SDR_`; as chaves de provedor (`ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`) e as do CRM (`CRM_MCP_TOKEN`, `CRM_API_TOKEN`) não, porque são os nomes que as
bibliotecas e o servidor MCP procuram. O arquivo de referência é [`.env.example`](.env.example); o
ambiente do compose tem o seu em [`local/.env.example`](local/.env.example). Os valores abaixo são
**fictícios** — não use segredos reais no repositório.

Crie seu arquivo a partir do exemplo:

```bash
cp .env.example .env                    # execução fora do compose
cp -n local/.env.example local/.env     # docker compose (-n não sobrescreve o que já existe)
make check-env                          # confere o local/.env antes de subir nada
```

| Variável | Obrigatória | Exemplo seguro | Descrição |
|---|---|---|---|
| `SDR_ENV` | Não | `dev` | Ambiente lógico. Padrão `dev`. |
| `SDR_PROFILE` | Não | `local` | `local` (padrão) ou `producao`. Decide **uma** coisa: se o token estático de desenvolvimento vale. |
| `SDR_DATABASE_DSN` | Sim | `postgresql://sdr:sdr@localhost:5432/sdr` | DSN do Postgres. |
| `SDR_LLM_PROVIDER` | Não | `anthropic` | `anthropic` (padrão), `openai` ou `ollama`. Outro valor levanta erro explicando. |
| `SDR_LLM_PROVIDER_FALLBACK` | Não | `openai` | Provedor de reserva quando o primário falha. Vazio = sem reserva. |
| `SDR_MODEL_CONVERSA` | Não | `claude-sonnet-4-5` | Modelo da conversa. |
| `SDR_MODEL_ROTEAMENTO` | Não | `claude-haiku-4-5` | Modelo de roteamento/extração. |
| `SDR_ANTHROPIC_WORKSPACE_ID` | Não | `wrkspc_exemplo` | Só para chave de organização; chave já escopada deixa vazio. |
| `SDR_EMBEDDINGS_PROVIDER` | Não | `ollama` | Único valor aceito: o `bge-m3` dá as 1024 dimensões que o schema espera. |
| `SDR_OLLAMA_EMBEDDING_MODEL` | Não | `bge-m3` | Trocar exige alterar `shared/sdr_shared/db/schema.sql`. |
| `SDR_OLLAMA_URL` | Não | `http://localhost:11434` | Endereço do Ollama (no compose, `http://ollama:11434`). |
| `SDR_RAG_LEXICO` | Não | *(vazio)* | `1` liga a fusão léxica (RRF) do RAG institucional, desligada por padrão. |
| `SDR_TRANSCRICAO_PROVIDER` | Não | `auto` | `auto`, `whisper_local` ou `off` (não transcreve; o cliente é convidado a escrever). |
| `SDR_WHISPER_MODEL` | Não | `small` | Tamanho do modelo faster-whisper (`tiny`…`large-v3`). |
| `SDR_LLM_TIMEOUT_S` | Não | `45` | Timeout por turno; acima disso o cliente recebe o fallback. |
| `SDR_REDIS_URL` | Não | `redis://localhost:6379/0` | Fila (no compose, `redis://redis:6379/0`). |
| `SDR_TELEGRAM_BOT_TOKEN` | Não | `000000:exemplo-token` | Token do bot, do `@BotFather`. Sem ele, sobram o chat do site e a CLI. |
| `SDR_TELEGRAM_BOT_USERNAME` | Não | `mora_vertice_bot` | Usuário do bot, para montar o link `t.me/<usuario>`. |
| `SDR_SESSAO_SECRET` | Recomendada | `troque-por-uma-string-aleatoria-longa` | Assina a sessão do chat do site. Sem valor, as sessões caem a cada reinício. |
| `SDR_PAINEL_TOKEN` | Sim (fora do perfil `local`) | `exemplo-token-painel` | Credencial do painel na API e no WebSocket `papel=dashboard`. No perfil `local`, vazio vira `dev-token`; fora dele, vazio não aceita ninguém. |
| `SDR_PUBLIC_API_URL` | Não | `http://localhost:8000` | Base para montar a URL absoluta das fotos (`/fotos/...`) fora da API. |
| `SDR_CRM_URL` | Não | `http://crm-mcp:8200/mcp` | Endpoint do servidor **MCP** do CRM (não a REST). Vazio = ponte desligada. |
| `SDR_CRM_TOKEN` | Não | *(o valor de `CRM_MCP_TOKEN`)* | Credencial do agente no servidor MCP. |
| `SDR_CORS_ORIGINS` | Recomendada (produção) | `https://app.exemplo.com` | Origens permitidas na API, separadas por vírgula. Vazio = `*` (só em dev). |
| `SDR_GOOGLE_CLIENT_ID` | Não | `exemplo.apps.googleusercontent.com` | OAuth do Google Agenda (opcional). |
| `SDR_GOOGLE_CLIENT_SECRET` | Não | `exemplo-secret` | OAuth do Google Agenda (opcional). |
| `SDR_GOOGLE_REDIRECT_URI` | Não | `http://localhost:8000/calendario/callback` | URI de retorno do OAuth. |

Duas variáveis sem o prefixo `SDR_` completam a ponte com o CRM, e trocá-las uma pela outra dá 401
sem explicação: **`CRM_API_TOKEN`** é a credencial do servidor MCP na REST do CRM (emitida por
`make crm-token`) e **`CRM_MCP_TOKEN`** é a credencial de quem se conecta ao servidor MCP.

Sem `SDR_GOOGLE_*`, a Mora usa a grade interna de horários e as visitas continuam sendo marcadas.
Sem `CRM_MCP_TOKEN`, a Mora roda sozinha, sem CRM.

---

## 10. Como executar localmente

### Opção A — Docker Compose (caminho recomendado)

```bash
# 1. Clonar e entrar no diretório
git clone <url-do-repositorio>
cd agent-sdr-morai

# 2. Configurar o ambiente e conferir antes de subir nada
cp -n local/.env.example local/.env
# edite local/.env: ANTHROPIC_API_KEY e, se for usar o CRM, CRM_MCP_TOKEN
make check-env

# 3. Subir tudo, em primeiro plano. `make local` sobe o mesmo sem o serviço do Ollama.
make local-ollama
# equivalente a: cd local && docker compose --profile ollama up --build

# --- daqui em diante, em OUTRO terminal, com o compose no ar ---

# 4. Bancos e massa, na ordem das dependências
make preparar

# 5. Credencial da Mora no CRM (aparece uma vez; cole em CRM_API_TOKEN no local/.env)
make crm-token
cd local && docker compose up -d crm-mcp agent && cd ..

# 6. Índices: acervo e documentos institucionais
make ollama-pull      # baixa o bge-m3 (embeddings); demora, uma vez só
make seed
make docs-kb

# 7. Encerrar o ambiente
cd local && docker compose down          # use down -v para apagar também os volumes (Postgres/Ollama)
```

`make` sozinho imprime essa ordem — é o alvo padrão, e é a fonte que se mantém em dia com o
Makefile.

`make local` e `make local-ollama` executam `scripts/check_env.py` antes de subir.

**Sobre o schema:** `local/00-crm.sql` e `shared/sdr_shared/db/schema.sql` estão montados em
`docker-entrypoint-initdb.d`, mas o Postgres só executa esses scripts quando o **volume é novo**.
Num volume que já existia — o caso de quem acompanha o projeto há algum tempo — eles nunca rodam, e
o sintoma é `FATAL: database "crm" does not exist` sem nada explicando a causa. Por isso `make
preparar` cria e aplica tudo explicitamente, e é idempotente: rodar de novo não estraga nada.

**Sem CRM:** a Mora roda sozinha. Pule os passos 4 e 5 (exceto `make migrate`, que o `preparar`
inclui) e siga para o 6.

### Opção B — Execução fora do compose (desenvolvimento)

Requer Postgres com pgvector acessível e Python 3.12. Instale as dependências e aplique o schema:

```bash
make setup                                # instala serviços (uv/pip) e front-ends (npm)
psql "$SDR_DATABASE_DSN" -f shared/sdr_shared/db/schema.sql
```

Suba cada processo em um terminal (os comandos espelham o `local/docker-compose.yml`):

```bash
# API REST
cd services/api/src && uvicorn api.main:app --port 8000 --reload

# Canais (HTTP + WebSocket)
cd services/channels/local && uvicorn app:app --port 8001 --reload

# Agente (worker)
cd services/agent/src && python -c "from agent.handler import local_worker; local_worker()"

# Front-ends
cd apps/web && npm run dev
cd apps/dashboard && npm run dev -- --port 5174
```

Uma alternativa via linha de comando, sem canais externos, é a CLI do agente:

```bash
make cli                                  # conversa com a Mora no terminal
```

### Sobre implantação

Não há ambiente implantado, e isso é uma escolha: a entrega roda inteira na máquina de quem avalia,
com `docker compose`, sem conta em provedor de nuvem, sem túnel e sem URL pública. O que existiu de
infraestrutura como código foi removido do repositório junto com os adaptadores que a acompanhavam
([ADR-0002](docs/adr/0002-runtime-do-agente-em-container.md)).

### Serviços e portas

| Serviço | URL local | Porta | Health check |
|---|---|---:|---|
| Site (PWA) | http://localhost:5173 | 5173 | — (Vite dev server) |
| Painel | http://localhost:5174 | 5174 | — (Vite dev server) |
| API | http://localhost:8000 | 8000 | `GET /health` (503 quando degradado) |
| API (OpenAPI) | http://localhost:8000/docs | 8000 | — |
| Canais (HTTP/WS) | http://localhost:8001 · ws://localhost:8001/ws | 8001 | `GET /health` (503 se o Redis cair) |
| Agente | worker (sem HTTP) | — | via tabela de saúde no Postgres (ADR-0011) |
| CRM — API | http://localhost:8100 | 8100 | `GET /health/ready` |
| CRM — servidor MCP | http://localhost:8200/mcp | 8200 | `GET /saude` |
| CRM — painel | http://localhost:3000 | 3000 | — (Vite dev server) |
| Langfuse (opcional) | http://localhost:3000 | 3000 | — (mesma porta do painel do CRM) |
| Postgres / Redis / Ollama | host: 5433 / 6380 / 11435 | — | `pg_isready` (db) |

Validação rápida após subir:

```bash
curl -s http://localhost:8000/health      # {"ok": true, "agente": "Mora", ...}
curl -s "http://localhost:8000/imoveis?limite=3"
```

---

## 11. Manual de uso

### 11.1 Agente (Mora)

- **Como iniciar.** Abra o site (`http://localhost:5173`) e clique em "Falar com a Mora", ou envie
  uma mensagem ao bot do Telegram configurado. A Mora se apresenta na primeira mensagem.
- **Capacidades.** Entende intenção (comprar, alugar, investir), coleta região, faixa de preço,
  quartos e urgência, recomenda imóveis do catálogo com explicação, oferece horários de visita e
  encaminha para um corretor quando solicitado.
- **Exemplos de mensagens.**
  - "Quero um apartamento de 2 quartos em Pinheiros até 700 mil."
  - "Tem casa para alugar até 3 mil na zona sul?"
  - "Quero investir, qual a rentabilidade?"
  - "Gostaria de agendar uma visita."
  - "Quero falar com um corretor."
- **Comportamento esperado.** Respostas curtas (até 3 frases), uma pergunta por vez, sem inventar
  imóveis, preços ou disponibilidade. Assuntos fora do mercado imobiliário são recusados com
  educação e a conversa é reconduzida.
- **Reiniciar/encerrar.** No site, a sessão é anônima e vinculada a um `session_id`; recarregar ou
  limpar o armazenamento do navegador inicia uma nova conversa. No Telegram, a conversa segue o
  histórico do chat.
- **Respostas incorretas.** Se a resposta não fizer sentido ou o cliente insistir fora do escopo, a
  Mora oferece o contato de um corretor humano. Falhas técnicas encaminham automaticamente ao corretor.
- **Uso responsável.** A Mora é uma assistente de demonstração; o conteúdo gerado deve ser conferido
  por um corretor antes de qualquer compromisso comercial.

### 11.2 Site

- **Acesso.** `http://localhost:5173` (não requer login).
- **Navegação.** Página inicial com destaques, catálogo (`/imoveis`), detalhe do imóvel e favoritos.
- **Pesquisa e filtros.** Busca por texto e filtros por operação (venda/aluguel), região, faixa de
  preço e quartos.
- **Resultados.** Cards com foto, preço e características; a página de detalhe traz galeria e CTA para
  conversar com a Mora sobre aquele imóvel.
- **Jornadas principais.** Buscar imóvel → abrir detalhe → conversar com a Mora → agendar visita, ou
  continuar a conversa no Telegram mantendo o contexto.

### 11.3 Painel administrativo

- **Acesso e autenticação.** `http://localhost:5174`. A autenticação é um token estático
  (`SDR_PAINEL_TOKEN`), que vale tanto para o header `Authorization` da API quanto para a conexão
  WebSocket `papel=dashboard`. No perfil `local`, vazio vira `dev-token`; fora dele, vazio não
  aceita nada (ADR-0008).
- **Perfis e permissões.** A API distingue rotas públicas, de corretor, de administração e de
  operação (ver tags em [API](#12-api)). O detalhamento de papéis por usuário é `A confirmar`.
- **Cadastro e manutenção.** Gestão de imóveis (incluindo upload/reordenação de fotos), corretores e
  configurações do agente.
- **Configuração do agente.** Ajuste de follow-up, agenda, área de cobertura, handoff e modelos de IA
  por nível — sem redeploy (ADR-0010).
- **Acompanhamento.** Funil de leads, conversas ao vivo, ficha do cliente e agenda de visitas.
- **Dashboards e governança.** Visão geral com KPIs e a aba de governança de IA (tokens, custo por
  modelo, limites e orçamento com degradação automática).
- **Auditoria.** Registro de tudo que altera o sistema, com exportação.
- **Operações sensíveis.** Assumir/devolver lead e responder pelo corretor enviam mensagens reais aos
  canais do lead; alterar limites de orçamento afeta o comportamento do agente (degradar/bloquear).

> Não utilize credenciais reais no repositório nem em exemplos.

---

## 12. API

- **URL base (local):** `http://localhost:8000`
- **Documentação interativa (OpenAPI):** `http://localhost:8000/docs`
- **Autenticação:** rotas de corretor/admin exigem `Authorization: Bearer <SDR_PAINEL_TOKEN>` (em
  desenvolvimento, `dev-token`) — o botão **Authorize** do Swagger aceita o mesmo valor. Rotas
  públicas (`/imoveis`, `/eventos`, `/fotos/...`) não exigem credencial.

Endpoints essenciais (a lista completa está no OpenAPI):

| Método | Rota | Acesso | Descrição |
|---|---|---|---|
| GET | `/health` | público | Saúde do sistema; 503 quando degradado. |
| GET | `/imoveis` | público | Lista imóveis com filtros (`operacao`, `regiao`, `preco_max`, `quartos`, `limite`). |
| GET | `/imoveis/busca` | público | Busca com filtros adicionais (bairro etc.). |
| GET | `/imoveis/{imovel_id}` | público | Detalhe do imóvel. |
| POST | `/eventos` | público | Registra evento de navegação do site (alimenta o cartão do lead). |
| GET | `/leads` | corretor | Lista leads por estágio/temperatura/corretor. |
| GET | `/leads/{lead_id}` | corretor | Detalhe do lead. |
| POST | `/leads/{lead_id}/analisar` | corretor | Solicita novo briefing/análise (assíncrono). |
| POST | `/handoff/{lead_id}/assumir` | corretor | Corretor assume a conversa. |
| POST | `/handoff/{lead_id}/responder` | corretor | Envia mensagem do corretor pelos canais do lead. |
| GET | `/dashboard/metricas` | corretor | KPIs do período com variação. |
| GET | `/governanca/uso` | admin | Consumo de LLM (tokens, custo, série diária). |
| GET | `/auditoria` | admin | Registro de auditoria. |

Exemplo de requisição/resposta (valores ilustrativos):

```bash
curl -s "http://localhost:8000/imoveis?operacao=venda&quartos=2&limite=1"
```

```json
[
  {
    "id": "IMOVEL-001",
    "titulo": "Apartamento 2q · Moema",
    "preco": 800000,
    "bairro": "Moema",
    "operacao": "venda"
  }
]
```

**Códigos de status e erros.** A API usa os padrões do FastAPI: `200/201/202/204` para sucesso,
`401` para não autenticado, `404` para recurso inexistente e `503` no `/health` quando degradado.

> Consulte o OpenAPI em `/docs` para o contrato completo; este README lista apenas o essencial.

---

## 13. Performance

Estratégias observadas no código e na configuração:

- **Roteamento econômico.** Roteamento e extração usam Haiku; a conversa usa Sonnet (ADR-0010) — reduz
  custo e latência por turno.
- **Roteamento determinístico primeiro.** O supervisor decide por regra e só chama o LLM na ambiguidade.
- **RAG híbrido com cascata por localidade.** Evita buscas amplas desnecessárias.
- **Timeout de LLM.** `SDR_LLM_TIMEOUT_S` (padrão 45s); ao estourar, o cliente recebe fallback e o
  lead é encaminhado ao corretor.
- **Provedor de fallback.** `SDR_LLM_PROVIDER_FALLBACK` assume quando o primário falha.
- **Governança de orçamento.** Ao estourar o limite, o agente degrada (modelo econômico) ou bloqueia
  (encaminha ao corretor).
- **Rate limiting por lead.** 5 mensagens/10s e 60 mensagens/hora (`guardrails/vazao.py`).
- **Cache de dados no front-end.** TanStack React Query.
- **Cache HTTP de imagens.** `Cache-Control: public, max-age=86400` nas fotos.
- **Paginação/limite.** Endpoints de listagem aceitam `limite` com teto (ex.: imóveis até 200).

**Benchmarks.** Não há benchmarks de desempenho medidos e versionados no repositório. Procedimento
reprodutível sugerido para obtê-los:

1. Subir o ambiente e popular o catálogo (`make local-ollama`, depois `make preparar` e `make seed`).
2. Medir a latência ponta a ponta de um turno com um provedor fixo (ex.: Anthropic API) capturando o
   `duracao_ms` já registrado nos logs do agente e na tabela de saúde (ADR-0011).
3. Repetir por cenário (qualificação, consulta com RAG, agendamento) e registrar p50/p95.

| Cenário | Métrica | Resultado | Ambiente |
|---|---|---:|---|
| — | — | A confirmar | A confirmar |

---

## 14. Segurança e privacidade

Legenda: **Implementado**, **Parcial**, **Recomendado**. A existência de um controle não implica que o
sistema seja seguro para produção — esta é uma POC.

| Controle | Estado | Detalhe |
|---|---|---|
| Autenticação do painel | Implementado | Token estático `SDR_PAINEL_TOKEN` na API e no WebSocket, fail-closed fora do perfil `local` — ADR-0008 |
| Autorização por área | Implementado | Rotas separadas (público/corretor/admin/operação) |
| Sessão assinada do chat do site | Implementado | `SDR_SESSAO_SECRET` impede sequestro de sessão |
| Sanitização de entrada | Implementado | Contrato `MensagemNormalizada`: trunca tamanho, remove controles/invisíveis |
| Guardrail de escopo (prompt injection) | Implementado | `guardrails/escopo.py`: recusa reprogramação, homóglifos e off-topic sem chamar o LLM |
| Blindagem de prompt | Implementado | Persona + cabeçalho de regras; texto do cliente em bloco com sentinela aleatória |
| Saneamento de saída | Implementado | `guardrails/saida.py`: descarta vazamento de instrução, mascara PII (CPF/cartão), remove tags/código/links |
| Injeção indireta via RAG | Implementado | Descrição de imóvel neutralizada antes de entrar no prompt |
| Rate limiting | Implementado | Por lead (rajada e hora) — `guardrails/vazao.py` |
| Auditoria | Implementado | Middleware registra tudo que altera o sistema |
| CORS | Implementado | `SDR_CORS_ORIGINS` (vazio = `*`, só em dev) |
| Separação de segredos do CRM | Implementado | `CRM_MCP_TOKEN` (agente → servidor MCP) e `CRM_API_TOKEN` (servidor MCP → REST) são distintos; o servidor MCP recusa subir sem o seu |
| Gerenciamento de secrets | Parcial | `.env` fora do versionamento; `scripts/check_env.py` recusa valores de exemplo. Não há cofre |
| Criptografia em trânsito | Parcial | Tudo roda em `localhost`, em HTTP. Expor este ambiente exigiria TLS na frente |
| Tratamento de PII / LGPD | Parcial | Mascaramento na saída; página de privacidade no site. Política de retenção formal: recomendada |
| Análise de dependências | Recomendado | Não há varredura automatizada no CI |

**Riscos conhecidos.** Rate limiting é por processo (não distribuído entre múltiplos workers);
transcrição de áudio como vetor de injeção não tem teste específico — a transcrição entra no prompt
pela mesma blindagem do texto do cliente, mas sem caso dedicado. Ver os comentários em
`services/agent/src/agent/guardrails/`.

---

## 15. Testes e qualidade

- **Tipos de teste.** Sete suítes de integração de backend com Postgres real (pgvector) e LLM falso
  (grafo do agente, API, canais, CRM, governança, segurança); build com TypeScript estrito nos
  front-ends; análise estática (`ruff` no Python, `eslint` nos front-ends) e cobertura combinada com
  piso. O harness de avaliação (`make eval`, `make eval-rag`) mede o **modelo** e fica fora do CI de
  propósito: custa dinheiro e varia entre execuções.
- **Executar backend:**

  ```bash
  make test            # host, Python 3.12 (cria e usa o banco sdr_test)
  make test-docker     # dentro do container do agente
  ```

  Os bancos são **`sdr_test`** e **`crm_test`** (o CRM é sistema à parte também na suíte): as suítes
  apagam tabelas e uma trava recusa rodar contra um banco sem "test" no nome
  (`SDR_TEST_ALLOW_WIPE=1` ignora a trava). A suíte roda em Python 3.12 sem avisos de depreciação.

- **Front-ends:**

  ```bash
  cd apps/web && npm run build
  cd apps/dashboard && npm run build
  npm run a11y         # (apps/web) verificação de acessibilidade

  # lint: as dependências ficam FORA do package.json — o container `web` do compose roda
  # `npm install` a cada subida da demo e não deve carregar ferramenta de CI junto.
  npm i --no-save --legacy-peer-deps eslint@9 typescript-eslint@8 @eslint/js eslint-plugin-react-hooks@5 globals
  npm run lint
  ```

- **Análise estática e cobertura:**

  ```bash
  make lint            # ruff em todo o Python; a régua e o porquê de cada regra desligada em ruff.toml
  make cobertura       # as mesmas sete suítes, medindo cobertura; falha abaixo do piso (.coveragerc)
  make eval-fake       # valida o HARNESS com LLM falso e embedder de trigramas (não mede qualidade)
  make eval-rag        # qualidade do RAG institucional com o embedder de verdade (exige ollama-pull)
  ```

  O piso é **75%** e o estado atual é 81%. Ele existe para uma queda brusca aparecer na CI, não para
  virar corrida por porcentagem — teste escrito para subir número não testa nada.

- **CI.** [`.github/workflows/ci.yml`](.github/workflows/ci.yml) roda dois jobs a cada push/PR:
  `python` (`make lint` → `make cobertura` → `make eval-fake` → conferência do `openapi.json`) e
  `frontend` (build estrito + `eslint` em `web` e `dashboard`). O estático vem antes do teste: nome
  indefinido aparece em segundos, sem esperar o banco subir.

---

## 16. Observabilidade e troubleshooting

A observabilidade em vigor é a **leve** (ADR-0011): tabelas no Postgres (`turnos`, `saude`,
`batimentos`), `/health` que devolve 503 de verdade, logs estruturados em JSON e a aba **Saúde do
sistema** no painel. Não há stack de métricas/tracing por padrão — a de OpenTelemetry+Grafana foi
revogada (ADR-0005). O **Langfuse** é opcional (`--profile observability`) para tracing de prompt/LLM.

- **Logs.** JSON estruturado por serviço (`shared/sdr_shared/log.py`); no compose use `docker compose logs -f <serviço>`.
- **Health checks.** `GET /health` na API e nos canais (503 quando degradado).
- **Uso de tokens.** Registrado por chamada e visível na aba de Governança do painel.

| Problema | Possível causa | Solução |
|---|---|---|
| `docker compose ps` mostra `channels` como `unhealthy` | Redis fora do ar | Verifique o container `redis`; `/health` do canal devolve 503 sem Redis |
| Chat do site "sem conexão" | Canais (`:8001`) ou WebSocket indisponível | Confira `docker compose logs -f channels` e a variável `VITE_WS_URL` |
| Catálogo vazio no site | Seed não executado | Rode `make seed` |
| Agente responde fallback sempre | LLM inacessível, credenciais ou timeout | Confira `SDR_LLM_PROVIDER`/credenciais e `SDR_LLM_TIMEOUT_S`; veja logs do `agent` |
| Painel retorna 401 | Token ausente/incorreto | Envie `Authorization: Bearer <SDR_PAINEL_TOKEN>` (ou `dev-token` no local) |
| Porta 5432/6379/11434 ocupada | Instância nativa em conflito | Ajuste `DB_HOST_PORT`/`REDIS_HOST_PORT`/`OLLAMA_HOST_PORT` |
| Resultados de busca "errados" após editar bairros | Embeddings desatualizados | Reindexe com `make seed` |
| `make test` recusa rodar | Banco sem "test" no nome | Use o `sdr_test`; em último caso `SDR_TEST_ALLOW_WIPE=1` |

---

## 17. Estrutura do repositório

```
agent-sdr-morai/
├── apps/
│   ├── web/          Site vitrine (React + Vite + PWA) com widget de chat
│   ├── dashboard/    Painel do corretor (funil, conversas, governança, auditoria)
│   └── crm/          Painel do CRM da imobiliária (React)
├── services/
│   ├── agent/        Grafo multiagente (LangGraph) — o cérebro; único que fala com o LLM
│   ├── channels/
│   │   ├── local/    Chat do site: HTTP + WebSocket
│   │   └── telegram/ Long polling de entrada e worker de saída
│   ├── api/          API REST (FastAPI): imóveis, leads, dashboard, handoff, governança
│   ├── crm/          CRM da imobiliária: REST, servidor MCP e banco próprios
│   ├── scheduler/    Follow-up automático
│   └── ingestion/    Carga de imóveis e documentos + embeddings
├── shared/           Pacote Python comum: modelos, contratos, DB, config, ports/adapters
├── local/            docker compose (Postgres+pgvector, Redis, workers, canais, apps) + Dockerfile.python
├── data/             Base simulada de imóveis e documentos institucionais
├── scripts/          Utilitários de dev (check_env, gerar_imoveis, gerar_openapi)
├── tests/            Suíte de integração da raiz
├── docs/             Arquitetura, ADRs e o portal MkDocs
└── .github/          CI (GitHub Actions)
```

**Regras de dependência.** `shared/` é a única ponte entre serviços. Canais só traduzem mensagens e
nunca chamam o LLM. O agente produz respostas neutras (`texto`, `opcoes`, `imoveis`, `acao`) e não
sabe qual canal respondeu. Detalhes em [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

**Convenções relevantes.**
- Cada serviço expõe um pacote com nome próprio (`agent`, `api`, `canal_telegram`, `sdr_scheduler`,
  `sdr_ingestion`, `sdr_crm`) — nunca `src` — para evitar colisão no `sys.path`.
- Os serviços Python compartilham **uma única imagem**, construída a partir da raiz do repositório
  (todos dependem de `shared/`): `local/Dockerfile.python`, com o código montado por volume. O que
  muda entre containers é o comando, não a imagem.

> A pasta `_to_delete/` e os arquivos `*.tgz` na raiz são material de trabalho descartável e não fazem
> parte da aplicação.

---

## 18. Roadmap e limitações

Esta seção lista o que **não** está pronto — separada das funcionalidades implementadas.

**Limitações conhecidas.**
- Nada está implantado: o sistema só existe rodando no `docker compose` de quem o subir. É escolha
  de escopo, não pendência — mas significa que não há ambiente público para demonstrar.
- O único canal externo é o Telegram. O WhatsApp foi removido do código (exigia número de negócio
  verificado e webhook com URL pública — ADR-0007); voltar significa escrever o adaptador de novo.
- A fusão léxica (RRF) do RAG institucional está pronta e desligada: falta medi-la com um embedder
  semântico de verdade (`SDR_RAG_LEXICO=1 make eval-rag`).
- Rate limiting é por processo, não distribuído entre múltiplos workers.
- Sem benchmarks de performance versionados.
- Tudo trafega em HTTP no `localhost`; expor este ambiente exigiria TLS e revisão de CORS.

**Débitos técnicos / itens em aberto.**
- Não há varredura automatizada de dependências no CI (a cobertura, essa está: `make cobertura`).
- Instrumentação de observabilidade de sistema (OTel/Grafana) foi revogada; existe apenas a leve.
- Papéis/permissões granulares por usuário no painel: a definir.

**Riscos e dependências externas.**
- Disponibilidade e cota do provedor de LLM (mitigadas por `SDR_LLM_PROVIDER_FALLBACK`).
- API do Telegram e, quando configurado, o Google Agenda do corretor.
- O custo variável do sistema é só o do modelo — e cai a zero com o Ollama, em troca de qualidade
  de conversa menor.

---

## 19. Contribuição

Não há um `CONTRIBUTING.md` formal no repositório; as práticas abaixo são inferidas do fluxo de CI e
das convenções do projeto (marcado como inferência).

- **Branches (inferido).** Crie uma branch a partir da principal para cada mudança
  (ex.: `feat/nome-curto`, `fix/nome-curto`).
- **Commits e Pull Requests (inferido).** Descreva o que muda e por quê; mantenha PRs focados.
- **Validações obrigatórias.** O PR precisa passar na CI: `make lint`, `make cobertura` e
  `make eval-fake` (backend) e `npm run build` + `npm run lint` (`web` e `dashboard`). Rode-os
  localmente antes de abrir o PR.
- **Antes de tocar em um serviço.** Leia [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) e respeite as
  regras de dependência entre camadas.
- **Convenção de commits / template de PR / processo de revisão formais:** `A confirmar`.

---

## 20. Licença e responsáveis

- **Licença:** MIT — ver [`LICENSE`](LICENSE) e [Licença](docs/project/licenca.md).
- **Responsáveis / equipe:** `A confirmar` (contexto acadêmico — FIAP, fase 5 — inferido pelo caminho
  do projeto; não confirmado por arquivo no repositório).
- **Canal de suporte / contato:** `A confirmar`. Os dados de contato exibidos no site
  (`apps/web/src/lib/imobiliaria.ts`) são placeholders de demonstração, não canais de suporte reais.

---

## 21. Pendências de documentação

Informações que não puderam ser confirmadas apenas com o conteúdo do repositório:

1. **Canal de suporte** oficial (licença: MIT, ver `LICENSE`; autoria: Marcos Ramos).
2. **Requisitos de hardware** mínimo/recomendado (sobretudo com Ollama e o faster-whisper no mesmo
   processo).
3. **Papéis e permissões** granulares por usuário no painel (a API separa por área, mas o mapeamento
   usuário → papel não está documentado).
4. **Benchmarks de performance** (nenhum número medido versionado).
5. **Convenção de commits, template de PR e processo de revisão** formais.
6. **Política de retenção e exclusão de dados** (LGPD) formal.

> Sugestão: converter estas pendências em issues e, quando resolvidas, atualizar as seções
> correspondentes deste README.
