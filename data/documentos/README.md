# Documentos institucionais (base de conhecimento da Mora)

O que entra aqui vira resposta da Mora sobre **como a imobiliária trabalha** — taxa, documentação
exigida, política de visita, prazo de retorno, condições de financiamento, privacidade. O catálogo de
imóveis segue por outro caminho (`data/imoveis/`, um imóvel = um chunk); estes são texto corrido e
vão com **chunking hierárquico** por cabeçalho (`shared/sdr_shared/conhecimento.py::fatiar`) para a
tabela `documentos` do Postgres com pgvector (ADR-0001 e ADR-0004).

```bash
make docs-secos     # seco: lista o que seria indexado, sem tocar no banco
make docs-kb        # fatia, gera embeddings e grava na tabela `documentos`
```

- **Formatos aceitos: `.md` e `.txt`.** PDF e HTML são recusados de propósito: extrair texto de PDF
  tem armadilha (coluna, tabela, cabeçalho repetido) e um chunk mal cortado vira resposta errada com
  cara de certeza.
- **Um cabeçalho `##` = uma pergunta.** É a unidade de recuperação: a busca devolve a seção, e a
  seção precisa responder sozinha, sem depender do parágrafo anterior.
- **Um assunto por arquivo.** Documento que mistura taxa, visita e financiamento devolve o pedaço
  errado. Subpasta, quando existir, vira o metadado `assunto`.
- **Não renomeie seções existentes sem olhar o eval.** `services/agent/evals/datasets/rag.jsonl`
  aponta para os títulos das seções pelo texto: renomear uma seção quebra os casos que a citam. Criar
  arquivo e seção novos é seguro; renomear exige atualizar o dataset junto.
- **Assunto novo não duplica assunto existente.** Duas seções respondendo "qual a entrada mínima"
  disputam a mesma pergunta, e a recuperação passa a variar por sorte. Quando um documento amplia
  outro, ele diz isso no cabeçalho e manda o resto para lá — como `financiamento-etapas-e-prazos.md`
  faz com o FAQ.

## Estes documentos são fictícios, e é o que os torna aceitáveis

Cada arquivo abre com um aviso de que é exemplo da Vértice Imóveis, que é uma imobiliária fictícia.
Isso não é formalidade: a Mora afirma ao cliente, com toda a confiança, o que estiver escrito aqui.
Um valor de taxa ou um prazo inventado e apresentado como real seria o agente prometendo condição
comercial que não existe — por isso o aviso fica dentro do documento, e não só no repositório.

Numa implantação de verdade estes arquivos são substituídos pelos documentos da imobiliária, e
nenhuma condição comercial deve ser escrita aqui por quem não pode decidi-la.

## O que existe hoje

| Arquivo | Assunto |
|---|---|
| `politica-de-visitas.md` | custo, agendamento, acompanhamento, remarcação, documento |
| `locacao-garantias-e-documentos.md` | garantias, fiador, documentos, pets, prazo de contrato |
| `taxas-e-prazos.md` | administração, cadastro, repasse, reajuste, vistoria, multa, comissão |
| `faq-financiamento.md` | entrada mínima e documentos para a análise de crédito |
| `financiamento-etapas-e-prazos.md` | etapas, prazos, FGTS, portabilidade, avaliação, custos |
| `documentacao-da-venda.md` | documentos, matrícula, ITBI, escritura, prazos, venda com inquilino |
| `locacao-comercial.md` | prazo, carência, luvas, encargos, garantias de empresa, ponto |
| `condominio-obras-e-uso-do-imovel.md` | o que o condomínio inclui, rateio, obras, sublocação |
| `atendimento-horarios-e-corretores.md` | horários, canais, escolha e troca de corretor, alçada da Mora |
| `privacidade-e-dados-do-cliente.md` | dados guardados, quem vê, opt-out, correção e exclusão |
