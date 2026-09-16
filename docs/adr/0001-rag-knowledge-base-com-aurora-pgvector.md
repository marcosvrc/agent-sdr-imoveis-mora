# ADR-0001 — RAG: Bedrock Knowledge Base com Aurora pgvector como vector store

**Status:** aceito · **Data:** 2026-09-08

## Contexto
A base de imóveis é simulada (centenas de registros). Imóvel é registro estruturado, não documento:
precisa de busca híbrida (filtros por preço/quartos/região + similaridade semântica).
Queremos um bloco "RAG gerenciado" visível na arquitetura sem perder controle.

## Decisão
- Bedrock Knowledge Base sobre S3, estratégia **no chunking** (um arquivo por imóvel) + `*.metadata.json`.
- Vector store: **Aurora Serverless v2 PostgreSQL + pgvector** (não OpenSearch Serverless).
- Embeddings: Titan Text Embeddings v2 (1024 dims). Região: us-east-1.
- Documentos institucionais (FAQ, políticas): mesma KB, chunking hierárquico (pai 1500 / filho 300 tokens).

## Consequências
- (+) Zero código de ingestão; filtros de metadados; a mesma tabela serve dashboard e agente.
- (−) Sync de ingestão leva minutos → base sincronizada antes da demo; imóveis recém-cadastrados
  são consultados pela tabela relacional diretamente.
- **Fallback (Caminho B):** `tools/buscar_imoveis.py` abstrai `retrieve()`; trocar por query pgvector
  direta não muda nenhum outro componente.
