# Observabilidade de sistema — OpenTelemetry + Grafana

Decisão de arquitetura: [ADR-0005](adr/0005-observabilidade-com-opentelemetry-e-grafana.md).

**Status: revogado em 2026-09-12.** Chegou a ser implementado por completo (código, compose,
3 dashboards) e testado, mas foi removido do repositório: os ~7 containers extras (Collector,
Prometheus, Tempo, cAdvisor, 2 exporters, Grafana) competem por CPU/RAM com o Ollama na mesma
máquina de desenvolvimento, e é o Ollama quem mais sofre — turnos do agente chegaram a 40-50s por
causa disso. Ver a seção "Atualização — revogado" no final do ADR-0005 para o raciocínio completo.

**O que está em vigor hoje** é o [ADR-0011](adr/0011-observabilidade-leve-no-postgres.md):
três tabelas no Postgres que já roda (`turnos`, `saude`, `batimentos`), `/health` que devolve 503 de
verdade, log estruturado em JSON e a aba **Saúde do sistema** no painel — sem nenhum container extra.

**O texto abaixo é o desenho original, mantido como referência caso valha reimplementar no futuro**
(por exemplo, rodando numa máquina com mais recursos, ou só em produção). Nada do que descreve abaixo
está hoje no código ou no `docker-compose.yml` — foi todo desfeito.

## 1. Objetivo

Dar visibilidade de **saúde de sistema** — coisa que o painel de negócio (Governança, Auditoria) não
mostra — respondendo, a qualquer momento, a três perguntas:

1. Está tudo no ar? (`api`, `channels`, `agent`, `resumidor`, `reativador`, `telegram-in`, `telegram-out`, `scheduler`, `db`, `redis`)
2. Está rápido? (latência por rota HTTP, por nó do grafo, por chamada externa — LLM, Google Calendar)
3. Está enfileirando/acumulando? (streams do Redis crescendo, workers atrasados, rate limit disparando)

Não é objetivo duplicar o que o painel de negócio já faz bem (funil de leads, temperatura, custo de
LLM por chamada — isso continua no Postgres via `RegistradorUso`, exibido em Governança). Onde os dois
mundos se cruzam (ex.: "quantas chamadas ao LLM por minuto" também é sinal de saúde), o dashboard técnico
lê a métrica agregada e linka de volta para o painel de negócio para o detalhe.

## 2. Arquitetura

```
 api ──┐                                    ┌─→ Prometheus ──┐
 channels ──┐                               │                │
 agent ──────┼─→ OTLP/gRPC → OTel Collector ─┼─→ Tempo ───────┼─→ Grafana
 resumidor ──┤                               │                │
 scheduler ──┘                               └─→ (Loki, fase2)┘
                postgres_exporter ──→ Prometheus ─┘
                redis_exporter ─────→ Prometheus ─┘
                cAdvisor + node-exporter → Prometheus ─┘
```

- Cada serviço Python usa o **OpenTelemetry SDK** (traces + métricas) e exporta via OTLP para um
  **OTel Collector** — um serviço novo no compose, atrás de `--profile observability` (mesmo padrão do
  Langfuse hoje).
- O Collector faz *fan-out*: métricas para **Prometheus** (scrape ou remote-write), traces para
  **Tempo**. Logs estruturados ficam de fora da fase 1 (ver §7) — continuam como `logging` padrão.
- **Grafana** é a única camada de visualização, com datasources Prometheus + Tempo + Postgres (esse
  último para cruzar métrica técnica com dado de negócio quando fizer sentido, ex. "latência da chamada
  de agendamento" ao lado de "visitas marcadas no dia").
- `postgres_exporter` e `redis_exporter` cobrem os dois serviços que não são código nosso.
  `cAdvisor` + `node-exporter` (ou só `cAdvisor`, já que é tudo container) cobrem CPU/memória/disco por
  serviço — a pergunta "algum container está estourando memória" hoje não tem resposta nenhuma.

## 3. Onde instrumentar, serviço por serviço

| Serviço | Como | O que emitir |
|---|---|---|
| `api` (FastAPI, porta 8000) | auto-instrumentação `opentelemetry-instrumentation-fastapi` **(chegou a ser implementado; removido na revogação)** | RED automático via `instrumentar_fastapi(app)`: contagem de requisições, duração, taxa de erro — por rota e por status. Spans de query no Postgres (`-psycopg`): **não ligado ainda** — a dependência está no extra `observabilidade` do `shared/pyproject.toml`, falta chamar `PsycopgInstrumentor().instrument()` no bootstrap. |
| `channels/local` (FastAPI + WebSocket, porta 8001) | `iniciar("channels")` chamado, **sem** `instrumentar_fastapi` **(deliberado)** | Este app também serve WebSocket (`/ws`) — a auto-instrumentação HTTP do FastAPI quebra o handshake em silêncio nesse caso (chat cai com "sem conexão"). RED automático fica só na `api`, que é REST puro. Métrica manual de conexões WebSocket ativas e mensagens por canal: **não implementada** ainda. |
| `agent` (worker LangGraph, sem HTTP) | instrumentação manual **(chegou a ser implementado; removido na revogação)** | 1 span (`agente.grafo`) por turno de conversa processado, mais o span de I/O do LangGraph dentro dele. Métricas implementadas: `agente.turno.duracao_ms` (histograma, label `canal`/`estagio`), `agente.mensagens_processadas` (counter, label `resultado=ok\|vazao\|handoff\|orcamento\|erro`), `agente.guardrail_escopo_recusas` (counter, label `categoria`), `agente.guardrail_vazao_ativacoes` (counter, label `janela=rajada\|hora`). Ainda não implementado: 1 span por nó do grafo e histograma de latência de LLM/Google Calendar isolados (ficam para uma fase futura — hoje entram dentro do span único do turno). |
| `resumidor` (worker) | `iniciar("resumidor")` chamado **(chegou a ser implementado; removido na revogação)** — reusa o mesmo processador (`handler.resumir`) do agente, então já herda o que for instrumentado em `graph.py`. Counter dedicado de itens processados/falhos: **não implementado**. |
| `scheduler`, `telegram-in`, `telegram-out`, `reativador` (workers) | **não implementado** | ficam para uma fase futura; hoje não chamam `iniciar()`. |
| Adapter `CalendarioGoogle` | instrumentação manual no adapter | histograma de latência da chamada à API do Google, counter de falhas — hoje essas falhas degradam silenciosamente para a agenda interna (por design), o que é ótimo para o cliente e péssimo para quem opera: sem essa métrica ninguém percebe que a integração caiu. |
| `db` (Postgres) | `postgres_exporter` (sidecar) | conexões ativas/máx, duração de query (`pg_stat_statements`), tamanho de tabelas, locks. |
| `redis` (streams = fila) | `redis_exporter` (sidecar) | memória usada, clientes conectados, ops/seg, **profundidade de cada stream** (equivalente a "mensagens na fila SQS") e consumer lag — é o sinal mais direto de "o agente está atrasado processando leads". |
| Todos os containers | `cAdvisor` | CPU/memória/disco por container — base do dashboard de saúde geral. |
| `apps/web`, `apps/dashboard` (frontend) | fora do escopo desta fase | Core Web Vitals via OTel JS ficaria numa fase 2, sem prioridade — o público do hackathon é a demo de sistema, não UX de frontend. |

**Cuidado com dado sensível em trace** (isso conecta direto com o trabalho de guardrails já feito): span
nunca leva o conteúdo da mensagem do cliente nem PII — só `lead_id` (idealmente um hash, não o valor
direto), `no`, `resultado`, contadores. O mesmo cuidado que motivou o mascaramento de CPF/cartão em
`guardrails/saida.py` vale para telemetria.

## 4. Catálogo de métricas propostas

**Saúde/infra**
- `up` por serviço (o Collector/exporters já fornecem via `up{job=...}` do Prometheus)
- CPU/memória/disco por container (cAdvisor)
- Conexões ativas do Postgres, duração de query p50/p95/p99
- Profundidade de stream do Redis, consumer lag por worker

**Latência e tráfego (RED — Rate, Errors, Duration)**
- `http_server_duration` (histograma) por rota × método × status — `api` e `channels`
- Taxa de erro 5xx por rota
- Conexões WebSocket ativas (gauge) — `channels`

**Agente / grafo / guardrails**
- Duração por nó do grafo (histograma, label `no`)
- Mensagens processadas por resultado (`counter`, label `resultado=ok|recusado|rate_limited|erro`)
- Recusas do guardrail de escopo (`escopo.avaliar`) por motivo
- Ativações do rate limiter (`vazao.py`) — rajada vs. hora
- Latência de chamada ao LLM (histograma) — complementa (não substitui) o custo/tokens já registrado
  em `RegistradorUso`
- Latência e falhas da chamada ao Google Calendar

**Filas / workers**
- Itens processados/falhos por worker (`resumidor`, `scheduler`)
- Tempo de processamento por item

## 5. Dashboards Grafana propostos

1. **Visão geral do sistema** — status `up` de cada serviço, CPU/memória por container, conexões do
   Postgres, profundidade das streams do Redis. É a tela para abrir primeiro numa demo ou num incidente.
2. **API & Canais — tráfego e latência (RED)** — requisições/seg, p50/p95/p99 por rota, taxa de erro,
   conexões WebSocket ativas.
3. **Agente — execução do grafo e guardrails** — duração por nó, taxa de recusa do guardrail de escopo,
   ativações do rate limiter, latência de LLM e de Google Calendar.
4. **Filas e workers** — profundidade de stream por fila, consumer lag, itens processados/falhos por
   worker.
5. **Banco de dados** — conexões, queries mais lentas, tamanho de tabelas, locks.

O dashboard de **negócio** (funil, temperatura, custo de LLM) continua sendo o painel React existente
(Visão geral / Governança) — não é recriado em Grafana; onde ajudar, um painel técnico linka para lá.

## 6. Alertas sugeridos (fase futura, depois dos dashboards)

- Taxa de erro 5xx acima de X% por 5 min, em `api` ou `channels`.
- p95 de latência HTTP acima de um limiar por rota crítica (`/leads`, `/eventos`).
- Profundidade de stream do Redis crescendo sem consumo (worker parado).
- Rate limiter do agente disparando com frequência anormal (possível ataque/flood — liga direto com o
  guardrail de vazão já implementado).
- Taxa de falha do adapter `CalendarioGoogle` acima de um limiar (degradação silenciosa virando visível).
- Conexões do Postgres perto do limite configurado.

## 7. Plano de implementação faseado

- **Fase 0 (feito):** este documento + ADR-0005.
- **Fase 1 — infraestrutura (feito):** `otel-collector`, `tempo`, `prometheus`, `postgres-exporter`,
  `redis-exporter`, `cadvisor` e `grafana` no `local/docker-compose.yml`, atrás de
  `--profile observability` (junto do `langfuse` já existente). `infra/otel/collector-config.yaml`,
  `infra/tempo/tempo.yaml`, `infra/prometheus/prometheus.yml` e
  `infra/grafana/provisioning/` (datasources Prometheus+Tempo, provider de dashboards) criados.
- **Fase 2 — auto-instrumentação (feito, com uma correção no meio do caminho):** `api` chama
  `iniciar("api")` + `instrumentar_fastapi(app)` no bootstrap (`shared/sdr_shared/observabilidade/otel.py`)
  — mesmo padrão de "helper em `shared/` usado por todo serviço" já usado para `RegistradorUso`.
  `channels/local` chama só `iniciar("channels")`, sem `instrumentar_fastapi`: essa auto-instrumentação
  chegou a ser ligada ali também, mas quebrava o handshake do WebSocket (`/ws`) assim que
  `SDR_OTEL_ENDPOINT` era configurado — o widget do site caía com "sem conexão". Removida de propósito;
  RED automático fica restrito à `api`, que é REST puro. Auto-instrumentação de queries Postgres
  (`-psycopg`) ainda não ligada (dependência já está no extra, falta o `.instrument()`).
- **Fase 3 — agente e guardrails (feito, com escopo reduzido):** span por turno e métricas manuais em
  `agent/handler.py`, `guardrails/escopo.py` e `guardrails/vazao.py` (ver tabela do §3). **Não feito
  ainda**, deliberadamente adiado: 1 span por nó do grafo, histograma de latência isolado de LLM e de
  `CalendarioGoogle`, métricas de `scheduler`/`telegram-in`/`telegram-out`.
- **Fase 4 — infra externa (feito):** `postgres_exporter`, `redis_exporter`, `cAdvisor` no compose
  (incluídos já na Fase 1 acima, já que o compose é um arquivo só).
- **Fase 5 — dashboards (feito, alertas pendentes):** três dashboards versionados em
  `infra/grafana/dashboards/`:
  1. **Mora — Visão Geral** (`visao-geral.json`) — RED da API, duração do turno do agente, turnos
     por resultado, guardrails, conexões do Postgres, memória do Redis e CPU por container.
  2. **Mora — API & Canais (RED)** (`api-canais-red.json`) — requisições/s e latência p50/p95/p99
     por serviço e rota, requisições por status code, taxa de erro 5xx por serviço, top rotas mais
     lentas.
  3. **Mora — Banco, Filas e Containers** (`infra-banco-filas.json`) — conexões e tamanho do
     Postgres, profundidade de cada stream do Redis e consumer lag por grupo (via
     `redis-exporter --check-streams`), memória/operações do Redis, CPU e memória por container.

  Os dashboards 2 e 3 dependem de dois ajustes feitos junto: o coletor agora promove `service.name`
  a label (`resource_to_telemetry_conversion`, em `infra/otel/collector-config.yaml`) — sem isso não
  dava para separar métricas de `api` vs. `channels` vs. `agent` — e o `redis-exporter` roda com
  `--check-streams=*` para expor profundidade e lag por stream/grupo, que antes só existia como
  conceito no plano. Os nomes exatos de algumas métricas do `redis-exporter`
  (`redis_stream_length`, `redis_stream_group_lag`) foram usados conforme a documentação do exporter,
  mas ainda não foram vistos com dado real — se algum painel do dashboard 3 aparecer vazio, o nome da
  métrica é o primeiro lugar para conferir (`http://localhost:9091/graph` no perfil local, testando a
  query direto). Regras de alerta do §6 **ainda não foram criadas**.

Cada fase foi entregue de forma independente, como planejado — dá para rodar hoje com só a Fase 1+2
(RED de API/canais) ou com tudo, via o mesmo `--profile observability`.

## 8. Onde cada peça entrou no repo

Caminhos de então, todos removidos na revogação — `infra/`, inclusive, deixou de existir por inteiro
quando as stacks em nuvem saíram do repositório. A lista fica para quem quiser refazer o caminho.

```
shared/sdr_shared/observabilidade/otel.py   # setup do SDK OTel: iniciar(), tracer(), contador(), histograma(), instrumentar_fastapi()
infra/otel/collector-config.yaml            # pipeline do Collector (receivers/exporters)
infra/tempo/tempo.yaml                      # storage local do Tempo
infra/prometheus/prometheus.yml             # scrape configs (otel-collector, exporters, cadvisor)
infra/grafana/provisioning/                 # datasources (Prometheus, Tempo) + provider de dashboards
infra/grafana/dashboards/*.json             # visao-geral, api-canais-red, infra-banco-filas (§5)
local/docker-compose.yml                    # serviços otel-collector/tempo/prometheus/postgres-exporter/
                                             # redis-exporter/cadvisor/grafana, atrás de --profile observability;
                                             # SDR_OTEL_ENDPOINT propagado a todos os serviços Python (vazio por padrão)
```

## 9. Relação com o Langfuse já opcional no compose

O compose local já tem `langfuse` (perfil `observability`) — mas resolve um problema diferente:
observabilidade de **prompt e conversa** (o que foi perguntado ao modelo, o que ele respondeu, por que
um nó tomou tal decisão). OTel+Grafana resolve observabilidade de **sistema** (o serviço está no ar,
está rápido, está enfilerando). Os dois convivem como dois blocos opcionais do compose, sem sobreposição
de responsabilidade — nenhum substitui o outro.
