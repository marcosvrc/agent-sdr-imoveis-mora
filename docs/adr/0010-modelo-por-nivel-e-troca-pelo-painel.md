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
   provedor* e *nesta região*?
3. **Invalidar o cache.** `agent/llm.py` cacheia a instância do modelo. A escolha do painel entrou na
   chave do cache, e `PUT`/`DELETE` chamam `invalidar_cache_modelos()` — sem isso um worker de vida
   longa seguiria com o modelo antigo para sempre. O `DELETE` só ganhou a invalidação porque um teste
   pegou a falta dela.
4. **Mostrar o efetivo, não a intenção.** `GET /config` devolve, por nível, o que o agente vai usar no
   próximo turno e se veio do painel ou do ambiente.

Junto, dois consertos que a mudança exigiu: `normalizar_modelo` prefixava `anthropic.` em qualquer
modelo no Bedrock, o que geraria `anthropic.amazon.nova-lite-v1:0` — agora só prefixa modelo Claude; e
a tabela de preços ganhou o catálogo atual (Sonnet 5, Opus 5, família Nova).

## Modelo recomendado por nível
Preços de setembro/2026, por milhão de tokens (Anthropic direto; Bedrock cobra por região).

| Nível | Recomendado | Racional |
|---|---|---|
| `conversa` | **Sonnet 5** ($2/$10) | Substitui o Sonnet 4.5 ($3/$15) que estava configurado: mais novo e 33% mais barato. Nesse patamar o Claude já é competitivo com Gemini 3.1 Pro ($2/$12) e mais barato que GPT-5.4 ($2,50/$15) — não há argumento de preço para trocar de família aqui. |
| `roteamento` | Haiku 4.5 ($1/$5), avaliar **Nova Lite** (~$0,06/$0,24) | Roda em toda mensagem: é onde o preço pesa. Gemini Flash-Lite e GPT nano são 10-20x mais baratos que o Haiku, mas ficam fora da AWS; o Nova entrega ganho parecido **dentro do Bedrock**, sem cloud nova, sem operador de dados novo e sem perder o Guardrail. Decidir medindo, com o harness de `evals/`. |
| `analise` | Sonnet 5 | Roda fora do turno e é lido por um humano que decide como abordar o lead. Candidato natural a Batch (50% de desconto) e o único lugar onde pagar mais por um modelo melhor pode se justificar. |

Sobre Gemini e OpenAI: os dois têm modo de schema estrito nativo, tecnicamente melhor que o
tool-calling do Anthropic para a extração do cartão. O que os derruba não é qualidade nem preço, é que
**toda chamada de LLM aqui vê o texto cru do cliente** — inclusive extração e roteamento. Não existe
nível "menos sensível" onde caiba um terceiro sem envolver PII, então adotá-los é adicionar um operador
de dados (LGPD), como no OpenRouter da ADR-0009. A diferença é que Vertex AI e Azure OpenAI são
relacionamentos gerenciáveis, com DPA e região — se um dia for necessário, é por ali, não por chave
avulsa.

## Consequências
- (+) Trocar modelo virou operação de painel, auditada (o `AuditoriaMiddleware` já registra `PUT /config`),
  reversível e válida no próximo turno.
- (+) O guardrail de orçamento não pode mais ser desligado por acidente ao trocar de modelo.
- (+) Adicionar provedor é uma função (`_construir`), então avaliar Nova ou qualquer outro é barato.
- (−) Mais uma superfície de configuração: um modelo caro escolhido por engano custa dinheiro de
  verdade. Mitigado pelo teste antes de salvar e pelo teto de orçamento que volta a funcionar.
- (−) Os preços do Nova na tabela são aproximados e o Bedrock cobra por região — conferir e ajustar
  pelo painel antes de confiar no custo exibido.

## O que fica de fora, deliberadamente
**Cache de prompt** é o maior ganho disponível e não entrou aqui: as três famílias cobram 10% em
leitura de cache, e o prefixo repetido a cada turno (blindagem + persona + prompt do nó) é o custo
dominante de entrada numa conversa de várias mensagens. A contabilidade já está pronta —
`RegistradorUso._tokens()` extrai `cache_escrita`/`cache_leitura` e `custo_usd` os precifica — só falta
ligar. Provavelmente rende mais que qualquer troca de modelo desta ADR. Fica como próximo passo, junto
com **Batch para o resumidor** (50%, fora do caminho do turno).
