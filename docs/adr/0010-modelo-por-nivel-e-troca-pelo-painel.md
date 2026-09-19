# ADR-0010 — Modelo por nível, editável no painel

**Status:** aceito · **Data:** 2026-09-12

## Contexto
Havia dois níveis de modelo — `conversa` (Sonnet) e `roteamento` (Haiku) — fixados em variável de
ambiente. Trocar exigia redeploy, e não havia como usar modelos diferentes para tarefas com exigências
opostas. Ao levantar o catálogo atual (setembro/2026) para decidir o que usar, apareceu um problema
mais sério que a rigidez:

```
custo_usd('claude-sonnet-4-5', …) → 4.5     ← está na tabela
custo_usd('claude-sonnet-5',   …) → 0.0     ← não está
```

`custo_usd` devolve zero para modelo sem preço cadastrado. Zero soma zero em `gasto_do_mes()`, o teto
mensal em dólar nunca é atingido, e o agente nunca degrada nem bloqueia. **Trocar de modelo desligava
silenciosamente metade do guardrail de orçamento** — e o painel de Governança seguia mostrando um
número saudável, justamente porque estava errado. (O teto de tokens/dia continua valendo: tokens são
contados independentemente de preço.)

## Decisão
**Três níveis, escolhidos no painel, com a tabela de preços como pré-requisito de gravação.**

`conversa` · `roteamento` · `analise`. O terceiro é novo: o briefing do corretor roda fora do turno
(tópico `resumir`), então latência não importa ali e ele pode usar modelo diferente do que fala com o
cliente. Vazio herda `conversa`, para não obrigar a preencher três campos para mudar um.

A chave `modelos` da tabela `configuracoes` manda; o `.env` é o piso. Campo vazio no painel significa
"usa o do ambiente", e `DELETE /config/modelos` restaura tudo — importante porque esse é o caminho de
recuperação de um modelo mal configurado, sem precisar de acesso ao banco.

Quatro travas, que são o real conteúdo desta decisão (a tela em si é trivial):

1. **Recusar modelo sem preço.** `PUT /config/modelos` retorna 422 se o modelo não tiver linha em
   `precos`, com o caminho para resolver. Ollama é exceção: roda local, custo zero é a verdade.
2. **Testar antes de salvar.** `POST /config/modelos/testar` faz uma chamada real e curta e devolve
   se respondeu, em quanto tempo e se há preço. Lista fixa de modelos envelhece; campo livre derruba
   o agente no turno seguinte. O teste responde o que a lista não responde: esse ID existe *neste
   provedor*?
3. **Invalidar o cache.** `agent/llm.py` cacheia a instância do modelo. A escolha do painel entrou na
   chave do cache, e `PUT`/`DELETE` chamam `invalidar_cache_modelos()` — sem isso um worker de vida
   longa seguiria com o modelo antigo para sempre. O `DELETE` só ganhou a invalidação porque um teste
   pegou a falta dela.
4. **Mostrar o efetivo, não a intenção.** `GET /config` devolve, por nível, o que o agente vai usar no
   próximo turno e se veio do painel ou do ambiente.

Junto, um conserto que a mudança exigiu: a tabela de preços ganhou o catálogo atual (Sonnet 5,
Opus 5). A normalização de ID de modelo também foi revista, e hoje `normalizar_modelo` só tira os
prefixos de provedor hospedado que um `.env` antigo possa carregar — nenhum provedor do projeto
adiciona prefixo.

## Modelo recomendado por nível
Preços por milhão de tokens, conforme `PRECOS_PADRAO` em `shared/sdr_shared/governanca/precos.py`
(consultados em setembro/2026 — preço de modelo muda mais rápido que código; confira antes de confiar
no número do painel). Os provedores aceitos são `anthropic`, `openai` e `ollama`.

| Nível | Recomendado | Racional |
|---|---|---|
| `conversa` | **Sonnet 5** ($2/$10) | Substitui o Sonnet 4.5 ($3/$15) que estava configurado: mais novo e 33% mais barato. O equivalente de conversa na OpenAI, `gpt-5.6-terra` ($2/$12), custa o mesmo na entrada e mais na saída — não há argumento de preço para trocar de família aqui. |
| `roteamento` | Haiku 4.5 ($1/$5) | Roda em toda mensagem: é onde o preço pesa. O equivalente barato da OpenAI, `gpt-5.6-luna` ($0,20/$1,20), é 5x mais barato na entrada e ~4x na saída; o Ollama é custo zero, mas disputa CPU e RAM com os embeddings na mesma máquina. Decidir medindo, com o harness de `services/agent/evals/`. |
| `analise` | Sonnet 5 | Roda fora do turno e é lido por um humano que decide como abordar o lead. Candidato natural a Batch (50% de desconto) e o único lugar onde pagar mais por um modelo melhor pode se justificar. |

Sobre Gemini e OpenAI: os dois têm modo de schema estrito nativo, tecnicamente melhor que o
tool-calling do Anthropic para a extração do cartão. O que pesa contra não é qualidade nem preço, é que
**toda chamada de LLM aqui vê o texto cru do cliente** — inclusive extração e roteamento. Não existe
nível "menos sensível" onde caiba um terceiro sem envolver PII, então cada provedor adicionado é um
operador de dados a mais (LGPD), como no OpenRouter da ADR-0009. A OpenAI entrou mesmo assim, como
reserva, pela razão registrada na atualização da ADR-0009 — e com a consequência de subprocessador
que está anotada lá. O Gemini continua fora: não há motivo que justifique um terceiro operador.

## Consequências
- (+) Trocar modelo virou operação de painel, auditada (o `AuditoriaMiddleware` já registra `PUT /config`),
  reversível e válida no próximo turno.
- (+) O guardrail de orçamento não pode mais ser desligado por acidente ao trocar de modelo.
- (+) Adicionar provedor é uma função (`_construir`), então avaliar outro modelo é barato.
- (−) Mais uma superfície de configuração: um modelo caro escolhido por engano custa dinheiro de
  verdade. Mitigado pelo teste antes de salvar e pelo teto de orçamento que volta a funcionar.
- (−) A tabela de preços é uma cópia da documentação dos fornecedores num dado dia, não uma consulta
  ao vivo. Conferir e ajustar pelo painel (configuração `precos`) antes de confiar no custo exibido.

## O que fica de fora, deliberadamente
**Cache de prompt** é o maior ganho disponível e não entrou aqui: as duas famílias pagas da tabela
(Anthropic e OpenAI) cobram 10% da entrada em leitura de cache, e o prefixo repetido a cada turno (blindagem + persona + prompt do nó) é o custo
dominante de entrada numa conversa de várias mensagens. A contabilidade já está pronta —
`RegistradorUso._tokens()` extrai `cache_escrita`/`cache_leitura` e `custo_usd` os precifica — só falta
ligar. Provavelmente rende mais que qualquer troca de modelo desta ADR. Fica como próximo passo, junto
com **Batch para o resumidor** (50%, fora do caminho do turno).
