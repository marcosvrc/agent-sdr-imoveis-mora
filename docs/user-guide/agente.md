---
title: Manual do agente (Mora)
description: Como acessar a Mora, iniciar uma conversa, o que ela faz, exemplos e limitações.
---

# Manual do agente (Mora)

## Como iniciar

- Abra o site (<http://localhost:5173>) e clique em **"Falar com a Mora"**, ou
- Envie uma mensagem ao bot do Telegram configurado.

A Mora se apresenta na primeira mensagem.

## Capacidades

- Entende a intenção (comprar, alugar, investir).
- Coleta região, faixa de preço, quartos e urgência.
- Recomenda imóveis do catálogo, com explicação.
- Oferece horários de visita.
- Encaminha para um corretor quando solicitado.
- **Avisa quando entra um imóvel novo** que casa com o que o cliente procurava, mesmo semanas depois.

## Mensagens de voz

A Mora é **multimodal na entrada**: o cliente pode mandar um **áudio** (mensagem de voz) no Telegram
(ou no WhatsApp, quando o canal estiver ativo) que o agente transcreve e responde normalmente.

- No **perfil local**, a transcrição roda 100% na máquina com o faster-whisper — sem AWS e sem custo.
- No **perfil AWS**, usa o Amazon Transcribe.
- Se a transcrição falhar, a Mora pede educadamente para o cliente **escrever** a mensagem — a conversa
  não trava.

O conteúdo transcrito é tratado com o mesmo cuidado de segurança do texto digitado (entra blindado, não
como instrução ao modelo). Configuração em
[Transcrição de áudio](../getting-started/configuracao.md#transcricao-de-audio).

## Aviso de imóvel novo

É a única mensagem que a Mora manda sem ninguém ter escrito antes. Ela sai quando um imóvel **entra**
no catálogo e bate com o que o cliente pediu — mesma operação, dentro do teto de preço, quartos
suficientes — e a mensagem sempre diz **por quê** ("no Brooklin, que era o bairro que você pediu, e
R$ 100 mil abaixo do seu teto").

Limites, para não virar spam: no mínimo 3 dias sem conversa, no máximo um aviso a cada 7 dias, nunca o
mesmo imóvel duas vezes, e nada para quem já está com um corretor. Uma recarga do catálogo inteiro não
avisa ninguém.

Para sair, basta responder **"não quero mais receber avisos"** — a Mora desliga na hora e confirma, sem
tentar convencer. O corretor também desliga pelo painel, na ficha do lead (aba **Atendimento**), para
quando o pedido chega por telefone. Follow-up e respostas às mensagens do cliente continuam normais.

## Exemplos de mensagens

- "Quero um apartamento de 2 quartos em Pinheiros até 700 mil."
- "Tem casa para alugar até 3 mil na zona sul?"
- "Quero investir, qual a rentabilidade?"
- "Gostaria de agendar uma visita."
- "Quero falar com um corretor."

## Comportamento esperado

Respostas curtas (até 3 frases), uma pergunta por vez, sem inventar imóveis, preços ou
disponibilidade. Assuntos fora do mercado imobiliário são recusados com educação, e a conversa é
reconduzida.

## Reiniciar ou encerrar

- **No site**, a sessão é anônima e vinculada a um `session_id`; recarregar ou limpar o armazenamento
  do navegador inicia uma nova conversa.
- **No Telegram**, a conversa segue o histórico do chat.

## Respostas incorretas

Se a resposta não fizer sentido ou o cliente insistir fora do escopo, a Mora oferece o contato de um
corretor humano. Falhas técnicas encaminham automaticamente ao corretor.

## Privacidade e uso responsável

A Mora é uma assistente de demonstração; o conteúdo gerado deve ser conferido por um corretor antes de
qualquer compromisso comercial. O texto do cliente é tratado como dado, nunca como instrução ao modelo
(ver [Segurança](../quality/seguranca.md)).
