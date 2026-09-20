---
title: "Decisões do CRM imobiliário"
description: Onde a implementação do CRM diverge da especificação recebida, e por quê.
---

# Decisões do CRM imobiliário

A especificação (`crm-imobiliario-especificacao.md`, seção 15) pede que decisões adicionais fiquem
registradas aqui e que mudanças de escopo, armazenamento ou autorização sejam **destacadas**. Este
arquivo é essa lista. Cada item diz o que o documento pedia, o que foi feito e o que se perde.

## D-01 — O CRM convive com a Mora, não a substitui *(escopo — destacado)*

**Documento:** trata o CRM como produto isolado, com o agente externo integrando por MCP.
**Feito:** o CRM é o registro **comercial** (oportunidade, preferências, interesses, visitas,
encaminhamento) e a Mora publica nele o que descobre na conversa. A Mora continua dona do que é
dela: transcrição, estado do grafo, embeddings, cadência de follow-up e reativação.

O fluxo é **num sentido só** — Mora escreve e lê do CRM por MCP sobre HTTP; nada do CRM escreve no
banco da Mora. É a regra que impede as duas verdades sobre o mesmo lead.

O transporte fechou uma divergência que ficou aberta por um tempo: o documento sempre disse "por
MCP", mas a primeira ponte falava REST, e o servidor MCP existia sem cliente nenhum. Hoje a Mora
entra por `ports/crm.py`, cujo adaptador é um cliente MCP; o stdio continua publicado para um
cliente externo. A porta existe porque MCP é feito para o MODELO escolher a ferramenta, e o grafo
da Mora não delega essa escolha — decisão fica no código, MCP fica no transporte.

**Custo:** existem dois cadastros de lead no ambiente. A alternativa (reapontar a camada de dados da
Mora para o CRM) reescreveria reativação, follow-up, score e busca vetorial, que estão apoiados no
schema atual.

## D-01b — Um acervo só, ligado por `code` *(escopo)*

O CRM sorteava cinquenta imóveis próprios e a Mora indexava outros duzentos: dois acervos
disjuntos descrevendo a mesma imobiliária. Passou despercebido enquanto ninguém cruzou os dois —
e apareceu de uma vez na integração de visita, onde pedir os horários de `SP-0001` ao CRM não
devolvia nada, porque `SP-0001` não existia lá.

O seed do CRM passou a gerar o acervo a partir do mesmo `data/imoveis/imoveis.json`, com `code`
igual ao identificador que a Mora usa. `code` é a chave entre os dois sistemas: nenhum dos lados
precisa adivinhar o identificador interno do outro, e a Mora resolve `SP-0001` para o `property_id`
do CRM por uma busca.

Fotos, região e destaque de investimento continuam só na Mora — são dados de vitrine. O CRM fica
com o registro comercial. O arquivo não é "da Mora": é a massa da imobiliária, que o CRM registra
e a Mora indexa.

As duas fixtures obrigatórias da especificação do CRM deixaram de ser forçadas por índice e
passaram a ser conferidas na geração, com mensagem própria: agora o teste prova que a massa tem o
cenário, em vez de provar que alguém escreveu uma exceção para ele.

## D-02 — Banco separado no mesmo Postgres *(armazenamento — destacado)*

**Documento:** PostgreSQL próprio, em Compose próprio.
**Feito:** banco `crm` no mesmo container Postgres do perfil local, com DSN próprio
(`CRM_DATABASE_DSN`) e schema próprio.

Banco separado — e não um schema dentro do banco `sdr` — porque é o que torna a regra D-01
verificável: uma consulta cruzada precisaria de outra conexão, e isso aparece na revisão. Instância
separada seria mais um container para subir sem nada em troca num ambiente de laboratório.

## D-03 — psycopg + `schema.sql` no lugar de SQLAlchemy + Alembic *(armazenamento — destacado)*

**Documento:** SQLAlchemy + Alembic.
**Feito:** psycopg 3 com SQL escrito à mão e um `schema.sql` idempotente, como no resto do
repositório.

Introduzir um ORM apenas neste serviço traria duas formas de falar com o banco no mesmo projeto, e
Alembic como única ferramenta de migração de um sistema que não tem nenhuma. As garantias que a
especificação realmente cobra — restrições, transação, unicidade parcial, `EXCLUDE` de intervalo —
são todas do Postgres, não do ORM.

**Custo:** sem histórico de migrações versionadas. Enquanto o banco é sintético e recriável, o
`schema.sql` idempotente basta; no dia em que houver dado que não se pode perder, isto precisa virar
migração de verdade.

## D-04 — `autocommit=False` no pool do CRM

O pool da Mora é autocommit. Aqui não pode ser: a seção 7 exige que o registro de idempotência e o
evento de auditoria entrem na **mesma transação** da mutação. Com autocommit, cada `execute` fecharia
a transação sozinho e abriria a janela exata em que a operação existe e o registro de idempotência
não — que é o instante em que o cliente repete a chamada por timeout.

## D-05 — `external_event_id` é único por **canal**

**Documento:** "único por source".
**Feito:** índice único parcial sobre `(channel, external_event_id)`.

A entidade `Interaction` não tem coluna `source` na seção 5; quem cumpre esse papel é o canal. O
mesmo identificador de evento pode existir no Telegram e no chat do site sem ser a mesma mensagem.

## D-06 — Motivo é exigido pela transição, não pelo estágio

**Documento:** tabela da seção 6, que pede motivo na perda e na reabertura.
**Feito:** a exigência está amarrada ao par `(origem, destino)`.

`in_service` aparece duas vezes na tabela com significados opostos: vindo de `new` é o atendimento
começando, vindo de `won`/`lost` é reabertura administrativa. Amarrar a exigência ao destino
obrigaria a inventar um motivo para a primeira mensagem de todo lead. *(Descoberto por um teste do
caminho feliz que falhou.)*

## D-07 — Primeiro corte sem painel React *(escopo — destacado)*

**Documento:** painel P0 (CRM-10).
**Feito:** o primeiro incremento vai do banco ao MCP, para que a Mora converse com o CRM o quanto
antes. O painel fica para o incremento seguinte.

A verificação do que existe hoje é por teste e por chamada REST/MCP, não por tela.

## D-08 — `[início, fim)` nos intervalos de agenda

`EXCLUDE USING gist` com `tstzrange(starts_at, ends_at, '[)')`. Com intervalo fechado nos dois lados,
o banco recusaria 14h–15h e 15h–16h do mesmo corretor como sobreposição — ou seja, recusaria a
agenda cheia de qualquer um.

## D-09 — Reserva do horário é garantida pelo banco

Índice único parcial `visits (slot_id) WHERE status IN ('confirmed', 'completed')`. Deixar isso só na
aplicação perde a corrida entre o `SELECT` e o `UPDATE` de duas transações simultâneas — e o cenário
"duas confirmações no mesmo slot" da seção 14 é exatamente essa corrida.

## D-10 — Servidor MCP pela API de baixo nível do SDK

**Documento:** SDK oficial do MCP, sem JSON-RPC à mão.
**Feito:** `mcp.server.lowlevel.Server`, com `tools/list` e `tools/call` registrados à mão — e não
a API de decoradores.

A razão é uma exigência da própria seção 8 que a API de alto nível não atende: erro de negócio
precisa sair com `isError=true` **e** `structuredContent` `{ok:false, error:{code,...}}`. Nos
decoradores, um retorno normal nunca marca `isError`, e uma exceção marca `isError` mas descarta o
conteúdo estruturado, entregando só "Error executing tool X". O `code` estável — que é o que o
agente usa para decidir se pergunta, espera ou desiste — se perderia.

A API de baixo nível também obriga a declarar `inputSchema` e `outputSchema` explicitamente, que é
o que o documento pede; nos decoradores eles seriam inferidos da assinatura.

## D-11 — Anotações de ferramenta são dica, não autorização

`readOnlyHint` e `idempotentHint` vão declarados, mas quem recusa é a API. A especificação diz isso
com todas as letras, e vale repetir aqui: um cliente MCP pode ignorar anotação, e a única coisa que
impede o agente de confirmar uma visita é `confirmar_visita` **não existir** no catálogo.

## D-12 — A Mora publica no fim do turno, depois de responder ao cliente

A chamada ao CRM acontece **depois** do despacho da resposta e engole a própria falha. Um CRM fora
do ar não pode virar um atendimento fora do ar: o cliente recebe a resposta, e a publicação perdida
vira uma linha de log — e volta sozinha no turno seguinte, porque o `operation_id` é estável.

Por isso também o encaminhamento é publicado do handler, e não do nó do grafo: no nó, uma falha do
CRM abortaria a resposta que a pessoa está esperando.

## D-13 — O `external_event_id` é o id da mensagem, não um hash do texto

Primeira versão derivava o identificador da interação de um hash do CONTEÚDO. O índice único do CRM
é `(canal, external_event_id)` — global, não por cliente. Resultado: dois clientes diferentes que
escrevessem "Oi, tudo bem?" no mesmo canal colidiam, e a mensagem do segundo entrava no histórico do
primeiro (ou melhor: não entrava em lugar nenhum).

`MensagemRepository.registrar` passou a devolver o id da linha, e é ele que vai para o CRM. Além de
único, resolve o caso legítimo de duas mensagens idênticas do mesmo cliente em turnos diferentes —
que o hash do texto engolia.

*Apareceu ao rodar a suíte duas vezes seguidas: na segunda, o histórico saía vazio.*

## D-14 — `agendado` da Mora não vira `visit_scheduled` no CRM

O CRM só aceita `visit_scheduled` com visita confirmada por uma pessoa, e o agente não confirma
visita. Então o estágio publicado para em `qualified`, e avança lá quando o corretor confirmar.

É uma divergência deliberada entre os dois sistemas: o CRM não pode afirmar "visita marcada" porque
o agente achou que marcou.

## D-15 — O painel usa sessão em cookie, e o mesmo host da API

`credentials: "include"` em toda chamada, e nenhum token de serviço no bundle: qualquer `VITE_*` vai
para dentro do arquivo que o navegador baixa.

A armadilha que isso cria, e que só apareceu abrindo o painel de verdade: **`localhost` e
`127.0.0.1` são sites diferentes para o navegador**. Com o painel em um e a API no outro, o login
devolve 200, o cookie `SameSite=Lax` não é guardado, e a tela volta ao formulário em branco — o
clássico "cliquei e não aconteceu nada". Três consertos: os dois endereços entraram na lista de
origens permitidas; o painel confere `/auth/me` logo após o login e explica o problema quando a
sessão não cola; e uma falha de rede/CORS agora tem mensagem própria, em vez do genérico "não foi
possível carregar" que mandaria a pessoa procurar o erro na senha.

## D-16 — Senha de acesso ao painel é GERADA no seed, não escrita no código

O seed cria uma senha aleatória para quem ainda não tem e a imprime uma vez. Senha de
desenvolvimento fixa no repositório é senha de produção no dia em que alguém apontar isto para um
ambiente exposto. Quem já tem senha não é tocado, então o seed continua idempotente.

## D-17 — Dois defeitos que só a tela mostrou

O quadro do funil pedia uma página (o máximo da API é 100) e exibia **100 de 120** oportunidades,
com contagens que contradiziam a Visão geral na tela anterior. Agora segue o cursor, com teto de 20
páginas e aviso quando trunca.

E os cartões mostravam `cliente 4a9ff44e`: a lista de oportunidades não trazia o nome. Um Kanban de
UUIDs obriga a abrir cada cartão para saber de quem se trata — `GET /opportunities` passou a
devolver `lead_name`.

Nenhum dos dois quebrava teste nenhum, e nenhum aparece em `tsc`.

## D-18 — O que eu afirmei sem medir, e o que a medição devolveu

Três afirmações minhas sobre o comportamento do sistema, feitas lendo código, foram desmentidas por
medição em dois dias. Ficam registradas porque o padrão importa mais que os casos.

**"O sistema nunca guardou um byte de imagem."** O painel da Mora tinha envio, remoção e troca de
capa desde antes — bytes em `fotos_dir/<imovel>/<uuid>.jpg`. A discussão inteira sobre onde gravar
imagem aconteceu sem olhar o lado que já tinha a resposta.

**"O resultado depende de qual regra roda primeiro."** Sobre as duas fontes de foto. Medido, não
depende: painel > CRM > arquivo, sempre, porque o `CASE` do `upsert` fala por último (ADR-0015).

**"O painel pode enviar a foto e gravar a referência no CRM."** Recomendado sem olhar o
`exigir_humano`, que exige sessão de usuário e não credencial de serviço. A recomendação era
inviável sem criar "agindo em nome de" — e esse custo mudou a decisão inteira.

As três custaram tempo e uma delas custou uma recomendação errada. O que funcionou, nas três, foi a
mesma coisa: rodar. O painel mostrou os bytes, o teste mostrou a ordem, o código de autenticação
mostrou a parede.

## D-19 — Uma tabela de amostra não confere um schema

O `/health/ready` do CRM já tinha a intenção certa escrita no docstring: "conecta mas não tem tabela
é indisponível, senão a primeira requisição quebra com erro de SQL". A conferência olhava
`opportunities` e mais nada.

Entrou `property_photos`, o readiness seguiu verde, e o erro apareceu do jeito que aquela
verificação existia para evitar: traceback de `psycopg` no meio de uma consulta de imóvel.

A lista de tabelas passou a sair do próprio `schema.sql`. Lista escrita à mão envelhece em silêncio,
e foi exatamente o que aconteceu.

Duas lições operacionais vieram junto, e as duas são sobre o mesmo arquivo ser reaplicado a cada
`docker compose up`: **`restart` não roda o `db-init`**, então mudança de schema exige `up`; e
`CREATE TABLE IF NOT EXISTS` **não acrescenta coluna** em tabela que já existe — coluna nova em
tabela antiga só entra por `ALTER ... ADD COLUMN IF NOT EXISTS`. A segunda foi descoberta por teste
vermelho, não por leitura.
