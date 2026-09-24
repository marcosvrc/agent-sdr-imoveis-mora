# Harness de avaliação do agente

`tests/` responde "o sistema está montado certo?" (LLM falso, determinístico, roda no CI).
Isto responde **"o modelo está se comportando bem?"** — e por isso chama a API de verdade.

## Rodar

```bash
make eval                    # tudo, 1 repetição, modelo real
make eval-rag                # só o RAG institucional, com o embedder real (exige `make ollama-pull`)
make eval-recomendacao       # só a recomendação de imóveis, com o embedder real
make eval-fake               # valida o HARNESS com dublês; roda no CI
cd services/agent && PYTHONPATH=../../shared:src python -m evals --suite extracao -n 3
```

Precisa do Postgres de teste no ar (`make test-db`) e das credenciais de LLM no `.env` — as mesmas
que o agente usa. O guarda `exigir_banco_de_teste` impede rodar contra o banco de desenvolvimento.

`ModuleNotFoundError: No module named 'psycopg'` significa que o python da máquina não tem as
dependências. Ou rode `make setup`, ou rode o harness dentro do container do agente, que já as tem:

```bash
make eval-recomendacao EVAL_EM=docker
```

`EVAL_EM=docker` vale para `eval`, `eval-fake`, `eval-rag` e `eval-recomendacao`. O `eval-embeddings`
continua só no host: ele troca o provedor de embeddings por variável de ambiente entre as passadas.

A suíte `recomendacao` **reprova quando não há embedder no ar**. Sem ele a busca cai nos filtros SQL
ordenados por preço e continua respondendo — plausivelmente, e é por isso que precisa reprovar: um
recall medido sobre ordenação por preço não mede recuperação nenhuma. Com Ollama, exige
`make ollama-pull` antes.

## As suítes

| suíte | pergunta | métrica |
|---|---|---|
| `extracao` | o modelo entende o que o cliente disse? | acerto por campo do cartão + **campos inventados** |
| `coerencia` | o cartão sobrevive a uma CONVERSA? | estado final depois de N turnos: correção de bairro, retirada de critério, studio com zero quarto |
| `roteamento` | o supervisor manda para o nó certo? | acurácia + matriz de confusão + quantas passaram pelo modelo |
| `adversarial` | um ataque passa? | **taxa de escape**, separando o que a regra barrou do que só o modelo segurou |
| `rag` | a busca institucional acha o trecho certo — e cala a boca quando não sabe? | recall@3, acerto no topo e **abstenção** |
| `recomendacao` | o que a busca devolve respeita o que o cliente pediu? | nível da cascata, teto de preço com a folga de 15 %, segmento e bairro |

`coerencia` existe porque `extracao` mede um turno isolado e o que quebra na conversa é o acúmulo:
o cliente corrige o bairro e o antigo continua no cartão, retira o teto e o teto fica. Nada disso
aparece medindo mensagem por mensagem.

`recomendacao` não tem gabarito de ids, de propósito: id fixo engessa o acervo e o eval passa a
medir a semente em vez da busca. O gabarito é o próprio pedido do cliente. O runner **indexa
`data/imoveis/imoveis.json` com o embedder em uso** antes de rodar, pela mesma razão que o RAG
indexa o corpus: o índice é parte do que está sendo medido.

Nenhuma usa juiz-LLM. Onde a resposta é ambígua, o dataset declara as formas aceitáveis
(`{"qualquer": [...]}`) — juiz tem erro próprio, e num harness pequeno esse erro vira o número.

## Ler o resultado

Três números carregam o resto:

- **campos inventados** (extração) — o modelo preencher orçamento que o cliente não deu é pior que
  deixar vazio: o vazio faz o agente perguntar, o inventado faz ele buscar a casa errada com convicção.
- **taxa de escape** (adversarial) — e o par ao lado dela: quantos ataques *só* não vazaram porque o
  modelo segurou. Esse é o risco residual do `escopo.py`, que é regex em português e termina em
  "na dúvida, atende" (ADR-0008). Se esse número for alto, a regra está carregando menos do que parece.
- **instáveis** — casos que deram resultado diferente entre repetições. Com `-n 1` sempre é zero, o
  que é justamente a armadilha: rode `-n 3` antes de acreditar em qualquer número.
- **abstenção** (rag) — a taxa nas perguntas que o corpus NÃO cobre. Recall alto com abstenção baixa
  é um agente que responde tudo, inclusive o que não sabe; para política de empresa isso é pior que
  um recall médio. As negativas *adjacentes* saem à parte de propósito: ali abster é conservador e
  responder pode ser extrapolar, e a escolha entre os dois é de produto — diluída numa média, ela
  vira uma decisão que ninguém tomou.
- **score: acertos min / maior engano** (rag) — é o que permite calibrar o piso de similaridade com
  evidência em vez de no olho. Quando o maior score de engano fica ACIMA do menor score de acerto, o
  relatório avisa: nenhum limiar separa os dois, e mexer no piso só troca um erro por outro. O que
  falta nesse caso é recuperação melhor, não ajuste.

Cada execução salva um JSON em `resultados/`, com data, modelo e custo. É o que permite comparar
antes/depois de mexer num prompt em vez de confiar na impressão de que "melhorou".

## Adicionar caso

Uma linha JSON no dataset da suíte. Em `extracao`, `esperado` é o que precisa sair e `nao_esperado`
é o que precisa continuar vazio — sempre preencha o segundo, é ele que pega alucinação.

Em `rag`, a regra é **não repetir o cabeçalho do documento na pergunta**. Um caso que pergunta
"Qual a taxa de administração?" para recuperar a seção "Qual a taxa de administração?" mede
casamento de string com passos extras, e passaria com qualquer embedder — inclusive um ruim. Escreva
como o cliente escreveria: "quanto vocês ficam do aluguel por mês?".

## O que `--fake` prova, e o que não prova

O modo de dublês usa um LLM falso e um embedder de **trigramas de caractere**. Ele prova que o
encanamento funciona: os datasets carregam, a indexação roda, o SQL vetorial responde, as métricas
calculam, a abstenção acontece e nenhum nó escapou do dublê para ir chamar o modelo de verdade.

Ele **não** prova qualidade nenhuma. O recall que ele imprime é baixo por construção — o dataset foi
escrito sem repetir o vocabulário dos documentos, então um embedder não-semântico erra quase tudo. O
trigrama existe porque um número que é sempre zero não detecta regressão; este é baixo mas sensível.

Qualidade só sai de `make eval` e `make eval-rag`, com modelo real, na sua máquina.

## A decisão pendente: fusão léxica

O repositório sabe fundir busca vetorial com busca full-text do Postgres (RRF). **Está desligada por
padrão**, porque não há evidência de que ajude — e há uma medição dizendo que atrapalha.

No harness, o embedder é de trigramas, ou seja, já é um método léxico. Ali os dois sinais são
redundantes e o segundo, mais ruidoso, empurra o trecho certo para fora do top-3:

| | recall@3 | paráfrase | literal | abstenção |
|---|---|---|---|---|
| vetorial | 31,9% | 20,5% | 87,5% | 85,7% |
| + léxico | 29,8% | 17,9% | 87,5% | 85,7% |

Com um embedder semântico de verdade a expectativa é a oposta: denso erra termo raro e exato, que é
onde o léxico acerta. Mas expectativa não é medição. **Decida em dois comandos:**

```bash
make eval-rag                      # sem fusão
SDR_RAG_LEXICO=1 make eval-rag     # com fusão
```

Compare `recall@3`, e principalmente `paráfrase` contra `literal` — se a fusão ajudar, o ganho
aparece no literal sem custar no parafraseado. Olhe também a abstenção: ela não deve cair. Se
ajudar, troque `POR_PADRAO_COM_LEXICO` para `True` em `tools/conhecimento.py`; se não, apague o
caminho em vez de deixá-lo desligado para sempre.

Uma nota sobre o piso: houve uma versão em que casamento léxico forte deixava um trecho passar do
piso de similaridade. Ela foi removida. Com os termos ligados por OU — que é o que faz o léxico
funcionar —, 7 das 10 negativas do conjunto pontuam acima de zero, porque quase toda pergunta em
português compartilha alguma palavra com algum trecho. O léxico serve para ORDENAR; quem decide
entre responder e calar continua sendo o cosseno.

## Limiares

Por padrão o harness informa e não reprova: número de LLM oscila, e transformar oscilação em build
vermelho ensina o time a ignorar o build. Para usar como portão (numa release, não em cada commit):

```bash
python -m evals --limite-escape 0 --limite-extracao 85
```
