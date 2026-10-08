---
title: Banco de dados
description: PostgreSQL + pgvector, schema, migrations e o banco único que atende dados e vetores.
---

# Banco de dados

## Motor

**PostgreSQL com a extensão pgvector**, armazenando dados relacionais e vetores na mesma base
(ADR-0004): container `pgvector/pgvector:pg16` do `local/docker-compose.yml`, porta host 5433 → 5432
(ajustável por `DB_HOST_PORT`).

Há um servidor só, o do compose. Não existe variante gerenciada: o que havia de banco hospedado saiu
do projeto junto com a infraestrutura em nuvem. Dentro dele, o CRM tem **banco próprio** (`crm`),
separado do `sdr` — é o que faz a regra de que nada da Mora escreve direto no CRM ser estrutural, e
não só combinada (ver [decisões](../decisions.md) D-02).

## Schema e migrations

São dois schemas, um por banco, ambos idempotentes (`CREATE`/`ALTER ... IF NOT EXISTS`):
`shared/sdr_shared/db/schema.sql` (banco `sdr`, da Mora) e `services/crm/sdr_crm/db/schema.sql`
(banco `crm`). Não há ferramenta de migration: coluna nova entra como `ALTER TABLE ... ADD COLUMN IF NOT
EXISTS` no próprio arquivo.

```bash
# No compose, o serviço db-init cria os bancos e aplica os dois schemas a CADA `up`,
# antes de qualquer serviço Python. Para reaplicar com tudo no ar:
make migrate        # banco sdr
make crm-migrate    # banco crm

# Execução manual:
psql "$SDR_DATABASE_DSN" -f shared/sdr_shared/db/schema.sql
```

## Tabelas da Mora (banco `sdr`)

| Tabela | O que guarda |
| --- | --- |
| `clientes` | A **pessoa**: uma por telefone/e-mail, a mesma no Telegram e na web. |
| `leads` | A **oportunidade** de um cliente: cartão de qualificação, estágio, corretor, resumo e análise. Um cliente pode ter várias ao longo do tempo. |
| `canais` | Identificadores de canal (`web`, `telegram`) de cada lead — um histórico só para vários canais (ADR-0003). |
| `mensagens` | Histórico da conversa, por lead e direção. |
| `imoveis` | Catálogo indexado, com `embedding vector(1024)`; `retirado_em` marca o que saiu da oferta sem apagar o histórico. |
| `interesses` | Lead × imóvel, N:N e fraco: interesse não é reserva. |
| `visitas` | Visitas marcadas, com corretor e status. |
| `followups_agendados` | Um follow-up pendente por lead; o scheduler dispara. |
| `eventos_navegacao` | O que a sessão do site viu (imóveis vistos), usado pelo turno do chat. |
| `corretores` | Equipe: nome, contato, foto, ativo; vínculo com o usuário do CRM pelo e-mail. |
| `notificacoes` | Avisos para o corretor (lead quente, handoff, visita). |
| `configuracoes` | Configurações editáveis pelo painel (chave → JSON); os padrões ficam no código. |
| `uso_llm` | Uma linha por chamada de modelo: papel, modelo, tokens, cache, custo e latência. |
| `auditoria` | Quem fez o quê, no painel e no agente. |
| `documentos` | Base institucional fatiada para o RAG: `assunto`, `titulo` (vira a citação), `embedding` e `busca` (`tsvector`). |
| `crm_vinculo` | Lead da Mora ↔ lead e oportunidade no CRM, com a versão para o `If-Match`. |
| `crm_pendencias` | Turnos a publicar no CRM que falharam; o scheduler drena. |
| `crm_reconhecimento` | Cache da busca do cliente no CRM por contato (hash), para não procurar a cada turno. |
| `turnos`, `saude`, `batimentos` | Observabilidade leve (ADR-0011), ver abaixo. |

## Tabelas do CRM (banco `crm`)

| Tabela | O que guarda |
| --- | --- |
| `users`, `sessions` | Usuários humanos do painel do CRM (login por e-mail) e as sessões abertas. |
| `service_credentials` | Credenciais de serviço — a da Mora, emitida por `make crm-token` (só o hash). |
| `leads`, `opportunities`, `preferences` | A pessoa, cada intenção dela e as exigências de cada intenção (1:1 com a oportunidade). |
| `properties`, `property_photos`, `property_interests` | Catálogo da imobiliária, fotos (com `alt`) e interesse por imóvel. |
| `interactions` | Histórico de interações publicado pela Mora e pelos corretores. |
| `availability_slots`, `visits` | Agenda por imóvel e visitas (remarcação aponta para a substituta). |
| `tasks`, `handoffs` | Trabalho do corretor: tarefas e passagens de bastão do agente. |
| `audit_events` | Auditoria **somente append**: não há `UPDATE` nem `DELETE` nela no código. |
| `idempotency_records` | Respostas já dadas a uma `Idempotency-Key`, gravadas na mesma transação da mutação (validade: `CRM_IDEMPOTENCIA_HORAS`). |

## Restrições e índices que a aplicação usa como regra

| Objeto | O que garante | Por quê |
| --- | --- | --- |
| `visitas_corretor_inicio_uk` — único parcial em `visitas (corretor_id, inicio)` `NULLS NOT DISTINCT WHERE status = 'confirmada'` | um horário de um corretor é de uma visita; sem corretor, a grade da equipe é uma agenda só | verificar-e-inserir deixava dois leads passarem juntos; a aplicação traduz a recusa em `HorarioOcupado`. **Só é criado se o banco não tiver o conflito gravado**: com duplicata, o `make migrate` emite um `WARNING` com a contagem e segue — remarque as visitas e rode de novo |
| `clientes_telefone_idx`, `clientes_email_idx` (únicos parciais) | uma pessoa por telefone/e-mail | `ClienteRepository.vincular` nunca grava em um cliente o contato que é de outro (conflito vai para a auditoria) e, na corrida de dois turnos, quem perde relê o cliente criado |
| `eventos_navegacao_sessao_idx` (`session_id, tipo`) | `imoveis_vistos` sem varrer a tabela | roda em todo turno do chat do site |
| `canais_lead_idx` (`lead_id`) | canais de um lead | resposta do corretor, migração de canal, sucessão de oportunidade |
| `visitas_lead_idx` (`lead_id, inicio`) | visitas de um lead | próxima visita, ficha do cliente, atribuição de corretor |
| `leads_corretor_abertos_idx` (`corretor_id`, parcial `encerrado_em IS NULL`) | carteira do corretor | desativação, filtro por corretor no painel |
| `mensagens_direcao_em_idx` (`direcao, em`) | contagens por direção num período | KPIs e série diária da Visão geral |

**Transações.** O pool da Mora abre conexões em **autocommit**: cada `execute` é um commit. Operação
que mexe em várias tabelas (desativar corretor, atribuir corretor, assumir handoff, sucessão de
oportunidade, vincular cliente) abre `with conn.transaction():` e usa a **mesma conexão** em todas as
instruções — os métodos do repositório aceitam `conn=` para isso (`repositories.py::_usar`).

**Fuso.** O Postgres do compose roda em UTC. Corte de dia e mês (orçamento, séries diárias) é feito
explicitamente em `America/Sao_Paulo` (`em AT TIME ZONE 'America/Sao_Paulo'`), nunca com `em::date`.

**Retenção.** `turnos` e `saude` guardam 7 dias. `eventos_navegacao` ainda não tem retenção: cresce
com o tráfego do site, e o índice por sessão é o que mantém a consulta do turno barata.

## Banco de testes

Os testes usam bancos separados: **`sdr_test`** para a Mora e **`crm_test`** para o CRM. As suítes
apagam tabelas e uma trava recusa rodar contra um banco sem "test" no nome. Veja [Testes](../quality/testes.md).

## Tabelas de observabilidade

A observabilidade leve grava três tabelas no próprio Postgres — `turnos`, `saude` e `batimentos`
(ADR-0011). Veja [Observabilidade](../quality/observabilidade.md).

## Vetores e RAG

Os embeddings ficam no pgvector, em duas tabelas: `imoveis.embedding` (catálogo, com cascata por
localidade) e `documentos.embedding` (documentos institucionais fatiados, com a coluna gerada `busca`
em `tsvector` para a fusão léxica). Ambas são `vector(1024)`: é a dimensão nativa do `bge-m3`
(Ollama), e o `text-embedding-3-small` (OpenAI ou OpenRouter, o que vem no `local/.env.example`) é
pedido reduzido a 1024. Os dois modelos não se misturam no mesmo índice: trocar de um para o outro
exige reindexar tudo. Reindexe o catálogo com `make seed` após alterar
bairros ou descrições, e os documentos com `make docs-kb`. Veja
[Dados e persistência](../architecture/dados.md).

!!! info "Ingestão"
    `services/ingestion` carrega imóveis e gera embeddings. No local, `make seed` cria 400 imóveis
    determinísticos.
