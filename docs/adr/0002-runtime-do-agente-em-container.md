# ADR-0002 — Runtime do agente: container local consumindo uma fila

**Status:** aceito · **Data:** 2026-09-08 · **Revisto em 2026-09-12**

## Contexto
Um turno multiagente faz de 2 a 5 chamadas ao modelo e leva de 20 a 40 segundos. O agente não pode
responder no fio da requisição HTTP do canal: o cliente escreve, o canal confirma o recebimento, e
a resposta volta pelo mesmo caminho quando estiver pronta.

## Decisão
O agente é um **worker**: um processo que consome o tópico `inbound` do broker e publica no tópico
de saída do canal. Hoje ele roda como um container no `local/docker-compose.yml`, com Redis fazendo
o papel de fila.

O ponto que importa não é o container: é `agent/handler.py` ser um consumidor puro, que recebe uma
`MensagemNormalizada` e devolve uma resposta. Quem chama esse consumidor — um `while` no worker,
um event source de fila gerenciada, um runner de container — é detalhe de empacotamento, e trocá-lo
não toca em nó nenhum do grafo.

## Alternativas
- **Responder dentro do HTTP do canal.** Mais simples de montar e errado pelo motivo certo: 40
  segundos de requisição aberta estoura o timeout de qualquer webhook, e uma falha no meio perde a
  mensagem do cliente sem deixar rastro.
- **Runtime gerenciado de agente.** Havia aqui uma decisão por função hospedada em container, com
  a fila gerenciada por trás. A entrega passou a ser **inteiramente local** — roda com um `docker
  compose up` na máquina de quem avalia, sem conta em nuvem, sem provisionamento e sem custo — e a
  decisão hospedada foi removida junto com o resto da infraestrutura. O desenho em fila continua
  sendo o que torna essa volta barata, se ela for desejada.

## Consequências
- (+) Quem clona o repositório consegue rodar tudo. Para um trabalho que é avaliado sendo
  executado, isso vale mais que a arquitetura de implantação.
- (+) A fila absorve pico e permite reprocessar: o turno que falhou não some.
- (−) Não há nada implantado, e este repositório não prova nada sobre operação em produção —
  escala, custo real, tolerância a falha de região. É limitação declarada, não pendência escondida.
