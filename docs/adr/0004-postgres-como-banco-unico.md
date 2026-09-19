# ADR-0004 — Um Postgres para tudo, em vez de um banco por finalidade

**Status:** aceito · **Data:** 2026-09-08 · **Revisto em 2026-09-12**

## Contexto
O sistema tem quatro necessidades de persistência que costumam justificar quatro bancos: registro
transacional (leads, visitas, imóveis), busca vetorial (o RAG do [ADR-0001](0001-rag-com-postgres-pgvector.md)),
agregação para o painel (funil, custo por modelo, tendência) e estado do grafo (o checkpointer do
LangGraph).

## Decisão
Um **PostgreSQL com pgvector** atende as quatro.

## Motivos
- O painel exige funil, filtros e agregação — isso é SQL, e um banco de documentos cobraria caro em
  código por cada tela.
- `pgvector` põe o vetor na mesma linha do registro. O filtro por preço e o vizinho mais próximo
  acontecem na mesma consulta, e não existe índice paralelo que possa divergir do catálogo.
- O checkpointer do LangGraph tem suporte nativo a Postgres: o estado da conversa fica junto do
  lead, e não em mais um lugar.
- Um banco só é um schema só, um backup só e um lugar só para olhar quando algo não bate.

## Consequências
- (+) A tabela que serve o agente é a mesma que serve o painel: o que o corretor vê é o que o
  agente usou.
- (−) O Postgres vira o gargalo único quando houver volume, e a busca vetorial concorre com a carga
  transacional pelos mesmos recursos. Na escala deste projeto isso é teórico; em produção seria a
  primeira coisa a medir.

Houve aqui uma comparação com um banco de documentos gerenciado, no tempo em que a entrega tinha
alvo de nuvem. O alvo mudou (ver [ADR-0002](0002-runtime-do-agente-em-container.md)), mas a decisão
não: os motivos acima nunca dependeram de onde o banco roda.
