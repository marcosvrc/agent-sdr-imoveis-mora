---
title: "Roteiro de demonstração"
description: A sequência que mostra a Mora conversando, respondendo política com RAG, reconhecendo um cliente do CRM, pedindo visita — e o acervo mudando de lado a lado.
---

# Roteiro de demonstração

Vinte minutos, cinco momentos. Cada um mostra uma capacidade diferente e termina com algo visível
numa tela — não com uma afirmação sobre o que o sistema faz.

Se houver só quinze minutos, corte o momento 5 e faça a versão curta do 4 (sem remarcar). O que não
se corta é o 1 e o 4: um mostra o agente, o outro mostra por que ele não decide sozinho.

A ordem importa: cada momento usa o estado que o anterior deixou. Pular um quebra o seguinte.

!!! warning "Tudo aqui é ficção"
    A Vértice Imóveis não existe. Imóveis, clientes, conversas e documentos institucionais são
    sintéticos — ver [Licença e dados](../project/licenca.md). Ao demonstrar, vale dizer isso uma
    vez no começo: quem assiste não tem como saber, e a massa é convincente o bastante para
    confundir.

## Antes de começar

```bash
make                   # a ajuda, com a ordem completa — é o alvo padrão
make check-env         # confere o local/.env antes de subir nada
make local-ollama      # sobe o compose com o Ollama, em primeiro plano
```

Em outro terminal, com o compose no ar:

```bash
make preparar          # schema da Mora + banco e schema do CRM + massa sintética, nesta ordem
make crm-token         # emite o CRM_API_TOKEN → cole no local/.env
cd local && docker compose up -d crm-mcp agent && cd ..

make ollama-pull       # baixa o bge-m3 (demora, uma vez só)
make seed              # acervo: vem do CRM quando ele está configurado
make docs-kb           # documentos institucionais
```

`CRM_MCP_TOKEN` precisa estar em `local/.env` **antes** de subir o compose — o servidor MCP recusa
iniciar sem ele. O `CRM_API_TOKEN` só existe depois que o CRM está no ar, e é por isso que há duas
idas ao arquivo. O `make check-env` reclama se só um dos dois estiver lá.

Confira antes de chamar alguém: `make check-env` não pode ter nenhum `✗`, e a Visão geral do
painel da Mora tem de mostrar imóveis no índice. Um roteiro que quebra no primeiro passo custa mais
credibilidade do que a demonstração inteira devolve.

Deixe abertas três abas — o site (`:5173`), o painel da Mora (`:5174`) e o CRM (`:3000`) — e um
terminal com `cd local && docker compose logs -f agent`, que é onde as decisões de roteamento
aparecem enquanto a conversa acontece.

## 1. A conversa (4 min)

No site, abra o chat e conduza uma qualificação normal:

> "oi, procuro um apartamento de dois quartos para alugar em Pinheiros, até 3.500"

**O que mostrar:** a Mora extrai o cartão de qualificação da conversa em vez de aplicar um
formulário; os cards de imóvel aparecem no chat; o painel da Mora atualiza em tempo real na aba ao
lado.

**O que dizer:** a decisão de rota é do grafo, não do modelo — há um supervisor que escolhe o
especialista, e isso é o que torna o comportamento reprodutível.

## 2. A pergunta que o catálogo não responde (3 min)

Ainda no chat:

> "vocês cobram taxa de visita?"

**O que mostrar:** a resposta cita a fonte (o documento institucional), e não sai do que está
escrito. Em seguida pergunte algo que o corpus **não** cobre:

> "vocês fazem seguro de automóvel?"

A Mora diz que vai confirmar e oferece o corretor, em vez de inventar.

**O que dizer:** é o piso de similaridade. Busca vetorial sempre devolve o vizinho mais próximo,
mesmo quando ele está longe; sem o piso, a pergunta sobre seguro traria o trecho de taxas e o
agente responderia com confiança sobre o assunto errado. Errar para "não sei" custa uma pergunta;
errar para o outro lado custa uma política inventada que o corretor vai ter que desmentir.

## 3. O cliente que o CRM já conhece (4 min)

No CRM, abra um cliente qualquer da massa e anote o e-mail dele e as preferências que o corretor
registrou. Depois, no site, inicie uma conversa nova e informe **esse** e-mail.

**O que mostrar:** a Mora não pergunta de novo a cidade, o orçamento e os quartos — ela já chega
sabendo, e segue a partir dali.

**O que dizer:** é o ponto da integração inteira. O agente bebe da fonte que a imobiliária já tem,
em vez de recomeçar do zero. E o que o cliente disser agora vence o registro: só campo vazio é
preenchido, então quem mudou de ideia não é conduzido pela intenção velha.

## 4. Reservar não é agendar (4 min)

Peça uma visita e escolha um horário.

**O que mostrar, nas duas telas:** a Mora diz ao cliente que o horário está **reservado** e que o
corretor confirma. No CRM, a visita aparece como **solicitada**, e a oportunidade **não** foi para
`visit_scheduled`. Mostre também os interesses registrados: os imóveis que foram apresentados
estão lá, prontos para o corretor ler antes de ligar.

**O que dizer:** quem aparece no imóvel no sábado é uma pessoa. Um agente que grava "visita
marcada" cria um cliente esperando na porta, com um corretor que nunca soube. As duas metades são
verdadeiras ao mesmo tempo — o horário está reservado e a visita não está confirmada — e é a única
combinação em que ninguém é enganado.

**Se sobrar um minuto aqui**, confirme a visita no CRM e depois clique em **Remarcar**, escolhendo
outro horário do mesmo imóvel. A visita antiga fica cancelada apontando para a nova, e a lista diz
"remarcada" em vez de "motivo". Antes isso era cancelar e pedir de novo: dois eventos soltos no
histórico, e uma visita cancelada indistinguível de cliente perdido.

!!! tip "De onde vêm os horários"
    Se a agenda estiver vazia, abra **Imóveis → Agenda** e crie um. É a mesma tela do momento 5, e
    ela existe justamente para a demonstração não depender do `make seed`.

## 5. O acervo muda, e a Mora acompanha (5 min)

É o arco completo da integração, e o único momento em que as duas pontas aparecem na mesma frase.

**Primeiro, cadastre.** No CRM, **Imóveis → Novo imóvel**: um código novo, bairro, aluguel e —
importante — deixe **condomínio em branco**. Salve. Na tela, o imóvel aparece com **"total
incompleto"** em vez de um número menor que a conta real, e diz o que falta (condomínio e outros
custos, se você deixou os dois vazios).

**Depois, abra a agenda dele** e crie um horário para amanhã.

**Agora mostre a Mora encontrando.** No site, peça um imóvel naquele bairro. Ele está lá, com
horário disponível para visita.

**Por fim, tire do catálogo.** De volta ao CRM, no cartão do imóvel: **Mudar situação → Reservado**,
com o motivo. Espere o ciclo de reindexação (o intervalo está em **Configurações → Operação**, no
painel da Mora) e peça de novo, no site.

**O que mostrar:** a Mora parou de oferecer. Ninguém rodou comando nenhum.

**O que dizer:** três coisas, nesta ordem.

Campo de custo em branco significa **desconhecido**, nunca zero — é o que evita a surpresa do
cliente no dia da assinatura, e é uma decisão de produto, não um detalhe de formulário.

`reserved` é a proposta aceita, antes da assinatura, e **volta** para disponível se a proposta cair.
Situação que só anda para a frente faz o acervo minguar sozinho.

E o índice do agente **não tem campo de situação**: imóvel indisponível não chega nele, some pela
purga da reindexação. Não é sincronização de status — é a fonte deixando de listar, e o índice
obedecendo. Se alguém perguntar o que acontece quando há visita confirmada, mostre: o CRM **recusa**
tirar o imóvel do catálogo. Tirá-lo por baixo mandaria o corretor a um endereço para mostrar o que
não está mais à venda.

## Se sobrar tempo

- **Governança de IA** no painel da Mora: custo por modelo e troca de modelo por nível, sem deploy.
  Em **Configurações → Modelos**, o ícone ao lado do campo abre a comparação: preço de entrada e
  saída, latência **medida neste ambiente** e quanto o uso real dos últimos 30 dias teria custado com
  cada modelo. Vale dizer que janela de contexto não aparece ali de propósito — o projeto não guarda
  esse dado, e número inventado numa tela de escolha vira o motivo de escolher errado.
- **Saúde do sistema**: além de "está lento?", ela responde "por quê" — espera por canal e por
  estágio, e quais nós do grafo aparecem nos 5% de turnos mais lentos. Diga que isso é **presença**,
  não duração: o turno grava por quais nós passou, não quanto tempo levou em cada um, então o que
  sai dali é suspeito e não culpado.
- **Auditoria**: a trilha do que o agente fez, com o motivo de cada decisão.
- **Desligue o CRM** (comente `CRM_MCP_TOKEN` e reinicie o agente) e refaça o momento 1. A Mora
  atende igual. É a porta fazendo o trabalho dela, e talvez seja a coisa mais difícil de mostrar e
  a mais importante de dizer: a integração degrada, não quebra.

## O que NÃO prometer

Duas ressalvas que é melhor dizer antes de alguém perguntar:

- **A qualidade do RAG é medida, mas o número não vem de graça.** Existe uma suíte própria em
  `services/agent/evals/`, com 57 perguntas institucionais em `datasets/rag.jsonl` — escritas do
  jeito que o cliente escreveria, sem repetir o cabeçalho do documento — e métricas de recall@3,
  acerto no topo, abstenção e separação entre o menor score de acerto e o maior score de engano.
  O que roda no CI é `make eval-fake`, com LLM falso e embedder de trigramas: prova o encanamento e
  **não diz nada sobre qualidade**. O número honesto sai de `make eval-rag`, com o `bge-m3` de
  verdade, na máquina de quem avalia. Se perguntarem pela fusão léxica: está implementada,
  desligada por padrão (`SDR_RAG_LEXICO`) e o A/B disponível piorou o recall, de 31,9% para 29,8%.
- **Nada disso está implantado.** Não existe ambiente no ar, nem endereço público: a entrega roda
  inteira na máquina de quem avalia, por `docker compose`. Houve um desenho para nuvem, com stacks
  CDK, e ele foi removido do repositório — o que está documentado é o que dá para levantar e ver
  funcionando aqui.
