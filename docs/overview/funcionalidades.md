---
title: Funcionalidades
description: Estado real das funcionalidades do Mora, por componente — implementadas, parciais e planejadas.
---

# Funcionalidades

As tabelas refletem o estado descrito no repositório. Legenda:

- :material-check-circle:{ .mora-ok } **Concluída** — implementada e com teste ou build associado.
- :material-progress-clock:{ .mora-warn } **Parcial** — escrita, mas sem teste automatizado ou dependente de serviço externo.
- :material-calendar-blank: **Planejada** — prevista, não implementada.

!!! warning "Itens parciais"
    As funcionalidades marcadas como **Parcial** não devem ser tratadas como prontas para produção.

## Agente de IA (`services/agent`)

| Funcionalidade | Estado | Evidência |
|---|---|---|
| Grafo multiagente (supervisor, qualificador, consultor, agendador, follow-up, handoff, resumidor, reativador) | Concluída | `tests/test_cenarios.py` |
| Reativação proativa: imóvel novo → leads adormecidos, com motivo, cadência e opt-out | Concluída | ADR-0013, `tests/test_reativacao_fluxo.py`, `shared/tests/test_reativacao.py` |
| RAG híbrido com cascata por localidade (bairro → vizinhos → região → cidade) | Concluída | `tools/buscar_imoveis.py`, `test_cenarios.py` |
| Agendamento de visita em dois turnos (oferta de horários → confirmação) | Concluída | `nodes/agendador.py` |
| Scoring de temperatura do lead (quente / morno / frio) | Concluída | `test_cenarios.py` |
| Guardrails de escopo, saneamento de saída e rate limiting | Concluída | `tests/test_seguranca.py` |
| Governança de LLM: registro por chamada, custo por modelo, orçamento com degradação | Concluída | `tests/test_governanca.py` |
| Transcrição de áudio — faster-whisper in-process, motor único | Concluída | `tools/transcricao.py`, `tests/test_transcricao.py` |
| Download de voz do Telegram para transcrição (getFile + download) | Concluída | `tools/transcricao.py`, `tests/test_transcricao.py` |
| Busca institucional sobre Postgres + pgvector, com piso de similaridade e reescrita de consulta | Concluída | ADR-0001, `tools/conhecimento.py` |
| Fusão léxica (RRF) na busca institucional | Parcial | implementada e **desligada** por padrão (`SDR_RAG_LEXICO`): no A/B o recall@3 caiu de 31,9% para 29,8% |
| Harness de avaliação com dataset e métricas de RAG | Concluída | `services/agent/evals/`, `make eval-rag` |

## Site (`apps/web`)

| Funcionalidade | Estado | Evidência |
|---|---|---|
| Landing com widget de chat, listagem, detalhe do imóvel, busca e filtros | Concluída | `npm run build` (TypeScript estrito) |
| PWA, tracking de navegação, SEO / acessibilidade | Concluída | ADR-0012, `vite-plugin-pwa` |
| CTA de continuidade no Telegram (mantém histórico) | Concluída | ADR-0006 |

## Painel administrativo (`apps/dashboard`)

| Funcionalidade | Estado | Evidência |
|---|---|---|
| Visão geral, leads, conversas ao vivo, agenda, imóveis, corretores | Concluída | `npm run build` |
| Configurações do agente e governança de IA (tokens, custos, limites) | Concluída | `routers/config.py`, `routers/governanca.py` |
| Auditoria e aba de saúde do sistema (observabilidade leve) | Concluída | ADR-0011, `routers/auditoria.py`, `routers/dashboard.py` |
| Interesses lead↔imóvel, simulação seca da reativação e interruptor de aviso na ficha do lead | Concluída | `components/Interesses.tsx`, `components/SimularReativacao.tsx`, `tests/test_api.py` |
| Funil da reativação na Visão geral (avisos → respostas → visitas → saídas) | Concluída | ADR-0013, `GET /dashboard/reativacao`, `components/ReativacaoResumo.tsx` |
| Tema claro / escuro / sistema, com contraste verificado nos dois | Concluída | ADR-0014, `components/SeletorTema.tsx`, axe-core em 11 telas |

## Backend, integrações e infraestrutura

| Funcionalidade | Estado | Evidência |
|---|---|---|
| API REST (imóveis públicos, leads, dashboard, handoff, eventos, config, governança, auditoria) | Concluída | `services/api`, `tests/test_api.py` |
| Canal Telegram — long polling (`getUpdates`), sem webhook e sem URL pública | Concluída | ADR-0007, `services/channels/telegram` |
| Canal Web (WebSocket) | Concluída | `services/channels/local` |
| Follow-up automático e ingestão de imóveis | Concluída | `services/scheduler`, `services/ingestion` |
| Ingestão de documentos institucionais (FAQ, políticas, taxas) para a tabela `documentos` do pgvector | Concluída | `sdr_ingestion/ingest_documentos.py`, `make docs-kb`, `shared/tests/test_conhecimento.py` |
| Integração Google Agenda do corretor | Parcial | `tools/agenda.py`; opcional, degrada para agenda interna |
| Ambiente completo em `docker compose` (Postgres+pgvector, Redis, workers, front-ends, CRM) | Concluída | `local/docker-compose.yml` |

Para o que **não** está pronto e os débitos técnicos, veja [Roadmap e limitações](../project/roadmap.md).
