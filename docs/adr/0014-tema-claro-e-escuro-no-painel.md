---
title: "ADR-0014: Tema claro e escuro no painel"
description: Por que o tema exigiu tokenizar a paleta inteira, como "sistema" é resolvido e o que impede o tema escuro de apodrecer.
---

# ADR-0014 — Tema claro e escuro no painel

**Status:** aceito · **Data:** 2026-09 · **Escopo:** `apps/dashboard`

## Contexto

O corretor passa o dia inteiro no painel, boa parte dele à noite. O pedido foi "claro, escuro e algo
bacana"; o levantamento mostrou que o trabalho não estava no seletor, e sim embaixo dele: **234
utilitários de cor fixa espalhados por 28 arquivos** (`bg-slate-100`, `text-slate-400`, `bg-red-50`,
`text-amber-800`…) e a paleta declarada como hex literal no `tailwind.config.js`.

Um tema escuro sobre essa base não é um tema: é uma tela escura com retângulos brancos aparecendo
uma tela de cada vez, conforme alguém abre.

## Decisão

### 1. A paleta vira variável CSS, e o Tailwind aponta para ela

`tailwind.config.js` não guarda mais cor nenhuma — `surface: "var(--surface)"`. Trocar de tema é
redefinir variáveis, sem recarregar a página e sem duplicar cada classe com um prefixo `dark:`.

### 2. Tokens de PAPEL, e tom em trio

`surface` é onde o conteúdo se apoia, `surface-2` é o realce sutil (hover, chip), `line` separa,
`ink`/`ink-soft`/`ink-muted`/`ink-faint` escrevem em quatro níveis. Cada tom semântico vem em trio:

| | `-soft` | `-strong` | `-line` | cheio |
| --- | --- | --- | --- | --- |
| uso | fundo do aviso | texto sobre ele | borda | bolinha, botão |

Trio, e não uma cor só, porque no escuro fundo e texto **não se invertem juntos**: o fundo escurece e
o texto clareia. Um `--bad` sozinho obrigaria cada componente a decidir isso na mão — que é
exatamente como a inconsistência começa.

Texto sobre cor cheia usa `text-canvas`: a cor do fundo da página é clara no tema claro e escura no
escuro, ou seja, sempre o oposto do bloco colorido embaixo dela.

### 3. "Sistema" é resolvido no JavaScript, não no CSS

Dois atributos no `<html>`: `data-tema` guarda a **escolha** (claro | escuro | sistema) e
`data-tema-efetivo` guarda o que está pintado (claro | escuro). O CSS só olha o segundo.

Assim existe **uma única cópia da paleta escura**. A alternativa — um `@media (prefers-color-scheme:
dark)` com o mesmo bloco repetido — significa duas listas de 30 variáveis para alguém atualizar só
uma delas. E o controle consegue mostrar "Sistema" marcado enquanto exibe a lua: são duas informações
diferentes, e as duas importam.

Três opções, não um interruptor de dois estados: quem trocou uma vez para escuro precisa conseguir
voltar para "deixa o computador decidir".

### 4. O tema é aplicado antes da primeira pintura

Um script inline de seis linhas no `index.html` lê o `localStorage` e carimba os atributos antes do
bundle carregar. Em um `useEffect` isso viraria um lampejo branco a cada carregamento para quem usa o
tema escuro. As três linhas duplicadas de `lib/tema.ts` são o preço de rodar antes de tudo.

## Consequências

- **Contraste foi reverificado nos dois temas**, com axe-core em 11 telas: 126 violações no início,
  zero no fim. Três delas eram **anteriores ao tema** e apareceram só porque a varredura passou a
  existir: rótulos de 10px a 3,42:1, `<select>` de filtro sem rótulo acessível em quatro páginas, e a
  transcrição da conversa — caixa com rolagem própria — inalcançável pelo teclado.
- A régua do escuro derrubou dois hábitos: `opacity-60` para indicar corretor inativo (apagava
  inclusive as iniciais brancas do avatar; quem diz "inativo" é o seletor ao lado) e o fundo do
  avatar em `hsl(h 45% 45%)`, que no amarelo dava 4,26:1 com texto branco.
- **O que mantém isto de pé é a regra, não o CSS:** nenhum componente escreve cor literal. No dia em
  que um `bg-slate-100` voltar, ele vira um retângulo branco no escuro — e ninguém percebe até alguém
  abrir aquela tela. Por isso a verificação roda nos dois temas, e não só no claro.

## Alternativas descartadas

- **`dark:` do Tailwind em cada classe** — dobra o tamanho de cada `className`, obriga a lembrar do
  par em todo lugar novo e não resolve os 234 usos avulsos: só os transcreve duas vezes.
- **Terceiro tema (alto contraste ou "noite da marca")** — mais uma paleta para revisar em cada tela,
  a troco de nada que o escuro já não resolva. A porta fica aberta: acrescentar um tema agora é
  escrever um bloco de variáveis.
- **Tema por conta, salvo no servidor** — preferência de aparelho, não de pessoa: o mesmo corretor
  quer claro no monitor do escritório e escuro no notebook à noite. `localStorage` é o lugar certo.
- **Estender ao site público agora** — a vitrine é pré-renderizada para SEO e as páginas precisariam
  nascer com o tema certo antes do JS. Fica para quando houver pedido.
