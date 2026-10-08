---
title: Modelos de linguagem
description: Quais modelos o Mora usa em cada papel, como provedor e ID são resolvidos, o que custa, como o painel compara e como trocar sem redeploy.
---

# Modelos utilizados: decisões e comparativos

Este documento descreve o que o código faz hoje com modelos de linguagem: os papéis, os provedores,
a tabela de preços, o registro de uso, a comparação que o painel mostra e os mecanismos de
timeout e reserva. Tudo foi conferido no código; onde há divergência entre uma recomendação de
ADR e o padrão configurado, a divergência está apontada. Não há aqui benchmark de qualidade —
o repositório não versiona resultado de avaliação com modelo real (ver
[Harness de avaliação](#harness-de-avaliacao)).

## Papéis de modelo

O agente não escolhe "um modelo": escolhe **cinco papéis**, um por função, cada um com modelo e
provedor próprios (ADR-0010, ADR-0016). Os papéis, a herança, a temperatura, o teto de saída, o
esforço de raciocínio e a ordenação no OpenRouter estão num módulo só:
`shared/sdr_shared/papeis.py`. A resolução é feita em
`shared/sdr_shared/ports/factory.py::get_chat_model`, e o agente a consome pelos acessores de
`services/agent/src/agent/llm.py` (lista em `llm.ACESSORES`).

| Papel | Acessor | Onde é usado | Temperatura | Teto | Esforço | Vazio herda de |
|---|---|---|---|---|---|---|
| `conversa` | `llm_conversa()` | `qualificador` (resposta), `consultor`, `agendador`, `followup`, `reativador` | `0.6` | 600 | `low` | `SDR_MODEL_CONVERSA` |
| `roteamento` | `llm_roteamento()` | `supervisor`, só quando as regras não decidem | `0.0` | 600 | `none` | `SDR_MODEL_ROTEAMENTO` |
| `extracao` | `llm_extracao()` | `qualificador._extrair` (`with_structured_output`), reusada pelo `consultor` | `0.0` | 600 | `none` | `roteamento` |
| `informacoes` | `llm_informacoes()` | nó `informacoes` (RAG institucional) | `0.6` | 600 | `low` | `conversa` |
| `analise` | `llm_analise()` | `resumidor` (briefing e análise do lead, fora do turno) | `0.6` | 1500 | `medium` | `conversa` |

Detalhes verificados em `factory.py`, `papeis.py` e `llm.py`:

- `modelo_efetivo(papel)` sobe a cadeia de herança consultando, em cada nível, o painel
  (`escolha_de_modelo(nivel, herdar=False)`, chave `modelos` de `configuracoes`) e depois o
  ambiente (`SDR_MODEL_<PAPEL>`). A mesma função serve o agente, `GET /config` e o relatório de
  avaliação — a tela não tem regra de herança própria. A resposta inclui `de`, o papel de onde o
  modelo veio.
- O teto (`max_tokens`) vale para Anthropic, OpenAI e OpenRouter (o `ChatOllama` não recebe esse
  parâmetro). Em modelo que **raciocina por padrão** ele é multiplicado por `FOLGA_RACIOCINIO = 4`,
  porque o raciocínio conta dentro do teto.
- Em modo **degradado** de orçamento, todo papel diferente de `roteamento` — inclusive `extracao` —
  é atendido pelo modelo de `roteamento` até o orçamento virar o mês. Temperatura, teto e esforço
  continuam os do papel pedido, e a governança grava o papel pedido.
- `llm.py` cacheia a instância com `lru_cache(maxsize=32)`; a **escolha do painel e o reserva do
  painel entram na chave do cache**: sem isso um worker de vida longa continuaria com o modelo (ou o
  reserva) antigo depois de uma troca.
- Cada instância recebe um `RegistradorUso(papel, provider)` como callback; o papel efetivo gravado
  pode ser sobrescrito pela contextvar `ctx_papel` de `shared/sdr_shared/governanca/uso.py`.
- Até 2026-09-28 a extração era gravada em `uso_llm` como `roteamento`; a comparação do papel
  `extracao` começa sem uso e mostra o mix de referência até acumular chamadas.

### Parâmetros por família de modelo

- `recusa_temperatura(model)`: Claude Sonnet 5+, Opus 4.7+, Fable e Mythos devolvem 400 para
  `temperature` fora do padrão em toda chamada; GPT-5 (fora `-chat`) e GPT-6 também não aceitam.
  Para esses, a temperatura não é enviada.
- `raciocina_por_padrao(model)`: Claude Sonnet/Opus 5+, Fable, Mythos, GPT-5/6, série o, Gemini 3.x.
  Recebem a folga no teto e o esforço do papel (Anthropic: mínimo `low`; OpenAI direta: `low`).
- Claude que raciocina é embrulhado em `SaidaEstruturadaNativa`: a extração usa
  `method="json_schema"`, porque com raciocínio ligado a Anthropic não força ferramenta e o Sonnet 5.5
  não permite desligar o raciocínio.

**Por que modelo por nível.** O ADR-0010 registra dois motivos: tarefas com exigências opostas
(roteamento roda em toda mensagem e pesa no preço; conversa é o que o cliente lê; análise roda
fora do turno e latência não importa) e o fato de que trocar de modelo antes exigia redeploy.
Um terceiro motivo foi o gatilho da decisão: `custo_usd` devolve `0.0` para modelo sem preço, e
trocar para um modelo fora da tabela desligava silenciosamente o teto mensal em dólar.

## Provedores

`_construir(provider, model, temp, papel)` em `factory.py` monta um provedor por vez. Os aceitos:

| Provedor | Classe | Papel no projeto | Chave |
|---|---|---|---|
| `anthropic` | `ChatAnthropic` | Primário padrão (`SDR_LLM_PROVIDER=anthropic`) | `ANTHROPIC_API_KEY` (sem prefixo `SDR_`); `SDR_ANTHROPIC_WORKSPACE_ID` quando a chave é de organização |
| `openai` | `ChatOpenAI` | Reserva de produção (ADR-0009, atualização 2026-09); pode ser primário | `OPENAI_API_KEY` (sem prefixo `SDR_`) |
| `ollama` | `ChatOllama` | Local, custo zero; `local/.env.example` o descreve como opção de desenvolvimento | nenhuma; `SDR_OLLAMA_URL` |
| `openrouter` | `ModeloOpenRouter`: dois `ChatOpenAI` com `base_url=SDR_OPENROUTER_URL` | Qualquer papel, pelo painel ou `.env` (ADR-0016), com retenção zero obrigatória; ver [OpenRouter](#openrouter) | `SDR_OPENROUTER_API_KEY` |

Variáveis relevantes, com os padrões de `shared/sdr_shared/config/settings.py` (a tabela completa
está em [Configuração](../getting-started/configuracao.md)):

| Variável | Padrão | Função |
|---|---|---|
| `SDR_LLM_PROVIDER` | `anthropic` | Provedor primário |
| `SDR_LLM_PROVIDER_FALLBACK` | vazio | Provedor de reserva; vazio = sem reserva |
| `SDR_MODEL_CONVERSA` | `claude-sonnet-4-5` | Modelo de `conversa` (e piso de `analise`) |
| `SDR_MODEL_ROTEAMENTO` | `claude-haiku-4-5` | Modelo de `roteamento` |
| `SDR_LLM_TIMEOUT_S` | `45.0` | Timeout por chamada |
| `SDR_OLLAMA_URL` | `http://localhost:11434` | Endereço do Ollama |
| `SDR_MODEL_EXTRACAO` / `SDR_MODEL_INFORMACOES` / `SDR_MODEL_ANALISE` | vazio | Modelo do papel; vazio herda do pai |
| `SDR_OPENROUTER_API_KEY` | vazio | Chave do OpenRouter |
| `SDR_OPENROUTER_ZDR` | `true` | Retenção zero em toda requisição; desligar só na bancada |
| `SDR_OPENROUTER_URL` | `https://openrouter.ai/api/v1` | Base da API (os testes apontam para um servidor falso) |

Divergência a registrar: o ADR-0010 recomenda **Sonnet 5** (`claude-sonnet-5`, US$ 2/10) para
`conversa` e `analise`, mas o padrão do código, o `.env.example` e a tabela `_EQUIVALENTE`
continuam em `claude-sonnet-4-5` (US$ 3/15). Até o ADR-0016 a troca nem funcionava: o Sonnet 5
recusa `temperature`, que o factory mandava sempre. Agora funciona, e a troca é pelo painel — sem
redeploy. A documentação da Anthropic dá a aposentadoria do Sonnet 4.5 como "não antes de
2026-09-29" e a do Haiku 4.5 como "não antes de 2026-10-15".

### Tradução de ID entre famílias

O fallback pode cair de uma família de modelo para outra, e `claude-sonnet-4-5` não existe na
OpenAI. `factory.py` resolve isso com três peças:

- `_FAMILIA = {"openai": ("gpt-", "o1", "o3", "o4"), "anthropic": ("claude",)}` — prefixos que
  identificam a família de um ID.
- `_EQUIVALENTE` — o par **por papel** quando a família não bate:

  | Provedor | `conversa` | `analise` | `roteamento` |
  |---|---|---|---|
  | `openai` | `gpt-5.6-terra` | `gpt-5.6-terra` | `gpt-5.6-luna` |
  | `anthropic` | `claude-sonnet-4-5` | `claude-sonnet-4-5` | `claude-haiku-4-5` |

  O pareamento é por posição na escala (conversa ↔ modelo bom, roteamento ↔ modelo barato), não
  por nome. `shared/tests/test_factory.py::test_todo_modelo_equivalente_tem_preco` garante que
  todo modelo dessa tabela tem linha em `PRECOS_PADRAO`.
- `modelo_do_provedor(model, provider, papel)` — mesma família: só normaliza o prefixo; família
  diferente: devolve o equivalente do papel. `normalizar_modelo(model, provider)` tira, só para
  `anthropic`, os prefixos `anthropic.`, `us.`, `eu.`, `apac.` que um `.env` herdado possa carregar
  (inclusive empilhados, como `us.anthropic.claude-…`). Para `ollama` a tradução é pulada.

`catalogo_de_modelos(tabela)` deriva a lista que o painel oferece **da própria tabela de preços**
(`PRECOS_PADRAO` mesclada com a configuração `precos` do banco), agrupando por `_FAMILIA`.
Consequência: cadastrar um preço novo faz o modelo aparecer no combo sem tocar no React, e o combo
nunca oferece modelo sem preço. Ollama fica de fora de propósito (o que existe lá depende do que
a máquina baixou), e a tela cai no campo livre. `bge-m3` e `llama3.1:8b` têm preço zero na
tabela mas não entram no catálogo porque não casam com nenhum prefixo de família.

## OpenRouter

Configuração passo a passo em [Usando o OpenRouter](../getting-started/openrouter.md).
Detalhe de implementação do [ADR-0016](../adr/0016-openrouter-e-modelo-por-funcao.md), em
`factory.py::_construir_openrouter` e `adapters/hospedados/openrouter.py`:

- **IDs** no formato `fornecedor/modelo`. `para_openrouter` e `de_openrouter` traduzem Anthropic e
  OpenAI nos dois sentidos (`claude-haiku-4-5` ↔ `anthropic/claude-haiku-4.5`); outro fornecedor
  indo para um reserva direto usa o equivalente do papel.
- **Preferências em toda requisição** (`preferencias_openrouter`): `data_collection: "deny"`,
  `zdr: true` (salvo `SDR_OPENROUTER_ZDR=false`) e `sort` por papel — `latency` em roteamento e
  extração, `throughput` em conversa e informações, `price` na análise.
- **Dois clientes.** `ModeloOpenRouter.invoke` usa o livre; `with_structured_output` usa o estrito,
  que liga `require_parameters` para cair só em endpoint que respeita o schema.
- **Catálogo** (`GET /models`, público, cache de 6 h por processo): decide se `temperature` e
  `reasoning` vão na requisição. Sem catálogo, decide pelo nome do modelo.
- **Custo:** `usage.cost` da resposta vai direto para `uso_llm` (`custo_informado` em `uso.py`), em
  vez da tabela.
- **Preço para a trava:** `POST /config/modelos/openrouter/sincronizar` grava o preço publicado de
  uma lista de modelos; o `PUT /config/modelos` com provedor `openrouter` busca sozinho antes de
  recusar. Modelos `anthropic/…` e `openai/…` usam a linha da tabela do fornecedor.
- O catálogo do painel só ganha o grupo `openrouter` quando há algum preço `fornecedor/modelo`
  cadastrado — os centenas de modelos do OpenRouter no combo não ajudariam ninguém.

- **Cache de prompt:** modelos `anthropic/…` e `qwen/…` recebem a mesma marcação `cache_control` da
  Anthropic direta (`MARCA_CACHE_OPENROUTER`); os demais fornecedores fazem cache sozinhos. Leitura e
  escrita de cache chegam a `uso_llm` (`cached_tokens` e `cache_write_tokens` da resposta).

Não implementado: identificar qual provedor atendeu por trás do OpenRouter (a resposta documentada não
traz o campo).

## Preços, registro de uso e orçamento

### Tabela de preços

`PRECOS_PADRAO` em `shared/sdr_shared/governanca/precos.py`, em **USD por 1 milhão de tokens**,
na ordem `(entrada, saída, escrita de cache, leitura de cache)`. O próprio arquivo avisa que é
uma cópia da documentação dos fornecedores num dado dia (Anthropic; OpenAI consultada em 2026-09)
e pode ser sobrescrita pelo painel (configuração `precos`).

| Modelo | Entrada | Saída | Cache escrita | Cache leitura |
|---|---|---|---|---|
| `claude-opus-5-5` | 4.0 | 20.0 | 5.0 | 0.40 |
| `claude-sonnet-5-5` | 2.0 | 10.0 | 2.50 | 0.20 |
| `claude-opus-5` | 5.0 | 25.0 | 6.25 | 0.50 |
| `claude-opus-4-1` | 15.0 | 75.0 | 18.75 | 1.50 |
| `claude-opus-4` | 15.0 | 75.0 | 18.75 | 1.50 |
| `claude-sonnet-5` | 2.0 | 10.0 | 2.50 | 0.20 |
| `claude-sonnet-4-6` | 3.0 | 15.0 | 3.75 | 0.30 |
| `claude-sonnet-4-5` | 3.0 | 15.0 | 3.75 | 0.30 |
| `claude-sonnet-4` | 3.0 | 15.0 | 3.75 | 0.30 |
| `claude-haiku-4-5` | 1.0 | 5.0 | 1.25 | 0.10 |
| `claude-haiku-3-5` | 0.80 | 4.0 | 1.0 | 0.08 |
| `gpt-6-astra` | 10.0 | 50.0 | 0.0 | 1.00 |
| `gpt-5.6-sol` | 5.0 | 30.0 | 0.0 | 0.50 |
| `gpt-5.6-terra` | 2.0 | 12.0 | 0.0 | 0.20 |
| `gpt-5.6-luna` | 0.20 | 1.20 | 0.0 | 0.02 |
| `gpt-5-mini` | 0.25 | 2.0 | 0.0 | 0.025 |
| `gpt-5-nano` | 0.05 | 0.40 | 0.0 | 0.005 |
| `bge-m3` | 0.0 | 0.0 | 0.0 | 0.0 |
| `llama3.1:8b` | 0.0 | 0.0 | 0.0 | 0.0 |

Notas do próprio código: na Anthropic, escrita de cache = 1,25× a entrada e leitura = 0,1× a
entrada; a OpenAI não cobra escrita de cache (terceiro valor zero) e o quarto valor é o preço de
"cached input"; Ollama e embeddings locais têm custo zero.

Funções auxiliares: `normalizar()` remove prefixos de provedor hospedado e sufixos de data/versão
(`-20250929`, `-v1:0`) para que IDs diferentes do mesmo modelo caiam na mesma chave;
`preco_do_modelo()` tenta a chave exata e depois prefixo; `custo_usd()` devolve `0.0` para modelo
desconhecido, arredondado a 6 casas.

### Registro de uso (`uso_llm`)

`RegistradorUso` (`shared/sdr_shared/governanca/uso.py`) é um `BaseCallbackHandler` do LangChain
registrado em toda instância de modelo. Em `on_llm_end`/`on_llm_error` ele grava uma linha em
`uso_llm` via `UsoRepository.registrar()` (`shared/sdr_shared/db/governanca.py`) com: `lead_id`,
`no`, `papel`, `provider`, `modelo`, tokens de entrada/saída/cache escrita/cache leitura,
`custo_usd`, `latencia_ms` e `erro`. Pontos verificados:

- `_tokens()` cobre os formatos de Anthropic, OpenAI e Ollama (`usage_metadata` com
  `input_token_details.cache_read`/`cache_creation`, ou `llm_output.usage`/`token_usage`).
- O custo é calculado com a tabela padrão mesclada aos preços do painel (`UsoRepository().precos()`).
- O `provider` gravado é o que **atendeu**: quando o reserva assume, a chamada não é contabilizada
  no nome do primário.
- Falha de gravação é engolida com `log.debug` — observabilidade não derruba o atendimento.

### Orçamento, degradação e bloqueio

`LIMITES_PADRAO` em `db/governanca.py`: `orcamento_mensal_usd: 50.0`, `teto_tokens_dia:
1_000_000`, `alerta_pct: 80`, `acao_ao_estourar: "degradar"`, `cotacao_brl: 5.12`. Tudo editável
pelo painel (chave `governanca` de `configuracoes`).

`estado_do_orcamento()` (cache de 60 s) calcula `pct = max(gasto_mes/teto_usd, tokens_hoje/teto_tok)`
e deriva o `modo`:

- `normal` — abaixo do teto;
- `degradado` — estourou e a ação é `degradar`: `get_chat_model` atende `conversa` e `analise`
  com o modelo de `roteamento`;
- `bloqueado` — estourou e a ação é `bloquear`, **ou** a ação é `degradar` e `pct >= TETO_DURO`
  (`1.5`, isto é, 150% do limite).

`_bloqueado_por_orcamento()` em `services/agent/src/agent/handler.py` roda antes do grafo, a cada
turno iniciado pelo cliente: se `modo_do_agente() == "bloqueado"`, escolhe um corretor, move o
lead para `HANDOFF`, audita `agente.bloqueado_por_orcamento`, responde "Vou chamar {corretor} para
continuar com você agora mesmo." e encerra o turno **sem chamar modelo**. Isso é o que o ADR-0009
chama de regra de negócio que um gateway não faria: degradar ou encaminhar a um humano, em vez de
só recusar a chamada.

## Comparativo de modelos

A comparação que o painel mostra é deliberadamente restrita ao que o projeto **mede ou decide**.
O docstring de `shared/sdr_shared/governanca/comparacao.py` explica a exclusão: janela de contexto,
limite de tokens e "velocidade" de catálogo não existem em lugar nenhum do repositório, e preencher
esses campos de memória faria alguém escolher modelo por número inventado.

### Como a conta é feita

`GET /config/modelos/comparacao?dias=30` (`services/api/src/api/routers/config.py`) devolve uma
lista **por papel** (`conversa`, `roteamento`, `analise`), cada uma ordenada da mais barata para
a mais cara. Para montar cada lista:

1. `UsoRepository.mix_por_papel(dias)` soma, por papel, chamadas e tokens (entrada, saída, cache)
   de `uso_llm` na janela, ignorando linhas com erro. Por papel, e não no total, porque a proporção
   entrada/saída é o que decide qual modelo sai mais barato.
2. `UsoRepository.latencia_por_modelo(dias, minimo=5)` calcula a **mediana** (`percentile_cont(0.5)`)
   de `latencia_ms` por papel e modelo. Mediana, não média, para uma chamada que pegou fila não
   puxar o número para sempre. Com menos de 5 amostras no papel, cai para a medição geral do
   modelo e marca `escopo: "geral"`; a tela mostra "outros papéis" nesse caso.
3. `catalogo_de_modelos(tabela)` dá as linhas; `recomendacoes(_EQUIVALENTE)` dá `{modelo: papel}`,
   preferindo `conversa` quando conversa e análise apontam para o mesmo modelo.
4. `comparar()` produz, por modelo: `preco`, `latencia` (`mediana_ms`, `amostras`, `escopo`),
   `recomendado_para` e `custo`.

**Custo contrafactual.** Quando o papel tem uso gravado (`mix["chamadas"] > 0`), o custo de cada
linha é o que os tokens **realmente consumidos** por aquele papel custariam com a tabela daquele
modelo (`base: "uso"`, com `dias` e `chamadas`). O código chama isso de estimativa, não previsão:
trocar de modelo muda o tamanho da resposta, e cache não se comporta igual entre provedores. Sem
uso gravado, a conta usa `MIX_REFERENCIA = {"entrada": 3000, "saida": 1000, ...}` (proporção 3:1
típica de conversa curta com histórico) e se declara `base: "referencia"`, com `dias: None`.

**Latência medida.** Modelo nunca chamado neste ambiente recebe
`{"mediana_ms": None, "amostras": 0, "escopo": None}` — nenhum número é inventado.

**Recomendações.** A coluna "Projeto usa para" sai da tabela `_EQUIVALENTE`, que é decisão
documentada, e não de opinião sobre qualidade. `test_recomendacao_sai_da_tabela_do_projeto_e_prefere_conversa`
confirma que `claude-opus-5` não aparece recomendado: o projeto não recomenda o que não escolheu.

A tela é `apps/dashboard/src/components/ComparacaoModelos.tsx`: um modal por papel, com colunas
Modelo, US$ por 1M (entrada · saída), Latência mediana, Custo (estimado ou "· N dias") e
"Projeto usa para". O aviso no topo muda conforme `base` é `uso` ou `referencia`. Clicar numa
linha preenche o campo do papel.

### Tabela comparativa derivada da tabela de preços

Ordem que `comparar()` produz com `catalogo_de_modelos()` e `PRECOS_PADRAO` atuais, do mais barato
ao mais caro. A coluna de custo é o mix de referência (3 000 entrada + 1 000 saída); empates são
desfeitos pelo nome do modelo, como no código (`key=(custo, modelo)`).

| # | Modelo | Provedor | US$/1M entrada | US$/1M saída | Custo no mix de referência (US$) | Recomendado para |
|---|---|---|---|---|---|---|
| 1 | `gpt-5-nano` | openai | 0.05 | 0.4 | 0.00055 | — |
| 2 | `gpt-5.6-luna` | openai | 0.2 | 1.2 | 0.0018 | roteamento |
| 3 | `gpt-5-mini` | openai | 0.25 | 2 | 0.00275 | — |
| 4 | `claude-haiku-3-5` | anthropic | 0.8 | 4 | 0.0064 | — |
| 5 | `claude-haiku-4-5` | anthropic | 1 | 5 | 0.008 | roteamento |
| 6 | `claude-sonnet-5` | anthropic | 2 | 10 | 0.016 | — |
| 7 | `claude-sonnet-5-5` | anthropic | 2 | 10 | 0.016 | — |
| 8 | `gpt-5.6-terra` | openai | 2 | 12 | 0.018 | conversa |
| 9 | `claude-sonnet-4` | anthropic | 3 | 15 | 0.024 | — |
| 10 | `claude-sonnet-4-5` | anthropic | 3 | 15 | 0.024 | conversa |
| 11 | `claude-sonnet-4-6` | anthropic | 3 | 15 | 0.024 | — |
| 12 | `claude-opus-5-5` | anthropic | 4 | 20 | 0.032 | — |
| 13 | `claude-opus-5` | anthropic | 5 | 25 | 0.04 | — |
| 14 | `gpt-5.6-sol` | openai | 5 | 30 | 0.045 | — |
| 15 | `gpt-6-astra` | openai | 10 | 50 | 0.08 | — |
| 16 | `claude-opus-4` | anthropic | 15 | 75 | 0.12 | — |
| 17 | `claude-opus-4-1` | anthropic | 15 | 75 | 0.12 | — |

**A ordem é a mesma em todos os papéis com a tabela atual.**
`shared/tests/test_comparacao_modelos.py::test_ordem_da_tabela_atual_e_a_mesma_em_todos_os_papeis`
afirma que a ordenação para um mix só de entrada, só de saída e 3 000/1 000 é idêntica — e o
docstring do teste vizinho explica o porquê: a razão saída/entrada varia pouco entre os modelos
(5× a 8×) perto da distância entre os preços. Isso foi reconferido para este documento aplicando
`custo_usd` aos três mixes sobre a tabela acima: as três listas coincidem. Portanto a lista por
papel **não** se justifica pela ordem; justifica-se pelo custo estimado e pela latência, que são
por papel de verdade. O teste com tabela inventada (`caro-na-entrada` × `caro-na-saida`) prova
que a conta reage ao mix se um dia entrar um modelo com razão extrema.

Esta tabela é sobre **preço**, não sobre qualidade. Nada aqui diz qual modelo responde melhor;
ver [Harness de avaliação](#harness-de-avaliacao).

## Timeout, retries e provedor de reserva

Os números de `factory.py` e `settings.py`:

- `llm_timeout_s = 45.0` no `.env`; o painel pode sobrescrever pela chave `operacao.llm_timeout_s`
  (`_timeout_do_painel()`), validada em `_validar_operacao` para a faixa **5 a 180 s**. A régua,
  segundo o comentário do código, é a espera do cliente, não o provedor.
- `MAX_RETRIES = 1`: uma tentativa a mais além da primeira, em todo provedor hospedado. O
  comentário registra por que não 2: com 2, o pior caso era 45 s × 3 tentativas × 2 provedores =
  270 s, e o lock por lead (então 180 s fixos) expirava no meio.
- `orcamento_do_turno_s(timeout_s=None)` = `espera * (1 + MAX_RETRIES) * 2 + 30`: cada provedor
  tenta `1 + MAX_RETRIES` vezes até o timeout, há no máximo dois provedores, e 30 s de folga para
  banco e embeddings. Com os padrões: 45 × 2 × 2 + 30 = **210 s**. É a validade do lock por lead
  em `shared/sdr_shared/adapters/local/broker.py::_lock_s()` — abaixo dela, o lock expiraria com
  o turno em curso e duas respostas sairiam para a mesma mensagem.
- Reserva: `get_chat_model` monta `ModeloComFallback(primario, reserva)` quando há reserva definido
  e ele é diferente do primário. A ordem de precedência é `_reserva_do_painel()` (chave
  `modelos.fallback_provider`), depois `SDR_LLM_PROVIDER_FALLBACK`. A string `"nenhum"` no painel
  **desliga** o reserva herdado do ambiente — sem ela, apagar o campo não desfaria um fallback do
  `.env`. `_validar_modelos` recusa reserva igual ao provedor de conversa (seriam duas tentativas
  no provedor que caiu).
- `ModeloComFallback.invoke` tenta o primário e, em qualquer exceção (portanto só depois dos
  retries internos dele), repete no reserva com um `log.warning`. `with_structured_output` é
  reimplementado no wrapper porque `Runnable.with_fallbacks` do LangChain o perde, e a extração
  do cartão depende dele. O ADR-0009 registra o custo: o pior caso de latência dobra.
- `POST /config/modelos/testar` (`config.py`) faz **uma** chamada real com `_construir(provider,
  modelo, 0.0, "roteamento").invoke("Responda apenas: ok")` e devolve `ok`, `latencia_ms`, os
  primeiros 120 caracteres da resposta, `tem_preco` e `preco`. Responde o que uma lista fixa não
  responde: o ID existe neste provedor, e quanto demora. Não passa pelo fallback.

Quando tudo isso falha, `handler.py` captura a exceção do grafo, audita `agente.turno_falhou` e
envia `_responder_falha` — o cliente recebe uma mensagem de desculpa em vez de silêncio.

## Embeddings e transcrição

**Embeddings** (`get_embedder` em `factory.py`). Três provedores, todos em **1024 dimensões**,
porque o schema declara `vector(1024)` em `imoveis.embedding` e `documentos.embedding`
(`shared/sdr_shared/db/schema.sql`):

| `SDR_EMBEDDINGS_PROVIDER` | Adaptador | Modelo | Observação |
|---|---|---|---|
| `ollama` (padrão do código) | `shared/sdr_shared/adapters/local/embeddings.py::OllamaEmbedder` | `SDR_OLLAMA_EMBEDDING_MODEL=bge-m3` | `dimensoes = 1024 if "bge-m3" in model else 768`; custo zero; exige o container do Ollama e `make ollama-pull` |
| `openai` (sugerido em `local/.env.example`) | `shared/sdr_shared/adapters/hospedados/embeddings.py::OpenAIEmbedder` | `SDR_EMBEDDINGS_MODEL=text-embedding-3-small` | Envia `dimensions=SDR_EMBEDDINGS_DIMENSOES` (`1024`) e valida o tamanho do vetor devolvido; dispensa o container; usa a mesma `OPENAI_API_KEY` |
| `openrouter` | `…/hospedados/embeddings.py::OpenRouterEmbedder` | `SDR_EMBEDDINGS_MODEL` (sem fornecedor vira `openai/text-embedding-3-small`) | Mesmo modelo, mesmos vetores do `openai`: trocar de um para o outro **não** exige reindexar. Usa `SDR_OPENROUTER_API_KEY`; manda `provider.data_collection: deny`, mas **não** `zdr` — nenhum modelo de embedding estava na lista de endpoints ZDR (2026-09-28), e exigi-lo derrubaria a busca. `baai/bge-m3` também serve (outro modelo: reindexar) |

O piso de similaridade do RAG (`conhecimento.PISO_POR_EMBEDDER`) é por **modelo**, não por provedor:
`text-embedding-3-small` → 0,48 por qualquer caminho; `bge-m3` → 0,35 pelo Ollama ou pelo OpenRouter.

Provedor desconhecido levanta `RuntimeError` em vez de cair no padrão: gravar vetor de outro
modelo no mesmo índice não dá erro na hora, dá busca errada depois. Trocar de modelo exige
reindexar (`make seed` e `make docs-kb`). A Anthropic não oferece API de embeddings, por isso a
escolha é independente do provedor de LLM. Há um preço `bge-m3: 0.0` na tabela; `text-embedding-3-small`
não tem linha, então seu custo (se registrado) sairia como zero — os embeddings não passam pelo
`RegistradorUso`, que é um callback de chat model.

**Transcrição** (`services/agent/src/agent/tools/transcricao.py`). Um motor só: **faster-whisper**
in-process, sem serviço externo e sem custo por minuto. Verificado no código:

- `WhisperModel(get_settings().whisper_model, device="cpu", compute_type="int8")`, carregado uma
  vez por processo; `int8` porque é leve em CPU e suficiente para voz curta de qualificação.
- `SDR_WHISPER_MODEL=small` (opções `tiny|base|small|medium|large-v3`); o comentário em
  `settings.py` diz que `small` equilibra qualidade e CPU/RAM para pt-BR.
- Idioma fixo: `_LANG = "pt"`.
- `SDR_TRANSCRICAO_PROVIDER`: `auto` e `whisper_local` dão no mesmo; `off` levanta e o cliente
  recebe o pedido para escrever. Também ajustável pelo painel (`operacao.transcricao`).
- Exige o extra `local` do agente; `make whisper-aquecer` existe no `Makefile` para baixar o modelo
  antes do primeiro áudio.

## Decisões e trade-offs

Resumo do que os ADRs registram (texto completo em
[ADR-0009](../adr/0009-gateway-de-llm-litellm-openrouter-ou-nada.md) e
[ADR-0010](../adr/0010-modelo-por-nivel-e-troca-pelo-painel.md)):

- **Sem gateway de LLM.** LiteLLM e OpenRouter foram avaliados e recusados: a camada que eles
  ofereceriam (ponto único, registro de uso, teto de orçamento, fallback) já existe em
  `factory.py` + `governanca/`, e a parte que mais valeria terceirizar — o que fazer ao estourar o
  teto — é regra de negócio (degradar ou encaminhar ao corretor). Contra o LiteLLM pesaram mais um
  container residente com Postgres e Redis próprios, ponto único de falha e histórico de segurança;
  contra o OpenRouter em produção, PII de cliente passando por um terceiro (LGPD) e mudança de
  controle recente.
- **OpenRouter como bancada.** `_construir` aceita `provider="openrouter"` para o harness comparar
  modelos sobre datasets sintéticos. Hoje, porém, o harness em `services/agent/evals/` não
  referencia OpenRouter em lugar nenhum — a porta existe no factory, o uso por `evals/` não foi
  localizado.
- **OpenAI como reserva de produção**, sem intermediário. Consequências registradas: a tabela
  `_EQUIVALENTE`, a exigência de preço para todo modelo equivalente e mais um subprocessador a
  documentar na política de privacidade (pendente, segundo o ADR).
- **Modelo por nível com quatro travas**: recusar modelo sem preço (422), testar antes de salvar,
  invalidar cache ao salvar/apagar, e mostrar o efetivo (`GET /config` devolve `efetivo` por nível
  com `origem: painel|ambiente`).
- **Fora de propósito**: cache de prompt (a contabilidade está pronta em `_tokens()` e
  `custo_usd()`, falta ligar) e Batch para o resumidor. O ADR-0010 avalia que o cache renderia
  mais que qualquer troca de modelo. Gemini fica fora por ser um terceiro operador de dados sem
  motivo que o justifique.
- **Trade-offs assumidos**: a tabela de preços é uma cópia num dado dia, não consulta ao vivo;
  o fallback dobra a latência do pior caso; não há cache de LLM nem chaves virtuais por time.

### Harness de avaliação

`services/agent/evals/` (README em `services/agent/evals/README.md`) mede o **modelo**, enquanto
`tests/` mede o encanamento com LLM falso. Suítes: `extracao` (acerto por campo + campos
inventados), `coerencia`, `roteamento` (acurácia + matriz de confusão), `adversarial` (taxa de
escape), `rag` (recall@3, acerto no topo, abstenção), `recomendacao`, `informacoes` (cita a fonte,
número fora do trecho, abstenção sem base) e `analise` (análise estruturada válida). Nenhuma usa
juiz-LLM. Cada suíte que mede um modelo pertence a um papel (`suites.PAPEL_DA_SUITE`), e
`make eval-matriz` compara os candidatos de `evals/matriz.json` papel a papel. Alvos do `Makefile`:

| Alvo | O que faz |
|---|---|
| `make eval` | Todas as suítes, modelo real (chama a API; fora do CI de propósito) |
| `make eval-fake` | Valida o harness com LLM falso e embedder de trigramas; roda no CI; os números não dizem nada sobre qualidade |
| `make eval-rag` | Só o RAG institucional, com o embedder real do `.env` |
| `make eval-matriz` | Candidatos por papel, lado a lado (`evals/matriz.json`), cada um num processo com o modelo do papel trocado e sem reserva; `ARGS="--plano"` estima as chamadas antes |
| `make eval-embeddings` | Roda a suíte `rag` duas vezes, reindexando com `ollama` (bge-m3) e depois `openai` (text-embedding-3-small), para comparar recall@3 e abstenção lado a lado |

**Resultados.** Há uma execução com modelo real, de 2026-09-24 (`resultados/20260924-235359.json`,
uma repetição por caso, US$ 0,20 em 55 chamadas): extração 88% de aprovação (95,2% de acerto por
campo, 1 campo inventado), roteamento 100%, adversarial 0% de escape, RAG com recall@3 de 87,9% e
abstenção de 16,7% nas perguntas fora do corpus. O arquivo grava `"modelo": "padrão"` porque o
relatório de então lia só `SDR_MODEL_CONVERSA`; desde 2026-09-28 ele grava o modelo efetivo de cada
papel e o que de fato atendeu (lido de `uso_llm`). Não há comparativo de qualidade entre modelos. A única medição de
qualidade citada nos ADRs é a do RRF léxico (recall 31,9% → 29,8%, em `decisoes.md`), que é sobre
o RAG, não sobre modelo de linguagem. Qualquer afirmação de "modelo X responde melhor" precisa
sair de `make eval` rodado na sua máquina, com `-n 3` ou mais, como o README recomenda.

## Cache de prompt

Todo turno manda o mesmo prefixo: blindagem, persona, prompt do nó e o histórico podado. Sem
marcação, esse prefixo é cobrado como entrada nova a cada chamada. A Anthropic cobra a **leitura**
de cache por 10% do preço da entrada, e a governança já media esses tokens (`uso.py` lê
`cache_read` e `cache_creation`; `precos.py` tem as quatro colunas) — só faltava marcar.

`ModeloComCacheDePrompt` (`shared/sdr_shared/ports/factory.py`) põe **dois pontos de corte**: no fim
da mensagem de sistema e no fim do histórico. Dois, e não um, porque medimos os prompts:

| Prefixo | Tamanho | Engata no Sonnet (mínimo 1024 tokens)? |
|---|---|---|
| Blindagem + persona | ~640–740 tokens | não |
| ... + prompt do nó | ~730–1160 tokens | só nos nós maiores (`analise`, `informacoes`, `extracao`, `qualificador`) |
| ... + histórico podado | cresce com a conversa | sim, a partir de poucas trocas |

Ou seja: o corte no sistema sozinho quase nunca pagaria. Quem faz a conta fechar é o corte no fim do
histórico — ele deixa o turno seguinte do mesmo lead reler tudo até ali por 10%.

**O que esperar.** O TTL do cache é de 5 minutos. Conversa de SDR tem intervalo de minutos entre
mensagens e follow-up em horas, então a taxa de acerto é modesta por natureza: ganha nas trocas
rápidas, não no acompanhamento. Por isso o indicador existe — **zero em "Leitura de cache" é um
resultado, não um defeito**, e diz que o prefixo não passou do mínimo ou que o intervalo passou de
5 minutos.

**Cuidados no código.**

- **Anthropic, direta ou pelo OpenRouter** (e Qwen pelo OpenRouter). `cache_control` é campo da API
  da Anthropic; mandá-lo para a OpenAI direta é erro de requisição — e a OpenAI já faz cache de
  prefixo sozinha, sem marcação. Pelo OpenRouter, o cache em memória não conta como retenção (vale
  com ZDR) e chamadas seguidas do mesmo modelo vão ao mesmo provedor. Ollama não tem o conceito.
- **A marcação copia a mensagem.** O histórico vive no checkpoint do grafo; marcar o original
  gravaria metadado de transporte dentro do estado da conversa. Há teste para isso.
- **Entrada que não é lista passa intacta.** O caminho `texto()` (supervisor e extração do cartão)
  manda uma string: ali não há prefixo reaproveitável.
- **Desligar:** `SDR_PROMPT_CACHE=false`. O modelo volta a ser o objeto cru, sem embrulho.

## Como trocar de modelo na prática

O caminho é o painel, área **Configuração do agente** (ver [Manual do painel](../user-guide/painel.md)),
que fala com `PUT /config/modelos`. Passo a passo conforme o código:

1. Escolha o papel (`conversa`, `roteamento` ou `analise`) e o provedor. O combo mostra o que
   `catalogo_de_modelos()` devolve; para `ollama` o campo é livre.
2. Opcionalmente abra a comparação (`ComparacaoModelos`) para ver preço, custo contrafactual e
   latência medida no seu ambiente.
3. **Teste** (`POST /config/modelos/testar`): confirma que o ID existe no provedor, mostra a
   latência e avisa se falta preço.
4. Salve. `_validar_modelos` recusa com 422 modelo sem preço (exceto Ollama), provedor desconhecido,
   ID com espaço ou acima de 120 caracteres, e reserva igual ao provedor de conversa. Ao salvar,
   `invalidar_cache_modelos()` faz a troca valer no próximo turno.
5. Para voltar ao `.env`, apague o campo ou use `DELETE /config/modelos`; não precisa de acesso ao
   banco nem de redeploy.
6. Se o modelo novo não estiver em `PRECOS_PADRAO`, cadastre o preço antes em Configurações →
   preços (chave `precos` de `configuracoes`); sem isso o custo é contabilizado como zero e o teto
   mensal em dólar deixa de valer.

Mudanças correlatas no mesmo lugar: `fallback_provider` (reserva; `nenhum` para desligar) e
`operacao.llm_timeout_s` (5–180 s). O `GET /config` mostra, por nível, o que o agente vai usar no
próximo turno e se veio do painel ou do ambiente — é isso que a tela exibe, não a intenção.

## Referências

- `shared/sdr_shared/ports/factory.py` — `get_chat_model`, `_construir`, `ModeloComFallback`,
  `_FAMILIA`, `_EQUIVALENTE`, `catalogo_de_modelos`, `orcamento_do_turno_s`.
- `shared/sdr_shared/governanca/precos.py`, `uso.py`, `comparacao.py`.
- `shared/sdr_shared/db/governanca.py` (`UsoRepository`, `estado_do_orcamento`) e `db/modelos.py`.
- `services/agent/src/agent/llm.py`, `handler.py`, `tools/transcricao.py`.
- `services/api/src/api/routers/config.py` — rotas `/config/modelos`, `/config/modelos/comparacao`,
  `/config/modelos/testar`.
- `apps/dashboard/src/components/ComparacaoModelos.tsx`.
- `shared/tests/test_comparacao_modelos.py`, `shared/tests/test_factory.py`.
- [Configuração](../getting-started/configuracao.md) · [Decisões arquiteturais](decisoes.md) ·
  [Componentes](componentes.md).
