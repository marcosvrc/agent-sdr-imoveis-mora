---
title: Dados e persistência
description: Postgres + pgvector, RAG híbrido com cascata por localidade e o banco único do Mora.
---

# Dados e persistência

## Um Postgres para tudo

O Mora usa **PostgreSQL com a extensão pgvector** para dados relacionais e vetores na mesma base: o
registro transacional (leads, visitas, imóveis), a busca vetorial, a agregação que o painel consulta
e o checkpointer do grafo cabem no mesmo banco (ADR-0004). É o container `db`
(`pgvector/pgvector:pg16`), publicado no host em `5433` para não colidir com um Postgres nativo.

O CRM é sistema à parte e tem **banco próprio** (`crm`) no mesmo servidor — a separação é o que
impede uma consulta cruzada de aparecer sem querer um dia.

O schema fica em `shared/sdr_shared/db/schema.sql`. Ele está montado em
`docker-entrypoint-initdb.d`, mas o Postgres só executa esses scripts quando o **volume é novo**:
num volume que já existia, quem aplica é `make migrate` (idempotente), que o `make preparar` chama.

## RAG híbrido com cascata por localidade

A recomendação de imóveis combina filtros estruturados com busca vetorial, expandindo a área de busca
em cascata quando necessário:

![Cascata da busca de imóveis](../assets/diagramas/busca-cascata.svg)

- **Embeddings.** Dois provedores, mesma dimensão: Ollama `bge-m3` (padrão, local) ou OpenAI
  `text-embedding-3-small` com `dimensions=1024` — o schema espera 1024, e trocar de modelo sem
  trocar essa coluna dá resultado errado sem erro nenhum. O local baixa com `make ollama-pull`.
- **Um caminho de RAG.** Busca vetorial direta no Postgres, no mesmo banco que o painel consulta
  (ADR-0001) — é o caminho testado, e é o único.

## RAG institucional (documentos da imobiliária)

FAQ, política de visita e tabela de taxas são texto corrido, não registro estruturado, e por isso
têm tratamento próprio em `shared/sdr_shared/conhecimento.py`:

- **Fatiamento por cabeçalho**, não por tamanho fixo: cada `##` já é a unidade de sentido, e o
  cabeçalho acompanha cada pedaço quando a seção precisa ser dividida.
- **Piso de similaridade de 0,35**: abaixo disso a busca devolve lista vazia, e o agente responde
  "não sei, o corretor confirma". Sem piso, uma pergunta que o corpus não cobre traz o vizinho mais
  próximo de coisa nenhuma — e vira afirmação falsa sobre a política da empresa.
- **Reescrita da consulta** com as falas anteriores do cliente: "e se eu sair antes?" não tem
  assunto nenhum para um embedding.
- **Fusão léxica (RRF)** implementada, testada e **desligada** por padrão, atrás de
  `SDR_RAG_LEXICO`: no único ambiente em que deu para medir, o A/B piorou o recall (31,9% → 29,8%),
  porque ali o embedder já é léxico e os dois sinais ficam redundantes. Quem tiver o `bge-m3` no ar
  decide com `SDR_RAG_LEXICO=1 make eval-rag`.

Indexe com `make docs-kb` (ou `make docs-secos`, que lista o que seria indexado sem tocar no banco).

!!! warning "Injeção indireta via RAG"
    A descrição de imóvel é **neutralizada** antes de entrar no prompt, para evitar que texto do
    catálogo funcione como instrução ao modelo. Veja [Segurança](../quality/seguranca.md).

## Observabilidade leve no banco

A observabilidade em vigor grava três tabelas no próprio Postgres — `turnos`, `saude` e `batimentos`
(ADR-0011) —, sem stack externa. Detalhes em [Observabilidade](../quality/observabilidade.md).

## Ingestão

O serviço `services/ingestion` carrega imóveis e documentos e gera os embeddings. Os dois alvos
rodam **dentro do container** do agente, e não no host: ali os padrões de conexão seriam
`localhost:5432` e `localhost:11434`, enquanto o compose publica em 5433 e 11435 — o melhor desfecho
seria falhar, e o pior, numa máquina com Postgres nativo, seria indexar no banco errado em silêncio.

```bash
make seed        # 400 imóveis determinísticos (250 residenciais + 150 comerciais) + embeddings
make docs-kb     # documentos institucionais → tabela `documentos`
make corretores  # a equipe de 20 corretores, casada com os usuários do CRM pelo e-mail
make fotos-acervo  # normaliza data/fotos-acervo/ e redistribui 2–3 fotos por imóvel (no host)
```

Reindexe com `make seed` sempre que editar bairros ou descrições, para não deixar embeddings
desatualizados. O embedding é **um por imóvel**, gerado em sequência: 400 imóveis são 400 chamadas
ao embedder na carga completa. Depois disso a sincronização incremental compara o texto canônico e
só reembeda o que mudou (`sdr_ingestion/sincronia.py`) — uma passada sem mudanças gera zero vetores.

## A massa de demonstração, e de onde ela vem

Quatro arquivos, todos versionados, cada um fonte única do seu assunto:

| Arquivo | O que é | Quem consome |
|---|---|---|
| `data/imoveis/imoveis.json` | o acervo: 400 imóveis, gerado por `scripts/gerar_imoveis.py` (determinístico na seed) | a Mora indexa; o CRM registra como `properties` — é o `code` que liga os dois |
| `data/equipe/corretores.json` | a equipe: 20 corretores fictícios, com região e situação | `scripts/semear_corretores.py` (Mora) e o seed do CRM (`users`), casados pelo **e-mail** |
| `data/imoveis/fotos_pool.json` | as fotos por categoria, escrito por `scripts/indexar_fotos.py` | `gerar_imoveis.py`, que distribui 2–3 por imóvel coerentes com o tipo |
| `data/documentos/*.md` | os documentos institucionais do RAG | `make docs-kb` → tabela `documentos` |

O padrão é o mesmo nos quatro: **um arquivo, dois consumidores**. Duas listas de imóveis ou duas
listas de equipe descreveriam a mesma imobiliária com dados diferentes, e a integração entre Mora e
CRM não encontraria o outro lado — foi exatamente o defeito que o acervo único corrigiu.

As fotos ficam em `data/fotos-acervo/<categoria>/` e são servidas por `GET /acervo/{categoria}/{arquivo}`
(`SDR_FOTOS_ACERVO_DIR`). O prefixo `/acervo/` é separado de `/fotos/` de propósito: `/fotos/%` é o
que marca "foto enviada pelo painel" na precedência painel > CRM > arquivo do `upsert` (ADR-0015).
Com a pasta vazia, o gerador usa URLs de um serviço de imagens de exemplo — a galeria funciona, mas
as fotos não têm relação com imóvel; `data/fotos-acervo/README.md` explica como trocar.
