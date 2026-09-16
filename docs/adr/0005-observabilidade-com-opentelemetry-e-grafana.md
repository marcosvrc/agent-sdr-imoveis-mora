# ADR-0005 — Observabilidade de sistema com OpenTelemetry + Grafana

**Status:** revogado em 2026-09-12 — implementado e depois removido (ver seção final); substituído pelo [ADR-0011](0011-observabilidade-leve-no-postgres.md) · **Data:** 2026-09-11

## Contexto
Hoje a observabilidade da Mora é só de **negócio**: o painel (Visão geral, Governança, Auditoria)
mostra leads, temperatura, chamadas ao LLM, custo e tokens — dados de aplicação, gravados no Postgres
via `RegistradorUso` (`shared/sdr_shared/governanca/uso.py`). Não existe visão de **saúde de sistema**:
latência por rota, taxa de erro HTTP, profundidade das filas Redis (que fazem papel de SQS), saúde do
Postgres, ou duração de cada nó do grafo do agente. Em produção (perfil `aws`) isso viraria CloudWatch;
no perfil `local` não há nada.

## Decisão
Adotar **OpenTelemetry** como padrão de instrumentação (traces + métricas) em todos os serviços Python
(`api`, `channels/local`, `agent`, `resumidor`, `whatsapp-out`, `scheduler`), exportando via OTLP para
um **OpenTelemetry Collector**, que alimenta **Prometheus** (métricas) e **Tempo** (traces). **Grafana**
como camada única de visualização, com datasources para Prometheus, Tempo e Postgres (para dashboards
que cruzam métrica técnica com dado de negócio).

Detalhamento completo (catálogo de métricas, dashboards, alertas, fases) em [`docs/observabilidade.md`](../observabilidade.md).

## Por que não Langfuse para isso
O compose local já tem `langfuse` (perfil `observability`) — mas é observabilidade de **prompt/conversa
LLM** (o quê foi perguntado, o quê o modelo respondeu, por que um nó decidiu X). OTel+Grafana é
observabilidade de **sistema** (o serviço está no ar? está lento? a fila está enchendo?). São
complementares, não concorrentes — ficam como dois perfis opcionais do compose.

## Alternativas consideradas
- **CloudWatch/X-Ray só em produção, nada em local:** mais simples, mas o hackathon precisa demonstrar
  saúde do sistema também em ambiente local/demo, e a instrumentação OTel no código é a mesma que
  alimentaria X-Ray via ADOT na AWS — não é trabalho jogado fora.
- **Prometheus + Grafana sem OpenTelemetry (client libs nativas por linguagem):** mais simples de
  começar, mas perde tracing distribuído (útil para ver o caminho de uma mensagem por
  canal → agente → LLM → banco) e amarra a instrumentação a uma stack só; OTel é vendor-neutral e o
  mesmo coletor serve Prometheus hoje e outro backend amanhã sem mexer no código instrumentado.

## Consequências
- (+) Uma única forma de instrumentar todo serviço novo (basta seguir `shared/sdr_shared/observabilidade/`).
- (+) Caminho direto para produção: os mesmos SDKs exportam para o ADOT Collector gerenciado da AWS.
- (−) Mais um bloco de infraestrutura no compose local (Collector + Prometheus + Tempo + Grafana) —
  fica atrás de `--profile observability`, como o Langfuse, para não pesar o `up` padrão.
- Este ADR fixa a decisão de arquitetura; a implementação (código, compose, dashboards) é trabalho
  futuro, deliberadamente não iniciado agora.

## Atualização (2026-09-12) — revogado
Implementado por completo (instrumentação em `api`/`agent`/`channels`, coletor OTel, Prometheus,
Tempo, `postgres_exporter`, `redis_exporter`, cAdvisor e três dashboards no Grafana) e testado em
ambiente local real. **Removido de volta em seguida** pelo motivo que o ADR não previu: os ~7
containers extras da stack de observabilidade competem por CPU/RAM com o Ollama (embeddings 100%
locais, ADR de LLM) na mesma máquina — e é justamente o Ollama que mais sofre com isso, criando
turnos do agente de 40-50s que pareciam travados, atrapalhando o próprio objetivo de demonstrar o
sistema funcionando bem. Em uma máquina de desenvolvedor rodando tudo junto (não um ambiente de
homologação com mais recursos), o custo superou o benefício para esta fase da POC.

Fica revertido por ora: código, `docker-compose.yml` e `infra/otel|tempo|prometheus|grafana` voltaram
ao estado anterior a este ADR. O Langfuse (observabilidade de LLM/prompt, ver seção acima) continua
disponível e é leve o suficiente para não competir por recursos da mesma forma. Se a necessidade de
observabilidade de sistema voltar (por exemplo, rodando em uma máquina com mais recursos, ou só em
produção via CloudWatch/X-Ray — que já não dependem desta stack), a análise, o catálogo de métricas e
os dashboards em `docs/observabilidade.md` continuam válidos como referência para reimplementar; o
código em si precisaria ser refeito, já que foi removido.

O substituto está no [ADR-0011](0011-observabilidade-leve-no-postgres.md): três tabelas no Postgres
que já roda, `/health` de verdade, log em JSON e uma aba no painel — zero container residente.
