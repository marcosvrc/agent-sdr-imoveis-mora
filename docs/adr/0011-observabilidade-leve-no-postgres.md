# ADR-0011 — Observabilidade leve: três tabelas no Postgres em vez de uma stack

**Status:** aceito · **Data:** 2026-09-12

## Contexto

O [ADR-0005](0005-observabilidade-com-opentelemetry-e-grafana.md) foi implementado e revogado no
mesmo dia: OpenTelemetry + Collector + Prometheus + Tempo + Grafana + três exporters somavam ~7
containers residentes que competiam por CPU e RAM com o Ollama na mesma máquina de desenvolvimento.
O efeito prático foi o oposto do pretendido — turnos do agente de 40-50s que pareciam travados.

Mas o problema que motivou o ADR-0005 continua de pé, e o episódio que o expôs foi concreto: o
container do Ollama não estava rodando, o agente falhava em toda chamada de embedding e **ninguém
percebeu por vinte minutos**. O que faltava não era um sistema de tracing distribuído. Era saber
três coisas:

1. **quanto o cliente esperou** — `uso_llm.latencia_ms` mede uma chamada de modelo isolada, não o
   turno inteiro (transcrição, guardrails, RAG, embedding, banco, despacho ao canal);
2. **o que está parado na fila** — profundidade dos streams do Redis;
3. **quem morreu** — um worker que caiu não reporta a própria morte.

Nenhuma dessas três precisa de coletor, de série temporal dedicada ou de um processo novo. E há um
Postgres já rodando, já com pool de conexão, já lido pelo painel que o corretor abre todo dia.

## Decisão

Gravar observabilidade **como dado de aplicação, no Postgres que já existe**, e mostrá-la na tela
do painel que já existe. Sem coletor, sem exporter, sem container adicional.

**Três tabelas** (`shared/sdr_shared/db/schema.sql`), servidas por `db/monitoramento.py`:

| tabela | escrita | volume | serve |
|---|---|---|---|
| `turnos` | 1 INSERT por turno, no `handler` | ~1 linha por mensagem de cliente | p50/p95 da espera, taxa de falha, caminho pelo grafo |
| `saude` | 1 INSERT a cada 30s, no laço do scheduler | 2.880 linhas/dia | profundidade das filas, conexões do banco |
| `batimentos` | 1 UPSERT a cada 30s por serviço | 6 linhas, fixo | quem está de pé |

Retenção de **7 dias**, aparada pelo próprio `amostrar()` uma vez por hora — sem cron, sem job.
Em uma semana de operação de POC isso é da ordem de 20 mil linhas: irrelevante para o Postgres.

**Toda escrita é best-effort.** `registrar_turno`, `amostrar` e `bater` engolem a própria exceção:
observar nunca pode derrubar o atendimento. Um `/health` que mente é ruim; um monitoramento que
mata o turno que estava medindo é pior.

**`/health` de verdade.** Antes, `api` e `channels` devolviam `{"ok": true}` incondicionalmente —
decoração, não monitoramento. Agora a `api` verifica o banco e lê `batimentos` (503 se algum
serviço está calado há mais de 120s) e o `channels` faz ping no Redis (503 se o barramento caiu,
porque um canal sem barramento aceita o WebSocket e some com a mensagem). O `docker-compose.yml`
usa os dois como `healthcheck`, então `docker compose ps` passa a mostrar `(unhealthy)` em vez de
`Up` com o chat mudo. É também o gancho pronto para qualquer monitor externo, se um dia houver um.

**Detecção de morte por terceiro.** Cada worker sobe uma thread daemon que carimba `batimentos` a
cada 30s. Daemon de propósito: se o processo principal morre, a thread morre junto e o carimbo
para de ser atualizado — que é exatamente o sinal desejado. Quem interpreta a ausência é outro
processo (a `api`, no `/health`, e a tela de saúde).

**Log estruturado** (`shared/sdr_shared/log.py`): uma linha JSON por evento, com `lead_id` e
`canal` do turno em toda linha via `ContextVar`. Ligado por padrão fora do perfil `local` (onde o
formato legível continua sendo o padrão, porque ali quem lê é uma pessoa). Isso cobre a metade
"eventos" da observabilidade — `docker compose logs agent | jq 'select(.duracao_ms > 10000)'`, sem
regex.

**Uma tela** (`/saude` no painel): espera típica e ruim, taxa de falha, barras por hora, filas,
serviços vivos ou mortos. Mesma autenticação do resto do painel — dado de operação não é público.

## Consequências

**A favor**

- Custo residente de infraestrutura: **zero**. Nenhum container, nenhum processo, nenhuma porta.
- O sinal que faltava no episódio do Ollama passa a ser visível em três lugares independentes:
  `docker compose ps` (unhealthy), a tela de saúde (serviço em vermelho) e o p95 do período.
- O p95 do turno é medido de ponta a ponta, do jeito que o cliente sente — não por componente.
- Nada aqui é específico de ambiente: as tabelas, o `/health` e a tela funcionam onde o compose
  subir, que hoje é a máquina de quem avalia — nada está implantado.
- Sobrevive à revogação do ADR-0005: nada aqui depende de OTel, e nada aqui impede adotá-lo depois.

**Contra, e assumido**

- **Não é tracing.** Não há span por operação, não há correlação entre serviços, não há flame
  graph. O `nos` de `turnos` (por quais nós do grafo o turno passou) é a aproximação barata disso,
  e para um grafo de 8 nós ela responde a maior parte das perguntas.
- **Cardinalidade fixa.** Não dá para fatiar por dimensão arbitrária como em Prometheus; as
  agregações são as que estão escritas no SQL de `resumo_de_turnos`.
- **Escrita síncrona no caminho do turno.** Um INSERT por turno, na mesma transação-conexão do
  pool. Medido, é ruído diante de uma chamada de LLM; mas é uma dependência a mais no caminho
  quente — mitigada por ser best-effort.
- **Sem alerta ativo.** Ninguém é avisado; alguém precisa olhar (a tela, ou o `docker compose ps`).
  Para a POC é aceitável, e o `/health` já é o gancho pronto para um alarme externo.
- **Sem retenção longa.** 7 dias. Análise de tendência mensal não é possível — e não é o objetivo.

## Alternativas consideradas

**Voltar ao ADR-0005 com menos componentes** (só Prometheus + Grafana, sem Tempo/Collector/
exporters). Ainda são dois containers residentes, ainda concorrendo com o Ollama, e ainda exigindo
que o corretor abra uma segunda ferramenta para ver o estado do sistema. O ganho sobre o que está
aqui — cardinalidade e retenção — não é o que a POC precisa.

**Um SaaS de observabilidade** (Grafana Cloud, Datadog, Better Stack). Zero peso local, mas
introduz credencial, egress de dados de conversa para terceiro e uma dependência externa em um
projeto cujo argumento é rodar inteiro na máquina. Descartado pelo mesmo motivo que o LiteLLM
hospedado no [ADR-0009](0009-gateway-de-llm-litellm-openrouter-ou-nada.md).

**Só log estruturado, sem tabelas.** Barato e suficiente para investigar um incidente pontual, mas
não responde "o p95 piorou esta semana?" sem alguém rodar uma consulta ad hoc, e não coloca nada na
frente de quem usa o sistema. As tabelas custam pouco e viram tela.
