# ADR-0001 — RAG sobre Postgres + pgvector, com fusão de ranking

**Status:** aceito · **Data:** 2026-09-08 · **Revisto em 2026-09-12** (ver "Revisão")

## Contexto
São duas recuperações diferentes, e confundi-las é o erro comum:

- **Imóvel** é registro estruturado, não documento. A pergunta "dois quartos em Pinheiros até 3.500"
  é filtro (preço, quartos, região) com um tempero de similaridade semântica por cima.
- **Documento institucional** (FAQ, política de visita, tabela de taxas) é texto corrido, e a
  pergunta chega na língua do cliente: "vocês cobram pra mostrar o imóvel?".

## Decisão
Um Postgres com **pgvector** serve os dois, e é o mesmo banco que o painel consulta.

- **Imóveis:** um chunk por imóvel (a ficha inteira é a unidade que faz sentido recuperar). Busca
  híbrida: filtro SQL (`operacao`, `regiao`, `quartos`, `preco`) + distância de cosseno no vetor.
- **Documentos:** fatiados por seção em `sdr_shared/conhecimento.py`, com `assunto` derivado da
  subpasta — é assim que se recupera a política de visita sem trazer a tabela de taxas junto.
- **Embeddings:** `bge-m3` pelo Ollama, 1024 dimensões, que é o que o schema espera. Roda na
  máquina de quem avalia, sem chave e sem custo por token.
- **Piso de similaridade** no caminho institucional (0.35). Busca vetorial sempre devolve o vizinho
  mais próximo, mesmo quando ele está longe: sem piso, "vocês fazem seguro de automóvel?" traria o
  trecho de taxas e o agente afirmaria uma política inventada. Lista vazia é resultado, não falha.

## Consequências
- (+) Um banco só: o mesmo `SELECT` que alimenta o funil do painel alimenta a busca do agente, e
  não existe índice que possa divergir do catálogo.
- (+) Roda inteiro na máquina de quem avalia — nenhum serviço a provisionar antes da primeira
  conversa.
- (−) Toda a qualidade da recuperação é responsabilidade do código, não de um serviço gerenciado.
  É por isso que existe `services/agent/evals/` com dataset próprio: sem medida, "melhorar o RAG"
  vira palpite.

## Revisão — o que a medição mudou
Duas coisas entraram por medição, e uma saiu:

- **Reescrita de consulta** entrou. "E se eu sair antes?" não tem assunto nenhum para um embedding;
  sem reescrever com o turno anterior, esses casos falham inteiros.
- **Fusão léxica (RRF sobre pgvector + `tsvector`)** está implementada e **desligada por padrão**,
  atrás de `SDR_RAG_LEXICO`. O A/B no dataset do repositório deu recall 31,9% → 29,8%: piorou.
  Fica no código porque a medição é do corpus de hoje, e o botão permite refazê-la; não fica ligada
  porque número pior é número pior.
- **Piso léxico** foi criado e removido no mesmo dia: com `OR` no `to_tsquery`, 7 das 10 negativas
  pontuam acima de zero, e nenhum corte separava as duas populações.

Houve aqui uma decisão anterior por um serviço gerenciado de Knowledge Base, com a mesma tabela
`pgvector` de vector store. Saiu junto com o resto da infraestrutura hospedada (ver
[ADR-0002](0002-runtime-do-agente-em-container.md)). O que ela trazia — ingestão sem código, filtro
por metadado — era exatamente o que este ADR agora escreve à mão, e a troca custou código de
ingestão e comprou a possibilidade de medir.
