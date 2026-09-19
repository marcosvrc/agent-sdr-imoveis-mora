# Mora — Agente SDR Imobiliário da Vértice Imóveis

Prova de conceito (POC) de um SDR (Sales Development Representative) imobiliário com IA
generativa. A agente virtual **Mora** atende o cliente, entende o que ele procura, recomenda
imóveis do catálogo, agenda visitas e passa o lead qualificado para um corretor humano.

O repositório é um monorepo: cada componente vive na sua pasta, com dependências, testes e deploy
independentes, comunicando-se apenas por contratos definidos em `shared/`.

**Status:** POC (prova de conceito). Núcleo implementado e testado nos perfis local e AWS; alguns
itens dependentes de serviços AWS estão escritos mas não testados (ver [Funcionalidades](#4-funcionalidades-implementadas)).

**CI:** GitHub Actions — testes de backend (Python 3.12 + Postgres pgvector), build dos front-ends
(`web` e `dashboard`) e `cdk synth` da infraestrutura. Ver [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

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
[Portal (GitHub Pages)](https://marcosvrc.github.io/agent-sdr-imoveis-mora/) · [Arquitetura](docs/ARCHITECTURE.md) · [ADRs](docs/adr) · [Perfil local](local/README.md) · [Observabilidade](docs/observabilidade.md) · [Como contribuir](docs/project/contribuir.md)

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
App nativo (o PWA cobre), CRM real (simulado no banco + endpoint `/leads/crm/sync`), Voice AI em
tempo real, multi-tenant e WhatsApp Business verificado da empresa.

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
| Transcrição de áudio (Amazon Transcribe) | Parcial | escrita, não testada (exige AWS) |
| RAG via Bedrock Knowledge Base | Parcial | escrita, não testada (exige AWS); fallback pgvector é o testado |

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

### Backend, integrações e infraestrutura
| Funcionalidade | Estado | Evidência |
|---|---|---|
| API REST (imóveis públicos, leads, dashboard, handoff, eventos, config, governança, auditoria) | Concluída | `services/api`, `tests/test_api.py` |
| Canal Telegram (long polling no local) | Concluída | `services/channels/telegram` |
| Canal Web (WebSocket) | Concluída | `services/channels/local`, `services/channels/web` |
| Canal WhatsApp (webhook HMAC, cards, template 24h) | Parcial | `tests/test_adapter.py`; **desativado** no compose (ADR-0007) |
| Follow-up automático e ingestão de imóveis | Concluída | `services/scheduler`, `services/ingestion` |
| Integração Google Agenda do corretor | Parcial | `tools/agenda.py`; opcional, degrada para agenda interna |
| Infraestrutura como código (AWS CDK, 10 stacks) | Concluída | `cdk synth` na CI |

> As funcionalidades marcadas como **Parcial** não devem ser tratadas como prontas para produção.

---

## 5. Tecnologias utilizadas

Versões obtidas dos arquivos do projeto (`package.json`, `pyproject.toml`, `settings.py`,
`docker-compose.yml`, `.github/workflows/ci.yml`). Onde a versão não está fixada no repositório,
consta `A confirmar`.

| Categoria | Tecnologia | Versão | Finalidade |
|---|---|---:|---|
| Frontend | React | ^18.3.1 | Interface do site e do painel |
| Frontend | Vite | ^5.4.0 | Build e servidor de desenvolvimento |
| Frontend | TypeScript | ^5.5.3 | Tipagem estática (build estrito) |
| Frontend | Tailwind CSS | ^3.4.0 | Estilos |
| Frontend | TanStack React Query | ^5.51.0 | Cache e sincronização de dados |
| Frontend | Zustand | ^4.5.0 | Estado do chat (site) |
| Frontend | Recharts | ^2.12.0 | Gráficos do painel |
| Frontend | AWS Amplify | ^6.5.0 | Autenticação Cognito no painel (perfil AWS) |
| Frontend | vite-plugin-pwa | ^0.20.0 | PWA do site |
| Backend | Python | 3.12 | Linguagem dos serviços |
| Backend | FastAPI | >=0.115 | API REST e apps de canal |
| Backend | Mangum | A confirmar | Adaptador FastAPI → AWS Lambda |
| LLM/IA | LangGraph | >=0.2 | Orquestração do grafo multiagente |
| LLM/IA | LangChain Core | >=0.3 | Abstrações de mensagens/modelos |
| LLM/IA | Amazon Bedrock — Claude Sonnet | `anthropic.claude-sonnet-4-5` (padrão, ajustável) | Conversa com o cliente |
| LLM/IA | Amazon Bedrock — Claude Haiku | `anthropic.claude-haiku-4-5` (padrão, ajustável) | Roteamento e extração |
| LLM/IA | Provedores alternativos | — | `anthropic` (API) e `ollama` (local), via `SDR_LLM_PROVIDER` |
| RAG/Embeddings | Amazon Titan Embeddings v2 | `amazon.titan-embed-text-v2:0` | Embeddings (perfil AWS) |
| RAG/Embeddings | Ollama bge-m3 | 1024 dims | Embeddings locais (opcional) |
| RAG/Embeddings | Bedrock Knowledge Base | — | RAG gerenciado; fallback pgvector direto (ADR-0001) |
| Banco de dados | PostgreSQL + pgvector | `pgvector/pgvector:pg16` | Dados relacionais + vetores |
| Banco de dados (AWS) | Aurora Serverless v2 (Postgres 16) | — | Mesma base, gerenciada (ADR-0004) |
| Fila / assíncrono (AWS) | Amazon SQS + EventBridge Scheduler | — | Mensageria e follow-up |
| Fila / assíncrono (local) | Redis Streams | `redis:7-alpine` | Substitui SQS/EventBridge no compose |
| Armazenamento (AWS) | Amazon S3 + CloudFront | — | Fotos e documentos |
| Autenticação | Amazon Cognito (AWS) / token estático (local) | — | Acesso ao painel (ADR-0008) |
| Infraestrutura | AWS CDK (Python) | ver `infra/requirements.txt` | IaC, 10 stacks |
| Containers | Docker + Docker Compose | — | Perfil local e imagens de deploy |
| CI/CD | GitHub Actions | — | Testes, build de front-ends, `cdk synth` |
| Observabilidade | Postgres (tabelas de saúde) + `/health` + logs JSON | — | Observabilidade leve (ADR-0011) |
| Observabilidade | Langfuse | `langfuse/langfuse:2` | Tracing de LLM (opcional, perfil local) |
| Testes | pytest | — | Testes de backend |

---

## 6. Arquitetura da solução

### Visão geral

O sistema separa o **cérebro** (o agente) dos **canais** (Telegram, web). O agente não sabe por qual
canal a mensagem chegou: cada canal traduz `evento do provedor → MensagemNormalizada` e
`RespostaAgente → formato do canal`. A única dependência cruzada permitida é o pacote `shared/`.

O mesmo código roda em dois perfis, escolhidos por `SDR_PROFILE`: **aws** (serverless) e **local**
(docker compose). A troca acontece apenas nos adaptadores (`shared/sdr_shared/adapters/{aws,local}`).

```mermaid
flowchart LR
  subgraph Entrada["Porta de entrada"]
    SITE["apps/web<br/>site vitrine + chat"]
    TG["Telegram<br/>Bot API"]
  end

  subgraph Canais["services/channels"]
    CH["Web (WebSocket)<br/>Telegram (long polling)"]
  end

  Q[["Fila<br/>SQS (aws) / Redis (local)"]]

  subgraph Agente["services/agent — grafo LangGraph"]
    SUP["Supervisor"]
    NODES["Qualificador · Consultor<br/>Agendador · Follow-up<br/>Handoff · Resumidor<br/>Reativador"]
    SUP --> NODES
  end

  LLM["LLM<br/>Bedrock / Anthropic / Ollama"]
  DB[("Postgres + pgvector<br/>Aurora (aws) / container (local)")]
  API["services/api<br/>FastAPI"]
  DASH["apps/dashboard<br/>painel do corretor"]

  SITE --> CH
  TG --> CH
  CH --> Q --> Agente
  Agente --> LLM
  Agente --> DB
  Agente -->|resposta neutra| CH
  API --> DB
  DASH --> API
  DASH -->|tempo real| CH
```

**Componentes e responsabilidades.**
- **`apps/web`** — site vitrine, catálogo e widget de chat; porta de entrada do cliente.
- **`apps/dashboard`** — painel do corretor (funil, conversas, agenda, imóveis, governança, auditoria).
- **`services/channels`** — adaptadores de canal, sem regra de negócio.
- **`services/agent`** — grafo multiagente; único componente que fala com o LLM.
- **`services/api`** — API REST (imóveis públicos, leads, dashboard, handoff, config, governança).
- **`services/scheduler`** — follow-up automático (agenda e cancela por lead).
- **`services/ingestion`** — carga de imóveis e geração de embeddings.
- **`shared/`** — modelos, contratos, repositórios (SQL + pgvector), portas e adaptadores.
- **`infra/`** — AWS CDK (só deploy; sem lógica).

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

### Diagrama de implantação local

```mermaid
flowchart TB
  subgraph Host["Máquina do desenvolvedor (docker compose)"]
    subgraph Front["Front-ends (Vite)"]
      W["web :5173"]
      D["dashboard :5174"]
    end
    A["api :8000"]
    C["channels :8001 (HTTP + WS)"]
    AG["agent (worker)"]
    RS["resumidor (worker)"]
    RT["reativador (worker)"]
    SC["scheduler (worker)"]
    TI["telegram-in / telegram-out"]
    PG[("db :5433 → 5432<br/>Postgres + pgvector")]
    RD[("redis :6380 → 6379")]
    OL[("ollama :11435 (opcional)")]
    LF["langfuse :3000 (opcional)"]
  end
  W --> A
  W --> C
  D --> A
  D --> C
  A --> PG
  C --> RD
  AG --> RD
  AG --> PG
  SC --> RD
  TI --> RD
```

As portas do host (5433, 6380, 11435) são deslocadas para não colidir com instâncias nativas de
Postgres, Redis e Ollama e podem ser ajustadas por `DB_HOST_PORT`, `REDIS_HOST_PORT` e
`OLLAMA_HOST_PORT`. Ver [`local/README.md`](local/README.md).

---

## 7. Decisões tecnológicas

Cada decisão está registrada como ADR (Architecture Decision Record) em [`docs/adr`](docs/adr).
Resumo das principais:

- **RAG com Knowledge Base + Aurora pgvector, com fallback pgvector direto** ([ADR-0001](docs/adr/0001-rag-knowledge-base-com-aurora-pgvector.md)).
  Usa um serviço gerenciado quando disponível; se `SDR_KNOWLEDGE_BASE_ID` estiver vazio, cai para
  busca vetorial direta no Postgres. **Trade-off:** o caminho gerenciado não é testado localmente.
- **Agente em Lambda container consumindo SQS** ([ADR-0002](docs/adr/0002-agente-em-lambda-container.md)).
  Maximiza serverless; as Lambdas são imagens de container porque dependem de `shared`, `psycopg` e `httpx`.
- **Canais como adaptadores sem lógica** ([ADR-0003](docs/adr/0003-canais-como-adaptadores.md)).
  Permite trocar/adicionar canal sem tocar no agente.
- **Aurora Serverless v2 (Postgres) em vez de DynamoDB** ([ADR-0004](docs/adr/0004-aurora-em-vez-de-dynamodb.md)).
  SQL para o painel e vetores na mesma base; escala a zero. **Trade-off:** exige VPC/NAT (custo).
- **Telegram em vez de WhatsApp como canal ativo** ([ADR-0007](docs/adr/0007-telegram-em-vez-de-whatsapp.md)).
  Bot criado sem verificação de negócio; o adapter de WhatsApp fica pronto para religar.
- **Modelo por nível, editável no painel** ([ADR-0010](docs/adr/0010-modelo-por-nivel-e-troca-pelo-painel.md)).
  Sonnet na conversa, Haiku em roteamento/extração; ajustável sem redeploy.
- **Observabilidade leve no Postgres** ([ADR-0011](docs/adr/0011-observabilidade-leve-no-postgres.md)),
  que **revogou** a stack OpenTelemetry+Grafana ([ADR-0005](docs/adr/0005-observabilidade-com-opentelemetry-e-grafana.md))
  por consumo de recursos na máquina de desenvolvimento.

---

## 8. Pré-requisitos

**Para o perfil local (recomendado para começar):**
- Git.
- Docker e Docker Compose.
- Credenciais do provedor de LLM escolhido (Amazon Bedrock ou Anthropic API) — ou Ollama para rodar
  100% local, sem custo.
- (Opcional) Token de bot do Telegram, obtido no `@BotFather`, para exercitar o canal externo.

**Para rodar os testes de backend ou executar serviços manualmente:**
- Python **3.12** (versão usada em produção e na CI).
- `pip` ou [`uv`](https://docs.astral.sh/uv/) como gerenciador de pacotes (o `Makefile` usa `uv`).
- Node.js **20** para os front-ends.

**Para o deploy AWS:**
- Conta AWS com acesso ao Amazon Bedrock na região escolhida.
- AWS CLI configurada e AWS CDK (`npm i -g aws-cdk`).
- Python 3.12 e dependências de `infra/requirements.txt`.

> Requisitos de hardware mínimo/recomendado: `A confirmar`. O uso de Ollama local aumenta bastante o
> consumo de CPU/RAM (ver [`docs/observabilidade.md`](docs/observabilidade.md)).

---

## 9. Configuração das variáveis de ambiente

Todas as variáveis usam o prefixo `SDR_`. O arquivo de referência é [`.env.example`](.env.example);
o perfil local tem o seu em [`local/.env.example`](local). Os valores abaixo são **fictícios** — não
use segredos reais no repositório.

Crie seu arquivo a partir do exemplo:

```bash
cp .env.example .env                 # execução manual / deploy
cp -n local/.env.example local/.env     # perfil local (docker compose)
```

| Variável | Obrigatória | Exemplo seguro | Descrição |
|---|---|---|---|
| `SDR_ENV` | Não | `dev` | Ambiente lógico. Padrão `dev`. |
| `SDR_PROFILE` | Não | `local` | `aws` (padrão) ou `local`; decide fila, scheduler e hospedagem. |
| `SDR_AWS_REGION` | Não | `us-east-1` | Região AWS. |
| `SDR_DATABASE_DSN` | Sim | `postgresql://sdr:sdr@localhost:5432/sdr` | DSN do Postgres. |
| `SDR_LLM_PROVIDER` | Não | `bedrock` | `bedrock`, `anthropic` ou `ollama`. Padrão `bedrock`. |
| `SDR_LLM_PROVIDER_FALLBACK` | Não | `anthropic` | Provedor de reserva quando o primário falha. Vazio = sem fallback. |
| `SDR_MODEL_CONVERSA` | Não | `anthropic.claude-sonnet-4-5` | Modelo da conversa. |
| `SDR_MODEL_ROTEAMENTO` | Não | `anthropic.claude-haiku-4-5` | Modelo de roteamento/extração. |
| `SDR_EMBEDDINGS_PROVIDER` | Não | `bedrock` | `bedrock` ou `ollama`. |
| `SDR_KNOWLEDGE_BASE_ID` | Não | *(vazio)* | ID da Knowledge Base; vazio = fallback pgvector direto. |
| `SDR_LLM_TIMEOUT_S` | Não | `45` | Timeout por turno; acima disso o cliente recebe o fallback. |
| `SDR_REDIS_URL` | Não (local) | `redis://localhost:6379/0` | Fila do perfil local. |
| `SDR_TELEGRAM_BOT_TOKEN` | Não | `000000:exemplo-token` | Token do bot (canal ativo no local). |
| `SDR_TELEGRAM_BOT_USERNAME` | Não | `mora_vertice_bot` | Usuário do bot, para montar o link `t.me/<usuario>`. |
| `SDR_WHATSAPP_PHONE_NUMBER_ID` | Não | `000000000000000` | ID do número (canal WhatsApp, desativado). |
| `SDR_WHATSAPP_TOKEN` | Não | `EAAB...exemplo` | Token da Meta Cloud API. |
| `SDR_WHATSAPP_APP_SECRET` | Não | `exemplo-app-secret` | Segredo para validar HMAC do webhook. |
| `SDR_WHATSAPP_VERIFY_TOKEN` | Não | `sdr-verify` | Token de verificação do webhook. Padrão `sdr-verify`. |
| `SDR_SESSAO_SECRET` | Recomendada | `troque-por-uma-string-aleatoria-longa` | Assina a sessão do chat do site. Sem valor, as sessões caem a cada reinício. |
| `SDR_PAINEL_TOKEN` | Sim (fora do local) | `exemplo-token-painel` | Credencial do painel fora do API Gateway (WebSocket). No local vazio vira `dev-token`. |
| `SDR_CORS_ORIGINS` | Recomendada (produção) | `https://app.exemplo.com` | Origens permitidas na API, separadas por vírgula. Vazio = `*` (só em dev). |
| `SDR_GOOGLE_CLIENT_ID` | Não | `exemplo.apps.googleusercontent.com` | OAuth do Google Agenda (opcional). |
| `SDR_GOOGLE_CLIENT_SECRET` | Não | `exemplo-secret` | OAuth do Google Agenda (opcional). |
| `SDR_GOOGLE_REDIRECT_URI` | Não | `http://localhost:8000/calendario/callback` | URI de retorno do OAuth. |

Sem `SDR_GOOGLE_*`, a Mora usa a grade interna de horários e as visitas continuam sendo marcadas.
Sem `SDR_KNOWLEDGE_BASE_ID`, o RAG usa pgvector direto.

---

## 10. Como executar localmente

### Opção A — Docker Compose (caminho recomendado)

```bash
# 1. Clonar e entrar no diretório
git clone <url-do-repositorio>
cd agent-sdr-morai

# 2. Configurar o ambiente do perfil local
cp -n local/.env.example local/.env
# edite local/.env: provedor de LLM, e CRM_MCP_TOKEN se for usar o CRM (veja o .env.example)

# 3. Subir tudo. Use `make local-ollama` para LLM e embeddings 100% locais.
make local
# equivalente a: cd local && docker compose up --build

# --- daqui em diante, em OUTRO terminal, com o compose no ar ---

# 4. Bancos e massa, na ordem das dependências
make preparar

# 5. Credencial da Mora no CRM (aparece uma vez; cole em CRM_API_TOKEN no local/.env)
make crm-token
cd local && docker compose up -d crm-mcp agent && cd ..

# 6. Índices: acervo e documentos institucionais
make ollama-pull      # só se usar embeddings locais
make seed
make docs-kb

# 7. Encerrar o ambiente
cd local && docker compose down          # use down -v para apagar também os volumes (Postgres/Ollama)
```

`make` sozinho imprime essa ordem — é o alvo padrão, e é a fonte que se mantém em dia com o
Makefile.

O `make local` executa `scripts/check_env.py` antes de subir.

**Sobre o schema:** `local/00-crm.sql` e `shared/sdr_shared/db/schema.sql` estão montados em
`docker-entrypoint-initdb.d`, mas o Postgres só executa esses scripts quando o **volume é novo**.
Num volume que já existia — o caso de quem acompanha o projeto há algum tempo — eles nunca rodam, e
o sintoma é `FATAL: database "crm" does not exist` sem nada explicando a causa. Por isso `make
preparar` cria e aplica tudo explicitamente, e é idempotente: rodar de novo não estraga nada.

**Sem CRM:** a Mora roda sozinha. Pule os passos 4 e 5 (exceto `make migrate`, que o `preparar`
inclui) e siga para o 6.

### Opção B — Execução manual (desenvolvimento)

Requer Postgres com pgvector acessível e Python 3.12. Instale as dependências e aplique o schema:

```bash
make setup                                # instala serviços (uv/pip) e front-ends (npm)
psql "$SDR_DATABASE_DSN" -f shared/sdr_shared/db/schema.sql
```

Suba cada processo em um terminal (os comandos espelham o `docker-compose.yml`):

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
make cli                                  # conversa com a Mora no terminal (perfil local)
```

### Deploy AWS (referência)

```bash
make deploy ENV=dev                       # build dos front-ends + cdk deploy --all (perfil aws)
```

### Serviços e portas (perfil local)

| Serviço | URL local | Porta | Health check |
|---|---|---:|---|
| Site (PWA) | http://localhost:5173 | 5173 | — (Vite dev server) |
| Painel | http://localhost:5174 | 5174 | — (Vite dev server) |
| API | http://localhost:8000 | 8000 | `GET /health` (503 quando degradado) |
| API (OpenAPI) | http://localhost:8000/docs | 8000 | — |
| Canais (HTTP/WS) | http://localhost:8001 · ws://localhost:8001/ws | 8001 | `GET /health` (503 se o Redis cair) |
| Agente | worker (sem HTTP) | — | via tabela de saúde no Postgres (ADR-0011) |
| Langfuse (opcional) | http://localhost:3000 | 3000 | — |
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

- **Acesso e autenticação.** `http://localhost:5174`. No perfil local, a autenticação usa um token
  estático (`SDR_PAINEL_TOKEN`, que vira `dev-token` quando vazio). No perfil AWS, usa Amazon Cognito.
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
- **Autenticação:** rotas de corretor/admin exigem Cognito JWT (perfil AWS) ou `Authorization:
  Bearer <SDR_PAINEL_TOKEN>` (perfil local). Rotas públicas (`/imoveis`, `/eventos`) não exigem auth.

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
- **Aurora Serverless v2** escala a zero quando ocioso (perfil AWS).

**Benchmarks.** Não há benchmarks de desempenho medidos e versionados no repositório. Procedimento
reprodutível sugerido para obtê-los:

1. Subir o perfil local e popular o catálogo (`make local && make seed`).
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
| Autenticação do painel | Implementado | Cognito (AWS) / token estático (local) — ADR-0008 |
| Autorização por área | Implementado | Rotas separadas (público/corretor/admin/operação) |
| Validação de webhook (HMAC) | Implementado | Canal WhatsApp valida assinatura do provedor |
| Sessão assinada do chat do site | Implementado | `SDR_SESSAO_SECRET` impede sequestro de sessão |
| Sanitização de entrada | Implementado | Contrato `MensagemNormalizada`: trunca tamanho, remove controles/invisíveis |
| Guardrail de escopo (prompt injection) | Implementado | `guardrails/escopo.py`: recusa reprogramação, homóglifos e off-topic sem chamar o LLM |
| Blindagem de prompt | Implementado | Persona + cabeçalho de regras; texto do cliente em bloco com sentinela aleatória |
| Saneamento de saída | Implementado | `guardrails/saida.py`: descarta vazamento de instrução, mascara PII (CPF/cartão), remove tags/código/links |
| Injeção indireta via RAG | Implementado | Descrição de imóvel neutralizada antes de entrar no prompt |
| Rate limiting | Implementado | Por lead (rajada e hora) — `guardrails/vazao.py` |
| Auditoria | Implementado | Middleware registra tudo que altera o sistema |
| CORS | Implementado | `SDR_CORS_ORIGINS` (vazio = `*`, só em dev) |
| Gerenciamento de secrets | Implementado (AWS) | Secrets Manager em produção; `.env` em dev |
| Criptografia em trânsito | Parcial | HTTPS/WSS providos pela AWS (API Gateway/CloudFront); no local é HTTP |
| Tratamento de PII / LGPD | Parcial | Mascaramento na saída; página de privacidade no site. Política de retenção formal: recomendada |
| Análise de dependências | Recomendado | Não há varredura automatizada no CI |
| Moderação/guardrails do provedor (Bedrock Guardrails) | Parcial | Previsto no CDK (perfil AWS), não testado |

**Riscos conhecidos.** Rate limiting é por processo (não distribuído entre múltiplos workers);
transcrição de áudio como vetor de injeção não tem teste específico; controles dependentes de AWS
(Guardrails, criptografia gerenciada) não são exercitados no perfil local. Ver os comentários em
`services/agent/src/agent/guardrails/`.

---

## 15. Testes e qualidade

- **Tipos de teste.** Testes de integração de backend com Postgres real (pgvector) e LLM falso
  (grafo do agente, API, canais, governança, segurança); build com TypeScript estrito nos front-ends;
  `cdk synth` da infraestrutura; análise estática (`ruff` no Python, `eslint` nos front-ends) e
  cobertura combinada com piso.
- **Executar backend:**

  ```bash
  make test            # host, Python 3.12 (cria e usa o banco sdr_test)
  make test-docker     # dentro do container do agente
  ```

  Ambos usam o banco **`sdr_test`**: as suítes apagam tabelas e uma trava recusa rodar contra um banco
  sem "test" no nome (`SDR_TEST_ALLOW_WIPE=1` ignora a trava). A suíte roda em Python 3.12 sem avisos
  de depreciação.

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
  ```

  O piso é **75%** e o estado atual é ~81%. Ele existe para uma queda brusca aparecer na CI, não para
  virar corrida por porcentagem — teste escrito para subir número não testa nada.

- **CI.** [`.github/workflows/ci.yml`](.github/workflows/ci.yml) roda os três jobs a cada push/PR:
  `python` (`make lint` → `make cobertura` → conferência do `openapi.json`), `frontend` (build estrito
  + `eslint` em `web` e `dashboard`) e `infra` (`cdk synth`). O estático vem antes do teste: nome
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
├── docs/             Arquitetura, ADRs e observabilidade
└── .github/          CI/CD (GitHub Actions)
```

**Regras de dependência.** `shared/` é a única ponte entre serviços. Canais só traduzem mensagens e
nunca chamam o LLM. O agente produz respostas neutras (`texto`, `opcoes`, `imoveis`, `acao`) e não
sabe qual canal respondeu. Detalhes em [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

**Convenções relevantes.**
- Cada serviço expõe um pacote com nome próprio (`agent`, `api`, `canal_whatsapp`, `canal_telegram`,
  `sdr_scheduler`, `sdr_ingestion`) — nunca `src` — para evitar colisão no `sys.path`.
- As imagens Docker são construídas **a partir da raiz do repositório** (dependem de `shared/`):
  `docker build -f services/<serviço>/Dockerfile .`.

> A pasta `_to_delete/` e os arquivos `*.tgz` na raiz são material de trabalho descartável e não fazem
> parte da aplicação.

---

## 18. Roadmap e limitações

Esta seção lista o que **não** está pronto — separada das funcionalidades implementadas.

**Limitações conhecidas.**
- Canal WhatsApp implementado mas desativado (depende de número de negócio verificado — ADR-0007).
- Knowledge Base e transcrição de áudio escritas, mas não testadas (exigem AWS).
- Rate limiting é por processo, não distribuído entre múltiplos workers.
- Sem benchmarks de performance versionados.
- CRM é simulado (`/leads/crm/sync`), não integrado a um sistema real.

**Débitos técnicos / itens em aberto.**
- Análise de dependências e cobertura de testes não estão no CI.
- Instrumentação de observabilidade de sistema (OTel/Grafana) foi revogada; existe apenas a leve.
- Papéis/permissões granulares por usuário no painel: a definir.

**Riscos e dependências externas.**
- Disponibilidade e cota do provedor de LLM (Bedrock/Anthropic).
- Custo de infraestrutura AWS dominado pelo NAT Gateway (ver estimativas em `docs/ARCHITECTURE.md`).

---

## 19. Contribuição

Não há um `CONTRIBUTING.md` formal no repositório; as práticas abaixo são inferidas do fluxo de CI e
das convenções do projeto (marcado como inferência).

- **Branches (inferido).** Crie uma branch a partir da principal para cada mudança
  (ex.: `feat/nome-curto`, `fix/nome-curto`).
- **Commits e Pull Requests (inferido).** Descreva o que muda e por quê; mantenha PRs focados.
- **Validações obrigatórias.** O PR precisa passar na CI: `make test` (backend), `npm run build`
  (`web` e `dashboard`) e `cdk synth` (infra). Rode-os localmente antes de abrir o PR.
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
2. **Versões** de `mangum` e das dependências de `infra/requirements.txt` (não inspecionadas em detalhe).
3. **Requisitos de hardware** mínimo/recomendado para o perfil local (sobretudo com Ollama).
4. **Papéis e permissões** granulares por usuário no painel (a API separa por área, mas o mapeamento
   usuário → papel não está documentado).
5. **Benchmarks de performance** (nenhum número medido versionado).
6. **Convenção de commits, template de PR e processo de revisão** formais.
7. **Política de retenção e exclusão de dados** (LGPD) formal.

> Sugestão: converter estas pendências em issues e, quando resolvidas, atualizar as seções
> correspondentes deste README.
