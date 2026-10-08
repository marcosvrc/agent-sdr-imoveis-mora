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

O schema vive em `shared/sdr_shared/db/schema.sql` e é idempotente
(`CREATE`/`ALTER ... IF NOT EXISTS`).

```bash
# Aplicado automaticamente na PRIMEIRA subida do container db (initdb.d); para reaplicar:
make migrate

# Execução manual:
psql "$SDR_DATABASE_DSN" -f shared/sdr_shared/db/schema.sql
```

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

Os testes usam um banco separado, **`sdr_test`**. As suítes apagam tabelas e uma trava recusa rodar
contra um banco sem "test" no nome. Veja [Testes](../quality/testes.md).

## Tabelas de observabilidade

A observabilidade leve grava três tabelas no próprio Postgres — `turnos`, `saude` e `batimentos`
(ADR-0011). Veja [Observabilidade](../quality/observabilidade.md).

## Vetores e RAG

Os embeddings ficam no pgvector, em duas tabelas: `imoveis.embedding` (catálogo, com cascata por
localidade) e `documentos.embedding` (documentos institucionais fatiados, com a coluna gerada `busca`
em `tsvector` para a fusão léxica). Ambas são `vector(1024)` — a dimensão do `bge-m3`, o único modelo
de embeddings do projeto, servido pelo Ollama. Reindexe o catálogo com `make seed` após alterar
bairros ou descrições, e os documentos com `make docs-kb`. Veja
[Dados e persistência](../architecture/dados.md).

!!! info "Ingestão"
    `services/ingestion` carrega imóveis e gera embeddings. No local, `make seed` cria 400 imóveis
    determinísticos.
