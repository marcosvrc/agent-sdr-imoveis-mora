---
title: Roadmap e limitações
description: O que vem depois e o que não está pronto no Mora — próximos passos por horizonte, limitações conhecidas, débitos e dependências externas.
---

# Roadmap e limitações

Esta página lista o que **não** está pronto e o que vem depois — separada das
[Funcionalidades implementadas](../overview/funcionalidades.md). A ordem dentro de cada horizonte é
a ordem sugerida de execução; nenhum item abaixo tem código escrito.

## Atividades futuras

### Curto prazo — fechar o que a POC deixou aberto

| # | Atividade | Por que | Onde mexe |
|---|---|---|---|
| 1 | **Migrar `react-router` 6 → 7** nas três apps | Dois avisos moderados do `npm audit` (open redirect via `\` e deserialização em SSR); o site é SPA, então o risco é baixo, mas a major é a única correção | `apps/web`, `apps/dashboard`, `apps/crm` |
| 2 | **Screenshots por tela no [Manual do CRM](../user-guide/crm.md)** | O texto foi escrito em 2026-09; sem imagem ainda exige subir o ambiente para entender | `docs/user-guide/crm.md` |
| 3 | **Publicar a especificação OpenAPI do CRM** | `make openapi` gera só a da API da Mora; as rotas do CRM (`/properties/{id}/status`, `/visits/{id}/reschedule`, `/brokers`) existem só no `/openapi.json` do serviço no ar | `scripts/gerar_openapi.py`, `docs/technical-reference/openapi.md` |
| 4 | **Sessão individual no painel da Mora** | Hoje um token único para a equipe (`SDR_PAINEL_TOKEN`); a auditoria registra "painel", não a pessoa. O CRM já tem login por usuário — o painel pode reaproveitar o modelo | `services/api/src/api/auth.py`, `apps/dashboard/src/lib/auth.ts` |
| 5 | **Correlação entre serviços** | O CRM gera `request_id` próprio e a Mora loga por `lead_id`; nada atravessa o MCP. Propagar um id de turno pelo cabeçalho do MCP liga o turno à linha de auditoria do CRM | `shared/sdr_shared/adapters/crm/via_mcp.py`, `services/crm/sdr_crm/mcp/` |
| 6 | **Escapar `%`/`_` na busca `ILIKE`** e trocar `CORS *` padrão por lista explícita fora do perfil local | Achados menores da revisão de setembro que ficaram fora do plano de 16 itens | `services/api/src/api/routers/imoveis.py`, `services/api/src/api/main.py` |

### Médio prazo — operar com mais de um corretor de verdade

| # | Atividade | Por que | Onde mexe |
|---|---|---|---|
| 7 | **Retenção e exclusão de dados pessoais (LGPD)** | Não há rotina de expurgo nem endpoint de exclusão a pedido do titular; transcrições e cartões ficam para sempre | `shared/sdr_shared/db/schema.sql`, scheduler, painel |
| 8 | **Fonte única das fotos: mover o upload para o CRM** | Hoje painel > CRM > arquivo, determinístico e documentado (ADR-0015), mas duas fontes. O caminho recomendado é o CRM receber o arquivo e servir a imagem — sem tocar na trava `exigir_humano` | `services/crm`, `apps/crm`, remover a tela do painel |
| 9 | **Rate limit distribuído** | O contador é em memória, por processo; com duas réplicas da API do CRM o teto dobra. Redis (que já existe) resolve | `services/crm/sdr_crm/api/contexto.py` |
| 10 | **Ferramenta de migração de schema** | Hoje o schema é reaplicado inteiro pelo `db-init` (idempotente por `IF NOT EXISTS`); mudança destrutiva ou de tipo não tem caminho. Alembic ou migrações SQL numeradas | `shared/sdr_shared/db/`, `services/crm/sdr_crm/db/` |
| 11 | **Testes de comportamento dos front-ends no CI** | O CI faz build estrito, eslint e acessibilidade; os roteiros Playwright usados na verificação manual não rodam automaticamente | `apps/*/scripts`, `.github/workflows/ci.yml` |
| 12 | **Pacote de UI compartilhado** | `ui.tsx`, `formato.ts` e ícones existem em duplicata entre painel e CRM (com identidades visuais distintas de propósito) | `apps/` |

### Longo prazo — além da POC

| # | Atividade | Por que |
|---|---|---|
| 13 | **WhatsApp** de volta como adaptador | Saiu porque a Cloud API exige URL pública e número verificado (ADR-0007). Numa implantação real é o canal que o cliente usa; o desenho de adaptadores (ADR-0003) foi mantido para isso |
| 14 | **Implantação** (qualquer nuvem) | A entrega é o `docker compose` local por escolha. Implantar exige segredos de verdade (`SDR_SESSAO_SECRET`, `SDR_PAINEL_TOKEN`, chaves rotacionadas), TLS, e o item 4 acima |
| 15 | **Avaliação com modelo real versionada** | Os resultados em `services/agent/evals/resultados/` são todos com o modelo falso (o harness é testado; a qualidade não é medida no CI). Rodar `make eval` com modelo real e versionar o relatório dá base para o comparativo de modelos |
| 16 | **Fusão léxica do RAG** | Implementada atrás de `SDR_RAG_LEXICO`; o A/B piorou o recall (31,9 % → 29,8 %). Vale revisitar com outro reranking, não religar como está |
| 17 | **Consumidor para `sdr:events`** | O tópico é publicado a cada mudança de estágio e ninguém o consome — é o gancho natural para webhooks ou analytics |

## Limitações conhecidas

- **Um canal externo só: o Telegram.** O WhatsApp foi removido do código (ADR-0007).
- **Nada está implantado.** A entrega inteira é o `local/docker-compose.yml`, rodando na máquina de
  quem avalia — escolha, não pendência (ver [Execução e custo](../ARCHITECTURE.md#10-execucao-e-custo)).
- **Fusão léxica do RAG desligada por padrão** (`SDR_RAG_LEXICO`), pelo resultado do A/B.
- **Rate limiting por processo**, não distribuído.
- **Sem benchmarks** de performance nem de qualidade com modelo real versionados.
- **Sem testes de comportamento de front-end** (build estrito, lint e acessibilidade cobrem o front).
- **Duas fontes de foto do imóvel** (painel e CRM), com precedência fixa — ADR-0015.
- **Token único do painel** — a auditoria da Mora não distingue pessoas da equipe.

## Débitos técnicos / itens em aberto

- Análise de dependências não está no CI (a cobertura e o pyright estão).
- Observabilidade de sistema (OpenTelemetry / Grafana) foi revogada; existe a leve (ADR-0011).
- Papéis / permissões por usuário no painel da Mora: a definir (o CRM já tem `admin`/`broker`).
- Política formal de retenção e exclusão de dados (LGPD).
- `CRM_SESSION_SECRET` existe na configuração e não é usado.
- O `state` do OAuth do Google Calendar vale por 10 min e pode ser reusado dentro da janela.

## Riscos e dependências externas

- Disponibilidade e cota do provedor de LLM (`SDR_LLM_PROVIDER`). O reserva
  (`SDR_LLM_PROVIDER_FALLBACK`) reduz o risco, não o elimina.
- API do Telegram e API do Google Agenda, quando configurada — esta degrada para a grade interna,
  aquela não tem substituto.
- Custo variável: só as chamadas ao modelo. Embeddings, transcrição e banco rodam na máquina.

!!! tip "Transformar pendências em issues"
    A sugestão do projeto é converter estes itens e as [Pendências de documentação](pendencias.md) em
    issues, atualizando as páginas correspondentes quando resolvidas.
