---
title: Escolha dos modelos
description: Qual modelo de linguagem atende cada função da Mora, por que foi escolhido, o que foi avaliado e descartado, e como a escolha é revista sem redeploy.
---

# Escolha dos modelos

A Mora não usa "um modelo": usa **um modelo por função**, escolhido pelo critério que importa
naquela função. O resultado é barato e rápido onde basta, e o melhor modelo onde o cliente lê.
Esta página explica a escolha; o funcionamento (papéis, provedores, preços, reserva) está em
[Modelos de linguagem](modelos.md).

## Os critérios

Cada função do agente pede coisas diferentes de um modelo. Foi isso que definiu a escolha, não a
fama do modelo.

| Função | O que a Mora precisa | O que pesa na escolha |
|---|---|---|
| **Conversa** | Escrever o que o cliente lê: português natural, curto, com a persona | Qualidade do texto e resistência a abuso de prompt; custo por mensagem, porque é a chamada mais frequente |
| **Roteamento** | Decidir qual especialista age, quando as regras não bastam | Tempo até o primeiro token (o cliente está esperando) e acerto na decisão; custo quase irrelevante, a resposta é uma palavra |
| **Extração** | Preencher o cartão do lead em JSON a partir do que o cliente disse | Não inventar dados e respeitar o schema; latência moderada |
| **Informações** | Responder políticas da imobiliária a partir dos documentos (RAG) | Fidelidade ao trecho recuperado, citar a fonte, admitir quando não há base |
| **Análise** | Briefing e análise do lead para o corretor, fora do turno | Qualidade e saída estruturada; latência não importa, roda em segundo plano |

Dois critérios valem para todos: **retenção zero** (o provedor não guarda prompt nem resposta,
exigido em toda chamada pelo OpenRouter) e **preço conhecido**, porque o painel recusa um modelo
sem preço cadastrado — sem isso o orçamento por lead não fecha.

## A escolha por função

Os modelos abaixo são os da configuração de demonstração (`SDR_MODEL_*` no `.env`), e são os que o
registro de uso (`uso_llm`) mostra atendendo cada função. Todos saíram de uma avaliação lado a
lado, em 29/09/2026, com três repetições por caso, sobre as suítes de cada função
(`make eval-matriz`); as tabelas completas estão em
[Avaliação dos modelos (29/09/2026)](avaliacao-modelos-2026-09-29.md). Custo e latência são os
medidos na avaliação, não os de tabela.

| Função | Modelo escolhido | Por quê | Alternativas avaliadas |
|---|---|---|---|
| Conversa | **DeepSeek V4.1 Flash** | Aprovou 100% dos casos adversariais, igual ao Claude Sonnet 5, com **1/16 do custo** (US$ 0,009 contra 0,143 na suíte) e menos da metade da latência (0,9 s contra 2,2 s) | Claude Sonnet 5: mesma aprovação, caro. GPT-6 Sol: 72%, com chamadas falhando por limite de uso |
| Roteamento | **gpt-oss-120b** | 94% de acerto com **0,6 s** por decisão; o modelo é aberto e barato, e a decisão é uma palavra | GPT-6 Luna: 59% de acerto e 3 s. Nemotron 3.5 Lightning: 88–91%, um pouco mais rápido, mas erra mais |
| Extração | **GPT-6 Luna** | 88% de aprovação, 95% de acerto por campo e só 3 dados inventados em 132 chamadas, empatado com o Claude Sonnet 5 a **1/28 do custo** | Claude Sonnet 5: mesmo acerto, US$ 1,21 na suíte. DeepSeek V4.1 Flash: 68%, com 23 dados inventados, inaceitável para o cartão. gpt-oss-120b: não respeita o schema |
| Informações | **DeepSeek V4.1 Flash** | 87% de aprovação, cita a fonte em 100% dos casos e sabe dizer que não há base; o mais barato e o mais rápido do grupo (0,9 s) | GPT-6 Luna: 80%, mais inventado. GPT-6 Sol: instável na avaliação |
| Análise | **DeepSeek V4.1 Flash** | 100% de aprovação com saída estruturada em 100%, por US$ 0,008 na suíte; como roda fora do turno, os 9 s de latência não afetam o cliente | Claude Opus 5.5: também 100%, a **38 vezes o custo**. GLM 5.3 Flash: 67%, 39 s. GPT-6 Sol: instável |

Resumo: o DeepSeek V4.1 Flash leva três funções porque empatou em qualidade com modelos muito mais
caros; onde ele falhou, na extração, entrou o modelo que não inventa dados. O roteamento usa o
modelo mais rápido que acerta.

### Padrão e reserva

- **Padrão sem OpenRouter:** Claude Sonnet 4.5 na conversa e Claude Haiku 4.5 no roteamento, pela
  API da Anthropic. É a configuração de origem do projeto, com cache de prompt ligado, e continua
  válida para quem prefere contratar um único fornecedor.
- **Reserva automática:** se o provedor principal falha, a chamada vai para a OpenAI com o modelo
  equivalente do mesmo nível (GPT-5.6 Terra na conversa e na análise, GPT-5.6 Luna no roteamento).
  O par é por posição, não por nome: modelo bom com modelo bom, modelo barato com modelo barato.
- **Local:** Llama 3.1 8B pelo Ollama é a opção de desenvolvimento sem custo e sem chave, como o
  próprio `.env` a descreve. Não entrou na matriz de avaliação e não é usada no atendimento.

## O que foi avaliado e descartado

| Opção | Por que ficou de fora |
|---|---|
| **Um modelo para tudo** | As exigências são opostas: o supervisor quer o primeiro token mais rápido que existir; a extração quer o modelo que menos erra em JSON. Com um modelo só, trocar um quebrava o outro (ADR-0010 e ADR-0016) |
| **Gateway LiteLLM** | Mais um container residente, com Postgres e Redis próprios, ponto único de falha; a parte que valeria terceirizar, o que fazer ao estourar o orçamento, é regra de negócio e ficou no código (ADR-0009) |
| **OpenRouter sem retenção zero** | Recusado na primeira avaliação por privacidade. Aceito depois com a retenção zero obrigatória em toda requisição e `data_collection: deny`, o que limita o roteamento a endpoints que também não guardam dados (ADR-0016) |
| **Gemini** | Um terceiro operador de dados sem ganho que o justificasse (ADR-0010) |
| **Sabiá (Maritaca)** | Não está no OpenRouter; entraria por um provedor direto se a avaliação justificar |
| **Modelo local na conversa** | Não foi avaliado para atendimento; fica como opção de desenvolvimento, sem custo |

## Como a escolha é revista

A escolha não é fixa no código; é configuração, e o próprio sistema mede se ela continua boa.

- **Comparativo no painel.** A tela de Modelos mostra, por função, o custo de tabela e a latência
  mediana medida em uso real de cada modelo. A decisão é pelo número medido, não por suposição.
- **Troca sem deploy.** O modelo de cada função é trocado no painel; a Mora testa o modelo antes
  de salvar e recusa modelo sem preço.
- **Avaliação repetível.** `make eval-matriz` roda os candidatos de cada função
  (`services/agent/evals/matriz.json`) sobre as suítes daquela função e produz a tabela de
  aprovação, custo e latência. É o que gerou os números desta página; rodar de novo com modelos novos
  é a forma de rever a escolha.
- **Orçamento por lead.** Se um lead estoura o teto de gasto com IA, todas as funções passam ao
  modelo de roteamento, o mais barato, e o corretor é avisado.

Detalhes das decisões: [ADR-0009](../adr/0009-gateway-de-llm-litellm-openrouter-ou-nada.md),
[ADR-0010](../adr/0010-modelo-por-nivel-e-troca-pelo-painel.md) e
[ADR-0016](../adr/0016-openrouter-e-modelo-por-funcao.md).
