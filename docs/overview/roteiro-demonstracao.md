---
title: "Roteiro de demonstração"
description: A sequência que mostra a Mora conversando, respondendo política com RAG, reconhecendo um cliente do CRM e pedindo visita.
---

# Roteiro de demonstração

Quinze minutos, quatro momentos. Cada um mostra uma capacidade diferente e termina com algo
visível numa tela — não com uma afirmação sobre o que o sistema faz.

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

## Se sobrar tempo

- **Governança de IA** no painel da Mora: custo por modelo e troca de modelo por nível, sem deploy.
- **Auditoria**: a trilha do que o agente fez, com o motivo de cada decisão.
- **Desligue o CRM** (comente `CRM_MCP_TOKEN` e reinicie o agente) e refaça o momento 1. A Mora
  atende igual. É a porta fazendo o trabalho dela, e talvez seja a coisa mais difícil de mostrar e
  a mais importante de dizer: a integração degrada, não quebra.

## O que NÃO prometer

Duas ressalvas que é melhor dizer antes de alguém perguntar:

- **A qualidade semântica do RAG não foi medida.** Os testes provam o encanamento — fatiamento,
  busca vetorial, ordenação, piso, caminho do "não sei" —, não que a recuperação escolhe sempre o
  melhor trecho. Isso depende do modelo de embeddings e precisa de avaliação própria.
- **Nada disso está implantado.** A solução foi desenhada para nuvem (`infra/`, com os stacks CDK)
  e a entrega roda local. "Deploy em cloud" é diferencial no enunciado, não requisito — e o desenho
  está escrito mesmo sem o deploy.
