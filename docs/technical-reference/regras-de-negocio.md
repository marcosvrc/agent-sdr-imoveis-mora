---
title: Regras de negócio
description: O que o agente e o painel decidem, com os valores exatos — a referência para escrever testes e entender o que o sistema faz.
---

# Regras de negócio

Este documento descreve **o que o sistema decide**, não como ele é construído. Cada regra vem com o
valor exato e o arquivo onde ela vive, para que dê para conferir a afirmação e escrever um teste em
cima dela.

!!! info "Como ler"
    - **Regra** é o enunciado verificável. Onde há número, o número é o do código, não uma
      aproximação.
    - **Onde** aponta o arquivo que decide. Se o código e este documento discordarem, **o código
      está certo e este documento está velho** — corrija-o.
    - A seção final, [Divergências conhecidas](#17-divergencias-conhecidas), lista pontos onde o
      comportamento surpreende. São candidatos naturais a teste.

---

## 1. Vocabulário

Quatro entidades são confundidas com frequência, e a diferença entre elas é regra de negócio:

| Termo | O que é | Regra |
| --- | --- | --- |
| **Cliente** | A pessoa | Só existe quando informa **telefone ou e-mail**. Sem contato, não há cliente — só lead. |
| **Lead / oportunidade** | Uma intenção, um ciclo de atendimento | A mesma pessoa pode ter várias. Mudar de intenção depois de fechar um ciclo abre outra. |
| **Interesse** | Vínculo lead ↔ imóvel | Fraco e N:N: um imóvel tem vários interessados; um lead se interessa por vários imóveis. |
| **Visita** | Compromisso datado | É a forma forte do interesse; exclusiva por horário. |

**Mora** é a agente; **Vértice Imóveis** é a imobiliária. O corretor é humano e aparece no sistema
como cadastro com regiões e carga.

---

## 2. Ciclo de vida do lead

### 2.1 Os sete estágios

`novo` · `qualificando` · `qualificado` · `agendado` · `handoff` · `inativo` · `frio`
(`shared/sdr_shared/models/lead.py`)

### 2.2 Transições — quem muda o quê

| De | Para | Quando | Onde |
| --- | --- | --- | --- |
| `novo` | `qualificando` | a intenção deixa de ser indefinida | `nodes/qualificador.py` |
| `novo`/`qualificando` | `qualificado` | o cartão fica **completo** e o consultor apresenta imóveis | `nodes/consultor.py` |
| qualquer | `agendado` | visita confirmada | `nodes/agendador.py` |
| qualquer | `handoff` | cliente pede humano, corretor assume, falha do agente ou orçamento bloqueado | `nodes/handoff.py`, `handler.py`, `routers/handoff.py` |
| qualquer | `inativo` | follow-up enviado e **ainda há** tentativas | `nodes/followup.py` |
| qualquer | `frio` | follow-up enviado e era a **última** tentativa | `nodes/followup.py` |
| `handoff` | `qualificado` ou `qualificando` | corretor devolve à Mora — `qualificado` se o cartão estiver completo | `routers/handoff.py` |

**Regra que surpreende:** devolver a conversa **não devolve o lead**. O `corretor_id` continua com
quem assumiu; só o estágio volta.

### 2.3 Encerramento e sucessão

Um lead nunca é apagado. Ao mudar de intenção **depois** de um ciclo fechado, o lead antigo recebe
`encerrado_em` e `sucessora_id`, e uma nova oportunidade nasce em `qualificando`.

**Condições para abrir a sucessora** — todas precisam valer (`shared/sdr_shared/db/clientes.py`):

1. a nova intenção não é `indefinida`;
2. é diferente da atual;
3. a atual **não** era `indefinida` (primeira definição não é mudança);
4. o estágio está em `{agendado, handoff, inativo, frio}` — mudar de ideia durante a qualificação é
   o cliente se corrigindo, e só ajusta o cartão;
5. o lead ainda está ativo.

A sucessora **herda** cliente, nome, telefone, e-mail e corretor, e **recomeça** o que a pessoa
procura. Os canais do lead passam a entregar na oportunidade nova.

---

## 3. Qualificação

### 3.1 O cartão e os campos obrigatórios

O cartão é a fonte de verdade da qualificação (`shared/sdr_shared/models/lead.py`).

| Intenção | Campos obrigatórios | Quantos |
| --- | --- | --- |
| compra, aluguel **e indefinida** | `intencao`, `regiao`, `preco_max`, `quartos`, `urgencia` | 5 |
| investimento | `intencao`, `perfil_investidor`, `ticket`, `retorno_esperado` | 4 |

- `completo()` = nenhum obrigatório faltando. **Contato não entra nessa conta**: um cartão pode
  estar completo sem telefone nem e-mail.
- `tem_contato()` = tem telefone **ou** e-mail. **Nome não conta.**
- A ordem das perguntas é a ordem das tuplas acima, uma por vez.

### 3.2 Extração — o que ela pode e não pode fazer

A extração roda no modelo barato (roteamento) com saída estruturada, e é **conservadora por
projeto** (`nodes/qualificador.py`):

- só grava campo cujo valor extraído não seja `None`, `[]`, `False`, `indefinida` ou `0`;
- **nunca apaga nem zera** um campo já preenchido;
- `pediu_visita` nunca volta para `False` pela extração;
- falha na extração devolve o cartão **inalterado** — o turno continua.

**Quem decide bairro e região é o catálogo `geo`, não o modelo.** São **18 bairros** em 5 regiões
(zona_sul 5, zona_oeste 4, zona_norte 3, zona_leste 3, centro 3). Se o local resolver como fora de
cobertura, `bairros` e `regiao` são **zerados**.

### 3.3 Captura de contato

| Regra | Valor |
| --- | --- |
| Nome | cortado em 80 caracteres |
| Telefone | só dígitos, aceito **somente com 10 a 13 dígitos**; fora disso é descartado |
| E-mail | minúsculo, cortado em 120 caracteres |
| Só preenche o que está vazio | o já informado nunca é sobrescrito |
| Auditoria | registra **quais campos** foram capturados, nunca os valores |

**Quando a Mora pede contato** (`nodes/qualificador.py`):

- canal **≠ web** → nunca pede (no Telegram já se tem o identificador);
- canal web e sem nome → pede **só o primeiro nome**, nunca junto com outro dado;
- canal web, com nome, **sem contato e com cartão completo** → pede **um** contato, de preferência
  telefone, ao apresentar imóveis ou agendar. Não insiste.

### 3.4 Roteamento — a ordem importa

O supervisor decide por regra determinística; o modelo só entra no último caso
(`nodes/supervisor.py`). **A primeira condição que casar vence:**

| # | Condição | Destino |
| --- | --- | --- |
| 0 | já há resposta no turno, ou `saltos > 1` | encerra |
| 1 | canal `sistema` | resumidor |
| 2 | tipo `followup` | follow-up |
| 3 | tipo `reativacao` | reativador |
| 4 | pede para sair dos avisos | reativador (**antes do porteiro de escopo**) |
| 5 | fora de escopo **e** não pede humano | recusa |
| 6 | pede humano, ou já está em `handoff` | handoff |
| 7 | escolheu horário (botão `slot:` ou texto após oferta) | agendador |
| 8 | pede visita, ou `pediu_visita` no cartão | agendador |
| 9 | pede outras opções | consultor |
| 10 | cartão completo e nada sugerido ainda | consultor |
| 11 | cartão incompleto | qualificador |
| 12 | resto | **modelo decide** entre qualificador, consultor, agendador e handoff |

Duas precedências que são decisão de negócio:

- **Opt-out vence o porteiro de escopo.** "Não quero mais nada" seria lido como fora de assunto e
  viraria recusa; quem pede para sair de uma lista sai na primeira vez que pede.
- **Pedir humano vence a recusa.** É legítimo em qualquer contexto, inclusive fora de escopo.

---

## 4. Score e temperatura

Calculado **sem IA**, a cada turno (`services/agent/src/agent/scoring.py`).

| Critério | Pontos |
| --- | --- |
| Intenção definida | +15 |
| Tem região | +10 |
| Tem `preco_max` ou `ticket` | +15 |
| Tem `quartos` ou `perfil_investidor` | +10 |
| Urgência `imediata` | +25 |
| Urgência `3_meses` | +15 |
| Urgência `6_meses` | +8 |
| Pediu visita | +15 |
| Imóveis abertos no site | +3 cada, **teto +9** |
| Respondeu em até 5 minutos | +5 |
| **Cada follow-up enviado** | **−10** |

Resultado limitado a 0–100.

| Temperatura | Faixa |
| --- | --- |
| quente | ≥ 60 |
| morno | 30–59 |
| frio | 0–29 |

- `respondeu_rapido` mede o **cliente voltar** em até 5 minutos, não a velocidade do agente. É
  medido **antes** de carimbar a atividade.
- Turnos iniciados pela Mora (follow-up, reativação) **nunca** pontuam por rapidez.
- Não pontuam: `preco_min`, `bairros`, `tipo_imovel`, `retorno_esperado`, dados de contato, estágio.

---

## 5. Busca de imóveis

### 5.1 Filtros aplicados sempre

| Regra | Valor |
| --- | --- |
| Operação | `aluguel` se a intenção é aluguel; **`venda` para compra e investimento** |
| Teto de preço | `preco_max` ou `ticket`, com **tolerância de +15%** |
| Quartos | filtro de **mínimo** (`>=`), não exato |
| Resultados buscados | 6 (o consultor pede 6, a função tem padrão 5) |
| Imóveis apresentados | **no máximo 3** |

### 5.2 A cascata — e o que a Mora pode afirmar

A busca desce níveis até achar algo. **O nível é a única autorização para falar de disponibilidade**
(`tools/buscar_imoveis.py`, `nodes/consultor.py`):

| Nível | Significa | O que a Mora deve dizer |
| --- | --- | --- |
| `bairro` | achou no bairro pedido | cita o bairro de cada um; **nunca** diz que não há opções |
| `vizinhos` | não há no bairro pedido; estes são de bairros vizinhos da mesma região | diz isso **antes** de apresentar; proibido inventar motivo (reserva, sistema) ou sugerir que ficam no bairro pedido |
| `regiao` | não há no bairro; estes são de outros bairros da região | explícito — salvo quando o cliente pediu a região, e aí é mensagem positiva |
| `cidade` | não há nem na região | diz com honestidade e pergunta se a região é flexível |
| `fora_de_cobertura` | a cidade não é atendida | uma frase dizendo que atendemos São Paulo capital; apresenta o mais próximo; **não inventa que há imóveis lá** |
| `vazio` | nada em lugar nenhum | **único caso** em que pode afirmar indisponibilidade ampla; propõe flexibilizar **um** critério |

**Vizinho** = outro bairro da mesma região; não é distância geográfica.

**Regra-mestra do prompt:** a lista é o resultado de *uma* busca com filtros, não o estoque inteiro.
A Mora nunca conclui indisponibilidade a partir do que não apareceu.

### 5.3 Alternativa no bairro

Quando não há nada no perfil pedido **dentro do bairro pedido**, o sistema procura o que existe ali
**fora do perfil** — "de dois quartos não tenho aí, mas tenho este de um".

- Só existe quando houve bairro pedido.
- Duas tentativas, parando na primeira com resultado: relaxa **quartos**, depois relaxa **preço**.
- Busca 3, o prompt recebe **as 2 primeiras**.

### 5.4 O que impede repetir

| Regra | Efeito |
| --- | --- |
| Imóvel `descartado` | **nunca** reaparece, em nenhuma sessão |
| Imóvel já `sugerido` | não repete, mesmo em sessão futura |
| Esgotou a novidade | repete as 3 melhores — mas nunca um descartado |

A memória entre sessões é a tabela `interesses`; o estado do grafo só conhece a conversa atual.

---

## 6. Interesses

Situações: `sugerido` · `interessado` · `descartado` · `visita_marcada`. Origens: `agente`, `site`,
`corretor`. Um registro por par lead+imóvel (`InteresseRepository`).

### 6.1 A regra de transição

> **`sugerido` nunca sobrescreve nada.**

Mostrar de novo um imóvel já descartado não apaga o descarte; reapresentar um com visita marcada não
rebaixa a visita. **Qualquer outra situação sobrescreve** a anterior — inclusive `descartado` sobre
`visita_marcada`, que é o caso real de quem desmarcou.

### 6.2 Quem cria o quê

| Situação | Quem | Quando |
| --- | --- | --- |
| `sugerido` | agente | ao apresentar imóveis, e ao avisar de imóvel novo |
| `interessado` | site | clique em "falar sobre este imóvel" — interesse **declarado** |
| `interessado` / `descartado` / `visita_marcada` | corretor | pelo painel |
| `visita_marcada` | agente | ao gravar a visita |

Passar os olhos numa ficha **não** é interesse: isso fica só em `imoveis_visualizados` no cartão.

### 6.3 Visibilidade

- A ficha do lead mostra **todos** os interesses, inclusive descartados.
- A lista de interessados de um imóvel **esconde os descartados** e os leads encerrados: a pergunta
  do corretor é "com quem eu falo sobre este imóvel", não "quem já disse não".
- Pela API, marcar `sugerido` é recusado (422). Para desfazer um descarte, marque `interessado`.

---

## 7. Visitas

| Regra | Valor |
| --- | --- |
| Horários | **10h, 14h e 16h** (horário de Brasília) |
| Dias | 5 dias úteis à frente; **fins de semana são pulados** |
| Antecedência | a grade começa **amanhã** — nunca hoje |
| Slots gerados / oferecidos | até 15 / **no máximo 8** |
| Duração | **60 minutos** |
| Colisão | horário já confirmado é removido da grade |

### 7.1 Como o horário é escolhido

Dois caminhos: **botão** (`slot:<iso>`, sem ambiguidade) ou **texto livre**, e neste o sistema
interpreta ordinais ("o primeiro", "o último"), hora ("14h", "às 3"), dia da semana, "amanhã" e data
`dd/mm`.

> **Só confirma se restar exatamente um candidato e o cliente tiver dito ao menos dia, hora ou
> data.** Qualquer ambiguidade reoferece em vez de adivinhar.

Se o cliente pedir hora que não existe na grade, a Mora explica em meia frase e reoferece — sem
inventar disponibilidade.

### 7.2 O que uma visita confirmada produz

1. revalidação da colisão (se ocupou no meio do caminho, reoferece dizendo isso sem culpar ninguém);
2. visita gravada com id determinístico — reclicar o mesmo horário **não** duplica;
3. interesse do imóvel vira `visita_marcada`;
4. estágio do lead vira `agendado` e `pediu_visita` fica `true`;
5. evento no Google Agenda do corretor, **se** ele tiver conectado;
6. auditoria e notificação ao corretor.

**O Google Agenda nunca derruba a visita.** Sem integração, com token expirado ou com erro, a visita
continua marcada e aparece no painel — só não há evento externo. Corretor sem agenda conectada usa a
grade interna.

### 7.3 Escolha do corretor

Quem atende é escolhido por **região e carga** (`CorretorRepository.escolher`):

1. corretores **ativos** que atendem a região — **quem não tem região declarada atende todas**;
2. se ninguém, os sem região declarada;
3. se ainda ninguém, qualquer ativo (a regra nunca falha por região);
4. entre os aptos, **menor carga**; empate resolve por ordem alfabética.

**Carga** = leads em `handoff` + visitas futuras. **Carteira** (o que se move numa desativação) é
mais ampla: todos os leads abertos + visitas futuras.

---

## 8. Handoff

| Ação | O que muda |
| --- | --- |
| **Assumir** | estágio vira `handoff`; corretor definido por: body → o já vinculado (se existir no cadastro) → roteamento por região → **fila da equipe**; visitas futuras acompanham; **follow-ups são cancelados** |
| **Responder** | não muda nada no lead; envia por **todos** os canais dele, sem passar pelo agente; registra a mensagem como `corretor` |
| **Devolver** | volta para `qualificado` (cartão completo) ou `qualificando`. O corretor **continua** vinculado |

**Regra explícita:** o usuário logado é um **ator de auditoria**, nunca vira o `corretor_id` do
lead. Sem corretor cadastrado, o lead vai para a fila da equipe (`corretor_id` nulo) — antes disso
gravava um id que a tela de corretores não conhecia.

Enquanto o lead está em `handoff`, a Mora **não responde**. A mensagem do cliente é registrada, o
follow-up é cancelado e o corretor recebe um aviso — **no máximo um a cada 15 minutos por lead**.

---

## 9. Corretores

| Regra | Detalhe |
| --- | --- |
| Nome | mínimo 2 caracteres; nome duplicado é recusado (409) |
| Regiões | **nenhuma selecionada = atende todas** |
| Inativo | não recebe handoff nem visita |
| Foto | quadrada, reduzida para 256 px no navegador; recusada acima de 300 KB |

### 9.1 Desativação — a carteira nunca fica órfã

Desativar **não apaga o cadastro**: ele fica inativo, o histórico é preservado e o toggle reativa.

O destino da carteira é **obrigatório** quando há carteira aberta:

| Destino | Efeito |
| --- | --- |
| `equipe` (ou vazio) | leads e visitas ficam sem dono, na fila |
| `auto` | escolhe pela região do corretor que sai e menor carga; se não houver ninguém, cai na fila |
| um corretor | precisa existir, estar **ativo** e não ser o próprio (422 em cada caso) |

Numa única transação movem-se: leads abertos, visitas futuras e **notificações não lidas**. As já
lidas ficam com quem leu — são histórico.

**Dois 409:**

- carteira aberta **sem destino** — escolher em silêncio esconderia a decisão de quem chamou;
- `remover_cadastro=true` **com carteira aberta** — apagar existe para cadastro criado por engano,
  não para desligar quem já atendeu.

Cada lead transferido gera uma notificação ao novo dono.

---

## 10. Follow-up

Cadência padrão (`shared/sdr_shared/followup.py`), configurável no painel:

| Tentativa | Base | quente (×0,25) | morno (×1,0) | frio (×2,0) |
| --- | --- | --- | --- | --- |
| 1ª | 2 h | 30 min | 2 h | 4 h |
| 2ª | 24 h | 6 h | 24 h | 48 h |
| 3ª | 72 h | 18 h | 72 h | 6 dias |

- **O número de tentativas é o tamanho da lista** — não existe um "3" escondido. Máximo aceito pelo
  painel: 10 tentativas, cada uma ≥ 5 minutos.
- **Janela civilizada: 08:00–20:00**, fuso de São Paulo. Fora dela o envio é **adiado**, nunca
  cancelado — "adiar é melhor que calar". Opcionalmente só dias úteis.
- Piso absoluto de 5 minutos entre o cálculo e o envio.
- Estágio após enviar: `frio` se era a última tentativa, `inativo` caso contrário.
- Cada follow-up enviado **desconta 10 pontos** do score.

**Cancelado quando:** o lead chega a `handoff`, `frio` ou `agendado`; as tentativas acabam; o
follow-up é desligado no painel; ou o cliente escreve estando em handoff. **Reagendado a cada turno
bem-sucedido** — conversa nova empurra o follow-up para frente.

No perfil local há **no máximo um follow-up pendente por lead** (chave primária por lead).

---

## 11. Reativação proativa

Quando um imóvel **entra** na base, a Mora avisa quem procurava algo assim e sumiu
([ADR-0013](../adr/0013-reativacao-proativa-de-leads-adormecidos.md)).

### 11.1 Pontuação

**Eliminatórios** — qualquer um zera e explica o porquê:

| Eliminatório | Regra |
| --- | --- |
| Operação | compra e investimento procuram `venda`; aluguel procura `aluguel` |
| Intenção indefinida | sem intenção não há o que casar |
| Acima do teto | `preco > preco_max` |
| Abaixo do piso | `preco < preco_min` |
| Quartos | `im.quartos < cartao.quartos` |
| Tipo | tipo pedido diferente do imóvel |

**Pontos** (teto 100, mínimo para avisar: **60**):

| Item | Pontos |
| --- | --- |
| Base (passou nos eliminatórios) | +30 |
| Bairro citado pelo lead | +40 |
| …ou região certa | +25 |
| …ou fora da área citada | +5 |
| Folga ≥ 10% do teto de preço | +25 |
| Folga menor que 10% | +10 |
| Tipo bate | +10 |
| Urgência imediata | +10 |
| Selo de investimento, para investidor | +15 |

Base sozinha (30) não avisa. Bairro exato (30+40 = 70) avisa. Só região (55) não avisa sem mais nada.

**Cada ponto gera um motivo em português** — é esse texto que vira a primeira frase da mensagem.
A decisão por pontuação determinística em vez de embedding foi exatamente essa: "R$ 20 mil abaixo do
teto que você me deu" é verificável; "similaridade 0,87" não é.

### 11.2 Quem não recebe, e por quê

Avaliado nesta ordem; devolve o **motivo**, não um booleano — é o que permite a tela de simulação
mostrar quem ficou de fora:

1. oportunidade encerrada;
2. pediu para não receber avisos;
3. já está com um corretor;
4. sem canal de contato;
5. já conhece o imóvel (descartou / tem visita / já foi apresentado);
6. recebeu aviso nos **últimos 7 dias**;
7. conversou há **menos de 3 dias** — a Mora fala com ele na conversa.

### 11.3 Limites de disparo

| Limite | Valor |
| --- | --- |
| Silêncio mínimo | 3 dias |
| Cadência por lead | 1 aviso a cada 7 dias |
| Avisos por imóvel | 20 |
| Leads varridos por rodada | 500 |
| Imóveis novos por ingestão | acima de **5**, nada é anunciado (é carga de catálogo, não novidade) |

Canal: **Telegram**, o único assíncrono que resta. Web fica de fora de propósito — o widget só
existe com a aba aberta. Lead sem conversa aberta não recebe: quem fala primeiro com quem nunca escreveu é o corretor.

### 11.4 Saída

O opt-out desliga em dois lugares: **na conversa** ("não quero mais receber avisos" — resposta fixa,
sem modelo, para a Mora não tentar convencer ninguém a ficar) e **no painel**, na ficha do lead.

### 11.5 Medição

O funil (`GET /dashboard/reativacao`, janela padrão 30 dias) é reconstruído da auditoria: avisos →
**responderam em até 48 h** (mais tarde é conversa nova) → viraram visita → pediram para sair. As
taxas somem quando não houve aviso no período: 0% sobre zero aviso é uma afirmação falsa.

---

## 12. Guardrails

### 12.1 Escopo — o porteiro

Regex determinística **antes** de gastar token. Ordem de avaliação:

| # | Verificação | Limite |
| --- | --- | --- |
| 1 | Texto gigante | **> 1200 caracteres** |
| 2 | Injeção de prompt | vence tudo, inclusive pedido legítimo junto |
| 3 | Fora do domínio sempre | bitcoin, day trade, eleição, remédio, poema — recusado mesmo citando imóvel |
| 4 | Domínio ou conversa | **passa**, mesmo com ruído junto |
| 5 | Fora do domínio (fraco) | perde para o domínio: "receita" também é receita de aluguel, "cozinha americana" é atributo |
| 6 | Nada casou | **passa** — na dúvida, atende |

- Homóglifos (cirílico/grego) são dobrados para ASCII antes de julgar. **Dígitos não são dobrados**:
  "2 quartos", "R$ 500 mil" e "apto 101" são vocabulário do domínio.
- Cada categoria tem um texto fixo de resposta, **sem passar pelo modelo**.
- A partir de **3 recusas no mesmo lead**, a Mora para de repetir a negativa e oferece um corretor.

### 12.2 Vazão

| Janela | Limite |
| --- | --- |
| Rajada | **5 mensagens em 10 segundos** |
| Hora | **60 mensagens por hora** |
| Aviso ao cliente | no máximo **1 por minuto** por lead |

Excedeu: o turno é descartado (a conversa não cai), o cliente é avisado uma vez e o evento é
auditado. Turnos iniciados pela Mora não passam pela vazão.

### 12.3 Saída — a última barreira

| Achado | Consequência |
| --- | --- |
| Vazamento de instrução interna | **resposta inteira descartada**, substituída por um texto neutro |
| CPF | mascarado (`[documento omitido]`) e **enviado** |
| Cartão (13–19 dígitos) | mascarado (`[número omitido]`) e enviado |
| **Telefone** | **não é mascarado** — confirmar "anotei o 11 98888-7777" é atendimento normal |

Tanto o texto bruto quanto o limpo são inspecionados: apagar o marcador interno não é o mesmo que
descartar a resposta que o continha.

---

## 13. Governança de LLM

### 13.1 Orçamento

| Limite | Padrão |
| --- | --- |
| Orçamento mensal | **US$ 50** (0 = sem teto) |
| Teto de tokens/dia | **1.000.000** (0 = sem teto) |
| Alerta | **80%** |
| Ação ao estourar | `degradar` |
| Cotação | R$ 5,12 |

O percentual que vale é **o maior** entre o de dólares e o de tokens.

### 13.2 Os três modos

| Modo | Quando | O que muda no atendimento |
| --- | --- | --- |
| `normal` | abaixo do teto, ou ação = `alertar` | nada |
| `degradado` | estourou e ação = `degradar` | conversa e análise passam a usar o **modelo de roteamento** (o barato) até virar o mês |
| `bloqueado` | ação = `bloquear`, **ou** `degradar` acima de **150%** (`TETO_DURO`) | **não chama modelo nenhum**: o lead vai para `handoff` e o cliente recebe "vou chamar {corretor} agora mesmo" |

Com ação = `alertar`, o modo é sempre `normal`, mesmo estourado — só o painel avisa.

### 13.3 Modelos e provedores

- Três níveis: `conversa`, `roteamento`, `analise`. **`analise` sem configuração cai em `conversa`.**
- O painel manda, o `.env` é o piso; campo vazio significa "usa o do ambiente".
- Provedores: `anthropic`, `openai`, `ollama`. O reserva
  ([ADR-0009](../adr/0009-gateway-de-llm-litellm-openrouter-ou-nada.md)) entra quando o primário
  falha, e se for de **outra família** o modelo é trocado pelo equivalente do papel — mandar
  `claude-sonnet-4-5` para a OpenAI voltaria 404.
- **Salvar modelo sem preço cadastrado é recusado (422)**, exceto Ollama: custo zero faria o teto em
  dólar nunca ser atingido.
- Temperatura: **0,0** no roteamento, **0,6** nos demais papéis.

---

## 14. Observabilidade e auditoria

### 14.1 O que a aba Saúde mede

`turnos` grava uma linha por turno com **o tempo que o cliente esperou**.

| `turnos.resultado` | Significa |
| --- | --- |
| `ok` | turno concluído |
| `vazao` | bloqueado pelo limite de mensagens |
| `handoff` | o corretor responde, o agente não |
| `orcamento` | bloqueado pelo teto de LLM |
| `erro` | exceção no grafo; o cliente recebeu o fallback |
| `reativacao` | aviso de imóvel novo |

Também: p50/p95/pior espera, turnos acima de 30 s, profundidade das filas e conexões do banco.
Retenção de **7 dias**, podada uma vez por hora pelo próprio laço do scheduler.

### 14.2 Batimentos e `/health`

Cada worker carimba `batimentos` a cada **30 segundos**, por uma thread daemon — se o processo
morre, a thread morre junto e o carimbo para. Sem carimbo há mais de **120 segundos**, o serviço é
dado como parado.

**`/health` devolve 503** quando o banco não responde **ou** algum worker está calado. Um `/health`
que devolve 200 sempre não é monitoramento, é decoração.

### 14.3 Auditoria

Responde a três perguntas: por que este lead mudou de estágio, quem alterou esta configuração, quem
exportou dado pessoal. **Falhar ao auditar nunca derruba a operação auditada.**

- Chaves contendo `senha`, `password`, `token`, `secret`, `authorization`, `api_key`, `imagem`,
  `foto` ou `embedding` viram `[omitido]`.
- Listas são cortadas em 20 itens, textos em 500 caracteres, profundidade em 4 níveis.
- **Exportar a trilha é ela própria uma ação auditada.**
- Todo `POST/PUT/PATCH/DELETE` da API é registrado automaticamente, com corpo, filtros, duração e
  origem. Exceções deliberadas: notificações (ruído) e calendário (auditado dentro do router).

---

## 15. O painel — o que o corretor pode fazer

| Tela | Ações | Travas |
| --- | --- | --- |
| **Visão geral** | filtrar período (7/14/30/90 dias) | somente leitura; pipeline e ticket **não** seguem o filtro |
| **Leads** | filtrar, ordenar, sincronizar CRM | exporta só `qualificado`, `agendado` e `handoff` |
| **Ficha do lead** | assumir, devolver, responder, trocar corretor, ligar/desligar avisos, gerar briefing, marcar interesse | **responder só em handoff**; seletor lista **apenas corretores ativos**; briefing tem timeout de 90 s e avisa se o worker está parado |
| **Clientes** | buscar, abrir ficha | leitura; quem não deixou contato não aparece aqui |
| **Conversas** | acompanhar ao vivo | leitura; para responder, abrir o lead |
| **Agenda** | ver visitas, exportar para o Google | leitura; marca "fora da grade" e "sem corretor" |
| **Imóveis** | subir/remover/reordenar fotos, ver interessados, simular reativação | **12 fotos** por imóvel; JPEG/PNG/WebP reduzidos a 1280 px; remover foto **é irreversível e pede confirmação**; a simulação **não envia nada** |
| **Corretores** | criar, editar, ativar/desativar, apagar, conectar Google Agenda | desativar **exige destino** da carteira; apagar só com carteira vazia; nenhum token do Google passa pelo painel |
| **Governança** | limites de orçamento, preços por modelo | modelo sem preço é recusado |
| **Auditoria** | filtrar, exportar CSV | mostra os 300 mais recentes; exportar é auditado |
| **Saúde** | ver espera, filas e serviços | leitura; >30 s ruim, >10 s alerta; fila >50 crítica |
| **Configurações** | agente, follow-up, agenda, cobertura, handoff, modelos | **só `followup` e `modelos` valem no próximo turno**; as demais seções são declarativas. Canais é leitura |

**Autenticação:** um token estático (`SDR_PAINEL_TOKEN`) e um ator fixo. No perfil local, sem
token configurado, vale `dev-token`; fora dele, sem segredo nada é aceito. Qualquer 401 devolve o
corretor ao login.

---

## 16. O site público

| Recurso | Regras |
| --- | --- |
| **Catálogo** | 12 por página; filtros por operação, tipo, quartos, suítes, vagas, preço, área, região e bairro; busca com atraso de 350 ms |
| **Ficha** | até 3 parecidos (mesmo bairro e operação); pontos de referência do bairro com a ressalva de que **o endereço exato vem com o corretor** |
| **Favoritos** | ficam **no navegador**, sem cadastro e sem servidor |
| **Vistos recentemente** | até 8 guardados, 4 exibidos, com botão de limpar |
| **Simulação de financiamento** | Tabela Price; entrada padrão 20%, juros padrão 10,49% a.a., prazos de 10 a 30 anos. **Só para imóveis de venda.** Rotulada como estimativa: não é proposta de crédito |
| **Custo mensal** | aluguel = aluguel + condomínio (**IPTU fica de fora**, depende do valor venal); venda = condomínio + IPTU estimado em 0,8% a.a. |
| **Chat** | sessão assinada pelo servidor, válida 12 h; fila de mensagens quando offline; aos 10 s avisa que ainda procura, aos 60 s oferece humano |
| **Rastreamento** | exatamente quatro eventos: `viewed_imovel`, `filtered`, `clicked_telegram`, `opened_chat`. Sem sessão válida, o servidor descarta |
| **Privacidade** | faixa que **não bloqueia** a navegação; base legal é legítimo interesse, e o consentimento acontece quando a pessoa entrega contato no chat |

### 16.1 Dados institucionais e a regra do placeholder

`nome`, `slogan`, `missão` e `descrição` são reais. **CRECI, CNPJ, endereço, telefone, e-mail,
horário e responsável técnico são placeholders.**

O site **não esconde e não finge**: exibe o valor apagado com um selo "EXEMPLO". E, o que mais
importa:

> **Placeholder nunca entra no dado estruturado.** O JSON-LD da organização só publica telefone e
> endereço se forem reais — declarar credencial falsa em formato legível por máquina é outra coisa
> que mostrá-la marcada como exemplo na tela.

Nunca devem ser inventados, nem depois: avaliações de clientes, notas, prêmios, número de imóveis
vendidos, tempo de mercado. Prova social só com origem verificável.

---

## 17. Divergências conhecidas

Pontos onde o comportamento surpreende. São bons candidatos a teste — e alguns são candidatos a
correção.

1. **A vazão é estado de processo.** Com N workers, o limite efetivo é ~N×5 por rajada e ~N×60 por
   hora. Em um processo só (perfil local) o número vale como está escrito.
2. **A taxa de falha da aba Saúde conta como falha tudo que não é `ok`** — inclusive `handoff`,
   `orcamento` e `reativacao`, que são comportamento projetado.
3. **`campos_faltantes()` testa `None`; o score testa "valor verdadeiro".** Com `quartos = 0` o
   cartão fica completo e o critério de quartos vale 0 ponto.
4. **`urgencia = "sem_prazo"` completa o cartão valendo zero ponto** — o lead fica completo e frio.
5. **Ação `alertar` nunca muda o modo**, nem acima de 150%. O teto vira apenas visual.
6. **`TETO_DURO` (150%) só existe para `degradar`.** Com `bloquear`, o bloqueio é em 100%.
7. **Devolver o lead não devolve o corretor** nem reagenda o follow-up cancelado no assumir.
8. **Responder por dois canais registra uma mensagem só**, atribuída ao primeiro canal.
9. **A limpeza da auditoria cobre `dados`, não `detalhe`** — e `detalhe` recebe até 300 caracteres
   do texto do modelo e até 900 de traceback.
10. **A carga do corretor conta visitas futuras sem olhar o status** — uma visita cancelada no
    futuro ainda pesa no roteamento.

---

## 18. Onde conferir

| Assunto | Arquivo |
| --- | --- |
| Cartão, estágios, temperatura | `shared/sdr_shared/models/lead.py` |
| Score | `services/agent/src/agent/scoring.py` |
| Roteamento | `services/agent/src/agent/nodes/supervisor.py` |
| Busca e cascata | `services/agent/src/agent/tools/buscar_imoveis.py`, `shared/sdr_shared/geo.py` |
| Interesses, visitas, imóveis | `shared/sdr_shared/db/repositories.py` |
| Corretores, métricas, reativação (funil) | `shared/sdr_shared/db/painel.py` |
| Cliente e sucessão | `shared/sdr_shared/db/clientes.py` |
| Follow-up | `shared/sdr_shared/followup.py` |
| Reativação (régua) | `shared/sdr_shared/reativacao.py` |
| Guardrails | `services/agent/src/agent/guardrails/` |
| Orçamento e preços | `shared/sdr_shared/db/governanca.py`, `shared/sdr_shared/governanca/precos.py` |
| Observabilidade | `shared/sdr_shared/db/monitoramento.py` |
| Auditoria | `shared/sdr_shared/db/auditoria.py` |
| API | `services/api/src/api/routers/` |
| Painel | `apps/dashboard/src/pages/` |
| Site | `apps/web/src/` |
