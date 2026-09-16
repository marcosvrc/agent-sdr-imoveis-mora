# Documentos institucionais da Knowledge Base

O que entra aqui vira resposta da Mora sobre **como a imobiliária trabalha** — taxa, documentação
exigida, política de visita, prazo de retorno, condições de financiamento. O catálogo de imóveis
segue por outro caminho (`data/imoveis/`, um arquivo = um chunk); estes são texto corrido e vão com
chunking hierárquico, configurado na data source `documentos` (`infra/stacks/ai_stack.py`).

```bash
python -m sdr_ingestion.ingest_documentos data/documentos                      # seco: lista o que subiria
python -m sdr_ingestion.ingest_documentos data/documentos meu-bucket KB123 DS9 # envia e sincroniza
```

- Formatos aceitos: `.md`, `.txt`, `.html`, `.pdf`. Máximo de 45 MB por arquivo.
- **Subpasta = assunto**, e o assunto vira metadado de filtro na Knowledge Base. Prefira
  `visitas/politica-de-visita.md` a `politica_visitas_v2_FINAL.md`.
- Um assunto por arquivo. Documento que mistura taxa, visita e financiamento devolve o pedaço errado
  na recuperação.

> **A pasta começa vazia de propósito.** Estes documentos descrevem regras reais da imobiliária —
> valor de taxa, prazo, exigência de documento — e nenhum deles pode ser inventado para preencher a
> demo: a Mora passaria a afirmar ao cliente, com toda a confiança, uma condição comercial que não
> existe. Enquanto a pasta estiver vazia, a Mora simplesmente não fala desses assuntos, que é o
> comportamento correto.

O perfil local não tem Knowledge Base: rodar sem bucket lista o que subiria e sai sem erro.
