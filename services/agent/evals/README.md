# Harness de avaliação do agente

`tests/` responde "o sistema está montado certo?" (LLM falso, determinístico, roda no CI).
Isto responde **"o modelo está se comportando bem?"** — e por isso chama a API de verdade.

## Rodar

```bash
make eval                    # tudo, 1 repetição
make eval-fake               # valida o harness sem gastar token (LLM falso)
cd services/agent && PYTHONPATH=../../shared:src python -m evals --suite extracao -n 3
```

Precisa do Postgres de teste no ar (`make test-db`) e das credenciais de LLM no `.env` — as mesmas
que o agente usa. O guarda `exigir_banco_de_teste` impede rodar contra o banco de desenvolvimento.

## As três suítes

| suíte | pergunta | métrica |
|---|---|---|
| `extracao` | o modelo entende o que o cliente disse? | acerto por campo do cartão + **campos inventados** |
| `roteamento` | o supervisor manda para o nó certo? | acurácia + matriz de confusão + quantas passaram pelo modelo |
| `adversarial` | um ataque passa? | **taxa de escape**, separando o que a regra barrou do que só o modelo segurou |

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

Cada execução salva um JSON em `resultados/`, com data, modelo e custo. É o que permite comparar
antes/depois de mexer num prompt em vez de confiar na impressão de que "melhorou".

## Adicionar caso

Uma linha JSON no dataset da suíte. Em `extracao`, `esperado` é o que precisa sair e `nao_esperado`
é o que precisa continuar vazio — sempre preencha o segundo, é ele que pega alucinação.

## Limiares

Por padrão o harness informa e não reprova: número de LLM oscila, e transformar oscilação em build
vermelho ensina o time a ignorar o build. Para usar como portão (numa release, não em cada commit):

```bash
python -m evals --limite-escape 0 --limite-extracao 85
```
