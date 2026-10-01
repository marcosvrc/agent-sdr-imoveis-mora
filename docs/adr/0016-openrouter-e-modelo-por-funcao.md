# ADR-0016 — OpenRouter como provedor e um modelo por função do agente

**Status:** aceito · **Data:** 2026-09-28 · **Revisa:** [ADR-0009](0009-gateway-de-llm-litellm-openrouter-ou-nada.md)
(a parte do OpenRouter) e [ADR-0010](0010-modelo-por-nivel-e-troca-pelo-painel.md) (os níveis)

## Contexto
Duas perguntas chegaram juntas: dá para usar modelos fora da Anthropic e da OpenAI, e dá para usar o
modelo mais adequado a cada função do agente? As duas esbarravam no desenho de então.

**Três papéis para nove nós.** `roteamento` servia o supervisor (uma palavra, só na mensagem ambígua)
e a extração do cartão (JSON estruturado, em todo turno de qualificação). `conversa` servia a fala da
Mora e a resposta do RAG institucional. Trocar o modelo do supervisor trocava, sem ninguém pedir, o que
preenche o cartão do lead — e as exigências são opostas: o supervisor quer o primeiro token mais rápido
que existir; a extração quer o modelo que menos erra em saída estruturada.

**Modelos fora das duas famílias exigiam uma integração cada.** Gemini, Mistral, DeepSeek, GPT-OSS no
Groq/Cerebras, Qwen: cada um com cliente, preço e formato de ID próprios.

**O ADR-0009 recusou o OpenRouter em produção** principalmente por privacidade, citando que o opt-out
de treinamento valia só para os provedores, não para o OpenRouter. A documentação atual
(2026-09) diz outra coisa: o OpenRouter **não guarda** prompts nem respostas por padrão, e a retenção
zero pode ser exigida por requisição (`provider.zdr`), limitando o roteamento a endpoints que também
não retêm.

Veio junto um problema que não era de escolha, era de funcionamento: os modelos atuais da Anthropic
(Sonnet 5 e 5.5, Opus 4.7+ e 5.x, Fable, Mythos) devolvem **400 para `temperature` fora do padrão em
toda requisição**, e raciocinam por padrão com os tokens de raciocínio contando no `max_tokens`. O
factory mandava `temperature` sempre e teto de 600: nenhum deles funcionava, e o Sonnet 4.5 — o padrão
— tem aposentadoria prevista para "não antes de 2026-09-29".

## Decisão

### 1. Cinco papéis, um por função
`conversa` · `roteamento` · **`extracao`** · **`informacoes`** · `analise`, definidos em um único
módulo (`shared/sdr_shared/papeis.py`) que API, factory, harness, comparação e painel leem.

| Papel | Nós | O que importa | Vazio herda de |
|---|---|---|---|
| `conversa` | qualificador, consultor, agendador, followup, reativador | português com persona | ambiente |
| `roteamento` | supervisor (mensagem ambígua) | primeiro token, preço | ambiente |
| `extracao` | `qualificador._extrair` (e o consultor, que a reusa) | JSON válido, não inventar | `roteamento` |
| `informacoes` | informacoes (RAG) | fidelidade ao trecho, citar fonte | `conversa` |
| `analise` | resumidor | qualidade; latência não importa | `conversa` |

A herança é o que torna a mudança segura: sem mexer em nada, cada nó usa exatamente o modelo que
usava antes. A precedência é por nível — painel do papel → ambiente do papel → painel do pai →
ambiente do pai — resolvida em `ports.factory.modelo_efetivo`, a mesma função que o agente, a tela e o
relatório de avaliação consultam.

Com o agente degradado por orçamento, **todo** papel passa a ser atendido pelo modelo de roteamento —
inclusive a extração, que não pode furar a degradação se alguém a apontar para um modelo caro. A
governança grava a função (`conversa`), não quem atendeu, para não misturar os papéis na comparação.

### 2. OpenRouter como provedor, com retenção zero obrigatória
`provider="openrouter"` deixa de ser só bancada e entra no painel. As condições estão no código, não
na configuração de quem usa:

- **Toda requisição** leva `provider: {"data_collection": "deny", "zdr": true}`. Desligar o ZDR
  (`SDR_OPENROUTER_ZDR=false`) é para a bancada com dataset sintético; o `check_env.py` e a tela avisam.
- **Ordenação por papel** (`provider.sort`): latência para roteamento e extração (saída curta — o
  cliente sente o primeiro token), velocidade de geração para conversa e informações, preço para a
  análise.
- **Dois clientes do mesmo modelo.** O da saída estruturada liga `require_parameters`, para cair só
  em endpoint que respeita o schema — sem isso, um endpoint que ignora `response_format` devolveria
  texto e o qualificador engoliria em silêncio. O da conversa não liga, para um parâmetro opcional não
  excluir endpoints bons.
- **Saída estruturada por ferramenta quando não há schema.** Endpoint que declara `tools` mas não
  `structured_outputs` (o Claude Sonnet 5 com retenção zero só existe no Bedrock, assim; vários
  hosts de DeepSeek e GLM também) recebe a extração como chamada de ferramenta — pedir schema com
  `require_parameters` deixaria o OpenRouter sem endpoint. Para Claude a ferramenta não é forçada:
  com raciocínio ligado a Anthropic recusa ferramenta forçada.
- **Parâmetros pelo catálogo.** O factory consulta `GET /models` (público, cache de 6 h) para saber se
  o modelo aceita `temperature` e `reasoning`; sem catálogo, decide pelo nome.
- **Custo da resposta.** O OpenRouter informa `usage.cost` em toda resposta; o `RegistradorUso` usa
  esse valor em vez da tabela. O teto mensal continua valendo para modelos que a tabela não conhece.
- **Preço antes de salvar.** A trava do ADR-0010 continua: modelo sem preço é recusado. Para o
  OpenRouter, a trava primeiro busca o preço publicado; `POST /config/modelos/openrouter/sincronizar`
  traz o de uma lista de modelos, que passam a aparecer no combo.
- **ID e fallback.** `anthropic/claude-haiku-4.5` ↔ `claude-haiku-4-5` e `openai/gpt-5.6-luna` ↔
  `gpt-5.6-luna` são traduzidos nos dois sentidos, e o preço da tabela vale para os dois caminhos
  (o OpenRouter repassa o do fornecedor). De outro fornecedor para o reserva direto, vale o
  equivalente do papel.
- **Cache de prompt.** Modelos `anthropic/…` e `qwen/…` recebem a mesma marcação `cache_control` do
  caminho direto (fim do system e fim do histórico); os demais fornecedores fazem cache sozinhos. O
  cache em memória não conta como retenção, então convive com o ZDR.
- **Embeddings pelo OpenRouter** (`SDR_EMBEDDINGS_PROVIDER=openrouter`): o mesmo
  `text-embedding-3-small`, com a chave do OpenRouter — os vetores são os mesmos do caminho direto,
  então o índice não é refeito e o piso do RAG (que passou a ser por modelo) continua valendo. Vai
  `data_collection: deny`, mas **não** `zdr`: nenhum modelo de embedding tinha endpoint ZDR, e a
  busca que falha não quebra nada visível — o RAG diria "vou confirmar" para tudo. É a mesma postura
  de chamar a OpenAI direto. Com isso, usar só o OpenRouter dispensa todas as outras chaves.
- **Reserva direto.** Com o OpenRouter como primário, o reserva deve ser `anthropic` ou `openai`: se
  o OpenRouter cair, tudo o que passa por ele cai junto. `check_env.py` avisa.

### 3. Parâmetros por família de modelo, em qualquer provedor
- `recusa_temperatura(model)`: não manda `temperature` para Claude Sonnet 5+, Opus 4.7+, Fable,
  Mythos, GPT-5 (fora `-chat`) e GPT-6.
- `raciocina_por_padrao(model)`: multiplica o teto por 4 (`FOLGA_RACIOCINIO`) e define o esforço do
  papel — `none` em roteamento e extração, `low` na conversa, `medium` na análise. Na Anthropic o
  mínimo aceito é `low`; na OpenAI direta usa-se `low` na série inteira (o GPT-5 original não aceita
  `none`). Pelo OpenRouter, modelo que não deixa desligar o raciocínio (`reasoning.mandatory` no
  catálogo; sem catálogo, `openai/gpt-oss-*`) recebe o menor esforço que aceita em vez de `none` —
  mandar `none` dava 400 em toda chamada.
- Claude que raciocina recebe `SaidaEstruturadaNativa`: a extração usa `method="json_schema"` (saída
  estruturada nativa), porque com raciocínio ligado a Anthropic não força ferramenta e o Sonnet 5.5
  não deixa desligar o raciocínio.

## Consequências
- (+) Qualquer modelo do catálogo do OpenRouter pode atender qualquer função, escolhido pelo painel,
  sem redeploy e sem integração nova.
- (+) Os modelos atuais da Anthropic passam a funcionar pela API direta — o que destrava a migração
  do Sonnet 4.5.
- (+) A governança fica correta também para modelo fora da tabela (custo da resposta).
- (−) **Mais um operador de dados** para a política de privacidade — o mesmo pendente do ADR-0009,
  agora com um nome a mais quando o OpenRouter for de fato usado com cliente real.
- (−) **Mais um salto de rede** em toda chamada que passa pelo OpenRouter. A tela de comparação mede a
  latência por papel e modelo; decidir pelo número medido, não por suposição.
- (−) O catálogo do OpenRouter é uma dependência de rede na construção do modelo (uma vez por processo
  e modelo, 5 s de timeout, falha cai na decisão pelo nome).
- (−) Histórico: antes deste ADR, as chamadas de extração eram gravadas como `roteamento`. A
  comparação do papel `extracao` começa sem uso e usa o mix de referência até acumular chamadas.

## O que fica de fora
- **Qual provedor atendeu atrás do OpenRouter.** Seria a trilha de auditoria ideal para LGPD, mas a
  resposta documentada não traz esse campo; gravar um dado que talvez nunca venha seria pior.
- **Escolha dos modelos.** Este ADR cria a possibilidade; qual modelo atende cada papel sai da matriz
  de avaliação (`make eval-matriz`, com `-n 3`), que roda os candidatos de `evals/matriz.json`
  nas suítes de cada papel.
- **Sabiá (Maritaca):** não está no OpenRouter. Entra por um provedor direto compatível com a API da
  OpenAI, se a matriz justificar.
