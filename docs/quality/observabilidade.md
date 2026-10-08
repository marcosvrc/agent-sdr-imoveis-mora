---
title: Observabilidade
description: A observabilidade leve do Mora — tabelas no Postgres, /health, logs JSON e Langfuse opcional.
---

# Observabilidade

A observabilidade em vigor é a **leve** (ADR-0011): tabelas no Postgres (`turnos`, `saude`,
`batimentos`), `/health` que devolve `503` de verdade, logs estruturados em JSON e a aba **Saúde do
sistema** no painel.

Não há stack de métricas / tracing por padrão — a de OpenTelemetry + Grafana foi **revogada** (ADR-0005)
por consumo de recursos na máquina de desenvolvimento. O **Langfuse** sobe por opção
(`--profile observability`), mas **nenhum código envia trace a ele ainda**.

## Sinais disponíveis

| Sinal | Onde | Detalhe |
|---|---|---|
| Logs | `docker compose logs -f <serviço>` | JSON estruturado por serviço (`shared/sdr_shared/log.py`). |
| Health checks | `GET /health` (API e canais) | `503` quando degradado. |
| Uso de tokens | Aba de Governança do painel | Registrado por chamada; custo por modelo e série diária. |
| Saúde do sistema | Aba do painel | Tabelas `turnos`, `saude`, `batimentos`. |

## Langfuse (opcional)

```bash
make local    # some o compose; adicione --profile observability para o Langfuse
```

Langfuse fica em <http://localhost:3001> (a 3000 é do painel do CRM; `LANGFUSE_HOST_PORT` muda) e
serviria para observabilidade de **prompt e conversa** — o que foi perguntado ao modelo e o que ele
respondeu. Hoje é só o serviço: não há SDK do Langfuse instalado nem chave configurada, então a
interface abre vazia. Integrar é trabalho por fazer; até lá, o que existe de observabilidade é o
das tabelas acima. Quem integrar define `LANGFUSE_NEXTAUTH_SECRET` e `LANGFUSE_SALT` no
`local/.env` — os padrões do compose são de desenvolvimento, aceitáveis só porque a porta fica no
loopback.

!!! note "Duas observabilidades diferentes"
    Langfuse cobre prompt / conversa; a stack OTel + Grafana (revogada) cobria saúde de sistema. A
    página [Observabilidade de sistema (referência)](../observabilidade.md)
    guarda o desenho original da stack revogada, como referência caso valha reimplementar no futuro.
