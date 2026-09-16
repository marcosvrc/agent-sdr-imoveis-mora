---
title: "ADR-0013: Reativação proativa de leads adormecidos"
description: Por que a Mora avisa sobre imóvel novo, quem ela pode avisar, como o motivo é calculado e como se sai da lista.
---

# ADR-0013 — Reativação proativa de leads adormecidos

**Status:** aceito · **Data:** 2026-09 · **Contexto:** fases 1–4 da reativação

## Contexto

A maior parte dos leads de uma imobiliária não é perdida por falta de imóvel: é perdida por
**desencontro de tempo**. A pessoa procurou dois quartos no Brooklin até R$ 800 mil quando não havia
nenhum; três semanas depois o imóvel entra na base e ninguém liga o fato à conversa que morreu.

O follow-up que já existia não resolve isso: ele reengaja por *tempo* ("faz três dias que você sumiu")
e se esgota em poucas tentativas. Reativação é o contrário — reengajar por *fato novo*, sem prazo para
acontecer e possivelmente meses depois.

## Decisão

Quando um imóvel **entra** na base, o sistema avalia os leads adormecidos contra ele e avisa os que
casam, com o motivo explícito.

### 1. Pontuação determinística, não embedding

O cartão de qualificação é estruturado (operação, preço, quartos, bairro, urgência) e o imóvel também.
Similaridade vetorial responderia "parecido", quando a pergunta é "cabe no que ele pediu" — e ainda
devolveria um número que ninguém consegue explicar ao cliente.

A régua (`shared/sdr_shared/reativacao.py`) tem **eliminatórios** (operação, teto de preço, quartos,
tipo pedido) e **pontos** (bairro exato, folga no orçamento, urgência, selo de investimento), com
`PONTOS_MINIMOS = 60`. Cada ponto produz um motivo em português — *"bairro exato: Brooklin"*, *"R$ 100
mil abaixo do teto"* — e é esse texto que vira a primeira frase da mensagem. Motivo verificável é o que
separa reativação de disparo em massa.

### 2. O aviso passa pelo grafo, não pelo canal

O worker (`agent/reativador.py`) só **seleciona** e publica uma `MensagemNormalizada` do tipo
`reativacao` na fila `inbound`. Daí em diante é um turno normal do agente: guardrails, orçamento de
LLM, sanitização da saída, auditoria e registro em `turnos`.

Escrever direto no canal seria bem mais curto — e deixaria justamente a única mensagem que a Mora manda
sem ninguém ter pedido fora de todo o controle que existe no sistema.

Turnos iniciados pelo agente (`INICIADAS_PELO_AGENTE`) não contam para a vazão, não viram mensagem
recebida no histórico e **não carimbam `ultima_mensagem_em`** — carimbar apagaria o silêncio que
motivou o contato.

### 3. Limites de spam, em três camadas

| Camada | Limite | Onde |
| --- | --- | --- |
| Silêncio mínimo | 3 dias sem falar (`DIAS_SILENCIO`) | `reativacao.elegivel` |
| Cadência | 1 aviso a cada 7 dias (`DIAS_ENTRE_REATIVACOES`, via `reativado_em`) | `reativacao.elegivel` |
| Repetição | imóvel já apresentado/descartado/com visita não volta | tabela `interesses` |
| Por imóvel | no máximo 20 avisos (`MAX_AVISOS`) | `agent/reativador.py` |
| Por carga | rodada que insere mais de 5 imóveis não anuncia nada | `ingest_imoveis.LIMITE_AVISOS_POR_LOTE` |

O último merece nota: `make seed` recarrega o catálogo inteiro. Sem separar **inserção** de
**atualização** (`ImovelRepository.upsert` devolve isso) e sem o teto por lote, uma reingestão avisaria
a base inteira sobre imóveis que já estavam lá.

Ficam de fora, sempre: lead encerrado, em handoff (o corretor está falando), sem canal de conversa
aberto, e quem pediu para não receber.

### 4. Opt-out em dois lugares

`leads.aceita_reativacao` é honrado pela régua, e pode ser desligado:

- **pelo cliente**, na conversa — "não quero mais receber avisos" é roteado pelo supervisor antes de
  qualquer outra regra (inclusive antes do guardrail de escopo, que leria a frase como off-topic) e
  responde com texto **fixo**: confirmar preferência é recibo, e gerar o texto abriria espaço para a
  Mora tentar convencer a pessoa a ficar;
- **pelo corretor**, no painel (`PUT /leads/{id}/reativacao`), porque o pedido também chega por
  telefone, por e-mail e no meio de uma visita.

### 5. A medição sai da auditoria, não de uma tabela de campanha

`lead.reativado`, `visita.agendada` e `lead.optout_reativacao` já registram tudo que o funil precisa —
carimbo de tempo, lead e o imóvel em `dados`. Uma tabela de campanha guardaria o mesmo fato num
segundo lugar, com a chance de os dois discordarem.

`GET /dashboard/reativacao?dias=30` devolve avisos → **responderam** (só quem voltou a falar em até
48h; mais tarde é conversa nova) → **viraram visita** → **pediram para sair**, mais quantos leads o
worker avaliou para chegar nos que avisou. A janela é de 30 dias porque reativação é lenta por
natureza: sete dias mostrariam zero quase sempre.

A taxa de **saída** aparece ao lado da de resposta de propósito. Olhar só quantos responderam esconde
o custo do recurso: com a régua frouxa, respostas e opt-outs sobem juntos — e o opt-out é
irreversível. As três taxas somem (`null`) quando não houve aviso no período: 0% de resposta sobre
zero aviso é uma afirmação falsa sobre a campanha.

## Consequências

- Uma coluna (`reativado_em`) e uma tabela (`interesses`) passam a ser **load-bearing**: sem elas a
  cadência não tem em que se apoiar e o mesmo lead recebe o mesmo imóvel a cada execução do worker.
- O painel simula o envio em modo seco (`GET /reativacao/imovel/{id}`), listando também os excluídos
  **com o motivo** — é assim que se calibra a régua antes de escrever para alguém de verdade.
- `turnos.resultado = "reativacao"` separa o aviso da conversa pedida pelo cliente, e o bloco
  **Reativação** na Visão geral mostra o funil (fase 4).

## Alternativas descartadas

- **Busca vetorial lead↔imóvel** — descrito acima: sem motivo explicável, e o cartão já é estruturado.
- **Enviar direto pelo canal, sem grafo** — perde guardrails, orçamento e auditoria na única mensagem
  não solicitada do sistema.
- **Avisar sobre todo imóvel atualizado** — transforma manutenção de cadastro em notificação.
- **Deduzir o descarte da conversa** ("ver outros" ⇒ descartou) — pedir mais opções não é recusar as
  anteriores; o descarte continua sendo ato explícito, no painel ou pela fala do cliente.
