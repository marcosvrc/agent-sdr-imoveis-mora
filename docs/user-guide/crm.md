---
title: CRM
description: Manual do CRM da imobiliária — login, funil, clientes, imóveis, agenda, visitas, encaminhamentos, auditoria, papéis e os erros que a tela pode mostrar.
---

# Manual do CRM

## 1. O que é, o que não é

O CRM é o sistema **da imobiliária**: cadastro de clientes, funil de oportunidades, acervo de
imóveis, agenda de visitas, tarefas e encaminhamentos. É um sistema **à parte** da Mora — tem
front próprio (`apps/crm`), API própria (`services/crm`) e banco próprio (`crm`, e não `sdr`).
A separação existe para o fluxo ser num sentido só: a Mora escreve no CRM pela API; nada do CRM
escreve no banco dela (`services/crm/sdr_crm/db/schema.sql`, cabeçalho; `services/crm/sdr_crm/config.py`).

O que ele **não** é:

- Não é o painel administrativo da Mora (ver [painel.md](painel.md)). O painel configura o agente,
  a base de conhecimento e as fotos; o CRM opera a carteira comercial. As duas telas têm cores e
  nomes diferentes de propósito: o cabeçalho do CRM diz "Vértice Imóveis · CRM · operação"
  (`apps/crm/src/App.tsx`).
- Não é um sistema em produção. Uma faixa permanente no topo avisa: **"Ambiente de testes — dados
  sintéticos. Nenhum contato aqui é uma pessoa real."** Ela não fecha nem some ao rolar
  (`apps/crm/src/componentes/ui.tsx`, `FaixaSintetica`).

**Como a Mora entra.** O agente não usa a tela: fala com o CRM por MCP (`crm-mcp:8200/mcp`), e o
servidor MCP chama a REST com uma **credencial de serviço** emitida por `make crm-token`. Essa
credencial tem escopos limitados e nunca inclui `admin` (`services/crm/sdr_crm/credenciais.py`,
`PADRAO`). O que a Mora pode e não pode fazer está na seção 4.

### Acesso

| O quê | Onde | Fonte |
|---|---|---|
| Tela do CRM | `http://localhost:3000` | `local/docker-compose.yml`, serviço `crm-web` |
| API REST | `http://localhost:8100` (`VITE_CRM_API`) | `crm-api`; `apps/crm/src/lib/api.ts`, `BASE` |
| Servidor MCP (só a Mora) | `:8200/mcp` | `crm-mcp` |
| Banco | Postgres `crm`, host `127.0.0.1:5433` | `db` |

Abra o painel e a API pelo **mesmo host** (`localhost` nos dois, ou `127.0.0.1` nos dois). Para o
navegador são sites diferentes, e o cookie de sessão não é guardado — o login devolve 200 e a tela
volta ao formulário. A tela detecta isso e mostra `SESSAO_NAO_PERSISTIU` com a orientação
(`apps/crm/src/paginas/Entrar.tsx`).

### Login

Tela "CRM da imobiliária", campos **E-mail** e **Senha**, botão **Entrar** (`Entrar.tsx`).

- **Usuários do seed**: Ana Ribeiro (`ana@example.com`, admin), Bruno Carvalho
  (`bruno@example.com`, broker), Carla Mendes (`carla@example.com`, broker), Diego Alves
  (`diego@example.com`, broker) (`services/crm/sdr_crm/seed/gerar.py`, `usuarios`).
- **Senhas**: não estão no repositório. `make crm-reset`/`crm-seed` gera uma senha aleatória para
  cada usuário que ainda não tem e imprime **uma única vez** no terminal, sob "Acesso ao painel
  (aparece só nesta execução)". Quem já tem senha não é tocado
  (`services/crm/sdr_crm/seed/__main__.py`, `_senha_de_bootstrap`).
- **Mensagem única de erro**: "E-mail ou senha inválidos." vale para usuário inexistente, senha
  errada e conta inativa. A tela não é mais específica que a API, para não revelar quais e-mails
  existem (`services/crm/sdr_crm/api/routers/autenticacao_rt.py`).
- **Teto de tentativas**: 10 por minuto **por IP** e 10 por minuto **por e-mail**, contados
  separadamente. Estourou → `RATE_LIMITED` (429) com `retry_after_seconds`
  (`services/crm/sdr_crm/config.py`, `login_tentativas_por_minuto`; `api/contexto.py`,
  `conferir_limite_de_login`).
- **Sessão**: cookie `crm_session`, HttpOnly, dura **12 horas** (`autenticacao_rt.py`, `DURACAO`).
  Expirou → a tela de login diz "Sua sessão expirou. Entre de novo para continuar."
- **Sair**: botão **Sair** no rodapé do menu. Revoga a sessão no banco (não só apaga o cookie) e
  limpa o cache da tela antes de voltar ao login (`App.tsx`, `sair`; `autenticacao_rt.py`).
- Limites de tamanho: e-mail até 320 caracteres, senha até 256 (`api/esquemas.py`, `Login`).

### Tema

Botão de sol/lua no cabeçalho do menu abre **Claro** ("Sempre claro"), **Escuro** ("Sempre
escuro") e **Sistema** ("Acompanha o macOS/Windows"). O padrão é Sistema; a escolha fica no
navegador (chave `tema-crm`, separada da do painel). O ícone mostra o tema em vigor; a marca de
seleção mostra a escolha (`apps/crm/src/lib/tema.ts`; `ui.tsx`, `SeletorTema`). Mesma mecânica
do painel (ADR-0014).

## 2. Convenções da interface

- **Identidade própria.** Menu lateral (gaveta no celular) com "Visão geral", "Funil", "Clientes",
  "Imóveis", "Visitas", "Encaminhamentos" e, só para administrador, "Auditoria". Rodapé mostra o
  nome e o papel ("administrador" ou "corretor") (`App.tsx`, `MENU`).
- **Link "Pular para o conteúdo"** é o primeiro item focável da página (`App.tsx`).
- **Trilha (breadcrumb).** Telas de detalhe têm um link de volta acima do título (ex.: "Clientes",
  "Voltar ao cliente", "Imóveis"). Existe porque quem chega por link colado não teria saída
  (`ui.tsx`, `CabecalhoPagina`).
- **Filtros na URL.** Em Clientes, Imóveis e Visitas os filtros vão para a barra de endereços:
  o botão voltar do navegador desfaz o filtro, a busca vira link copiável e recarregar não perde
  nada. Valor igual ao padrão sai da URL (`apps/crm/src/lib/filtros.ts`, `useFiltrosNaUrl`).
- **Busca com atraso.** Campos de texto esperam a digitação parar (350 ms; 500 ms no teto de
  preço) antes de consultar. Enquanto consulta, o card mostra "buscando…"
  (`filtros.ts`, `useAtraso`).
- **Paginação por cursor.** Não existe "página 7 de 12": a API pagina por `(created_at, id)` e não
  devolve total. A tela diz "N itens nesta página · página P" e oferece **Anterior** / **Próxima**
  (`ui.tsx`, `Paginacao`). Tamanhos: 25 clientes, 24 imóveis, 50 visitas por página; máximo da
  API é 100 (`api/protocolo.py`, `limite`).
- **Ordenação com aviso de ordem parcial.** Ordenar por coluna ou seletor reordena **só a página
  carregada**, porque o servidor entrega sempre por data de criação e não aceita outro critério.
  Quando há página seguinte, aparece a faixa: "A ordenação vale para esta página. Há mais
  resultados adiante, e o servidor entrega sempre por data de criação — o primeiro daqui não é
  necessariamente o primeiro de todos." Em tabelas, clicar no cabeçalho alterna crescente →
  decrescente → sem ordenação (a ordem do servidor é a única completa). Valores ausentes vão para
  o fim (`filtros.ts`, `ordenar`; `ui.tsx`, `AvisoOrdemParcial`, `ColunaOrdenavel`).
- **Etiquetas** coloridas sempre com texto junto (nunca só a cor): estágio, atendimento,
  política de contato, situação do imóvel, status da visita (`apps/crm/src/lib/formato.ts`).
- **Datas** em America/Sao_Paulo; o banco guarda UTC. Datas recentes aparecem relativas ("há 3 d")
  com a data completa no `title` (`formato.ts`, `dataHora`, `relativo`).
- **Dinheiro** em centavos no banco, R$ na tela (`formato.ts`, `brl`).
- **Botões ocupados** mostram "Aguarde…" até o servidor responder; nada é dado como feito antes
  disso. Erros aparecem com a mensagem da API, o código e os 8 primeiros caracteres do
  `request_id` (`ui.tsx`, `Botao`, `Erro`).
- **Estados vazios** têm texto próprio em toda lista ("Nenhum cliente encontrado", "Vazio.", etc.).

## 3. Telas

### 3.1 Visão geral — `/`

Página inicial. Mostra "Atualizado há N min · data" (carimbo `generated_at` do servidor).

Quatro números, os três primeiros com link e etiqueta "ação" quando maior que zero:

| Rótulo | Nota | Vai para | Conta |
|---|---|---|---|
| Esperando um corretor | encaminhamentos pendentes | /encaminhamentos | handoffs `pending` |
| Tarefas vencidas | prazo já passou | — | tarefas `open` com `due_at < now()` |
| Visitas a confirmar | solicitadas pelo agente | /visitas | visitas `requested` |
| Visitas futuras | já confirmadas | /visitas | visitas `confirmed` com início no futuro |

Card **Funil** com barra por estágio e link "abrir o quadro"; card **Base** com "Clientes ativos"
(não arquivados), "Oportunidades" (soma dos estágios) e "Imóveis disponíveis" (status `available`)
(`apps/crm/src/paginas/Visao.tsx`; `api/routers/dashboard_rt.py`).

### 3.2 Funil — `/funil`

Quadro com sete colunas, da esquerda para a direita, cada uma com contagem e texto de ajuda
(`formato.ts`, `ESTAGIOS`):

| Coluna | Ajuda na tela | Encerrado |
|---|---|---|
| Novo | Chegou e ainda ninguém falou com ele. | |
| Em atendimento | Conversa começou; o cartão ainda está incompleto. | |
| Qualificado | Já se sabe cidade, finalidade e teto de orçamento. | |
| Visita marcada | Tem visita confirmada no futuro. | |
| Negociação | Proposta em discussão — só uma pessoa move para cá. | |
| Ganho | Fechou. | sim |
| Perdido | Encerrado, com motivo registrado. | sim |

**Carregamento.** O quadro busca **todas** as oportunidades seguindo o cursor (páginas de 100, até
20 páginas). Se passar disso, avisa: "Mostrando as N mais recentes — há mais no banco do que cabe
neste quadro." (`apps/crm/src/paginas/Funil.tsx`, `PAGINAS_MAX`).

**Cada cartão** mostra a finalidade ("Aluguel"/"Compra", link para a oportunidade), o nome do
cliente (link para a ficha; sem nome vira "Cliente sem nome · xxxx" em itálico), a etiqueta de
atendimento quando não está com a Mora, e o motivo de perda quando houver.

**"Parada há N d".** Calculado sobre `updated_at` (última mexida), não sobre a criação. Limiares:
a partir de **7 dias** fica amarelo (atenção); a partir de **15 dias** fica vermelho (grave);
"mexida hoje" quando é zero. Estágios encerrados (Ganho, Perdido) nunca acendem. O cabeçalho da
coluna mostra "N parada(s)" somando os cartões acesos (`formato.ts`, `PARADO_ATENCAO`,
`PARADO_GRAVE`, `tomDoParado`).

**Mover pelo menu**, não por arrastar. Em cada cartão: seletor "Mover para…" com os outros
estágios, campo "Motivo (obrigatório)" quando a transição exige, e botão **Confirmar**. Se o
servidor recusar, a coluna não muda e o erro aparece no topo. A tela pede motivo para ir a
Perdido e para reabrir (Ganho/Perdido → Em atendimento); a lista completa de transições
permitidas e quem pode fazê-las está em
[regras-de-negocio.md](../technical-reference/regras-de-negocio.md) e resumida aqui
(`services/crm/sdr_crm/dominio/funil.py`):

| De | Para (permitido) | Observações |
|---|---|---|
| new | in_service, lost | |
| in_service | qualified, lost | qualificar exige cidade, propósito e teto de orçamento (`QUALIFICATION_INCOMPLETE`) |
| qualified | visit_scheduled, negotiation, lost | |
| visit_scheduled | qualified, negotiation, lost | |
| negotiation | won, lost | |
| won | in_service | reabertura administrativa, com motivo |
| lost | in_service | reabertura administrativa, com motivo |

- Motivo é exigido para qualquer → `lost` e para `won`/`lost` → `in_service`
  (`funil.py`, `EXIGEM_MOTIVO`; `schema.sql`, `opportunities_perda_ck`).
- `visit_scheduled` só é aceito com visita confirmada no futuro (`VISIT_NOT_CONFIRMED`); na
  prática ele nasce ao confirmar uma visita, não pelo menu.
- Qualquer outra combinação → `INVALID_TRANSITION`, com a lista `allowed` nos detalhes.
- Se outra pessoa mexeu no cartão antes de você confirmar → `VERSION_CONFLICT` e a tela diz:
  "Alguém alterou esta oportunidade enquanto a tela estava aberta. Recarregue para ver o estado
  atual antes de mover de novo."

### 3.3 Clientes — `/clientes`

Descrição da tela: "Nome procura; e-mail e telefone identificam. Arquivados ficam fora por padrão."

**Filtros** (card "Filtros", todos na URL):

| Campo | Comportamento | Fonte |
|---|---|---|
| Procurar por nome | `ILIKE %texto%`, com atraso de digitação | `api/routers/leads_rt.py`, `listar` |
| E-mail ou telefone | correspondência **exata**; com `@` vai como e-mail, senão como telefone (normalizado para E.164) | `Clientes.tsx`; `leads_rt.py` |
| Mostrar arquivados | inclui `archived_at` preenchido | `include_archived` |

Botão **Limpar filtros** aparece quando há algum filtro ativo.

**Tabela**: colunas **Nome** (link; ao lado, etiquetas "arquivado" e a política de contato quando
não for "Sem autorização registrada"), **Contato** (e-mail, ou telefone, ou identificador
externo), **Origem**, **Criado** (relativo). Nome, Origem e Criado ordenam a página.

Vazio: "Nenhum cliente encontrado — Ajuste os filtros. Clientes arquivados ficam fora da lista por
padrão e continuam acessíveis pelo link direto."

**Regras de cadastro** (a tela não cria clientes; quem cria é a Mora ou o seed):
- Todo cliente precisa de **pelo menos um identificador**: e-mail, telefone ou identificador
  externo. Nome não identifica pessoa (`schema.sql`, `leads_identificador_ck`; `esquemas.py`,
  `LeadNovo.exige_identificador`).
- Telefone precisa casar `^\+[1-9][0-9]{7,14}$` (`schema.sql`, `phone_e164`).
- E-mail, telefone e (origem + id externo) são únicos (`schema.sql`, índices `leads_*_uk`).
- Identificadores que apontem para clientes diferentes não são unidos automaticamente: a API
  devolve `LEAD_CONFLICT` para revisão humana (`leads_rt.py`).

#### Ficha do cliente — `/clientes/:id`

Título é o nome; trilha "Clientes". Etiquetas: "arquivado em <data>" (quando for o caso) e a
política de contato: "Sem autorização registrada" / "Contato liberado" / "Pediu para não ser
contatado" (`formato.ts`, `POLITICA_CONTATO`).

- Card **Identificação**: E-mail, Telefone, Identificador externo, Origem, Cadastrado.
- Card **Contato**: botões **Liberar contato** (quando não está liberado), **Bloquear contato**
  (quando não está bloqueado; botão vermelho) e **Arquivar** (quando não está arquivado). Texto da
  tela: "A Mora pode bloquear o contato a pedido do cliente, mas nunca liberar". Confirmado na API:
  qualquer mudança de política que não seja para `blocked` exige humano; arquivar exige humano
  (`leads_rt.py`, `alterar`). Não há botão de desarquivar na tela ("não localizado" em
  `LeadDetalhe.tsx`; a API aceita `archived: false` de um humano).
- Card **Oportunidades**: uma linha por oportunidade com finalidade, estágio e atendimento; link
  para o detalhe. Se houver mais de uma: "A mesma pessoa pode comprar e alugar ao mesmo tempo —
  cada intenção tem preferências próprias."
- Card **Linha do tempo**: interações em ordem decrescente, cada uma com etiqueta "cliente"
  (inbound) / "nós" (outbound) / "interno", o canal, a data e o texto **inteiro, sem
  interpretação**. Vazio: "Nenhuma interação registrada". Um cliente arquivado não recebe
  oportunidade nova (`api/routers/oportunidades_rt.py`, `criar`).

#### Oportunidade — `/oportunidades/:id`

Chega-se por um cliente, pelo funil, por uma visita ou por um encaminhamento; não há lista solta.
Trilha "Voltar ao cliente". Etiquetas de estágio e atendimento; faixa informativa quando não está
com a Mora:
- `human_pending` ("Aguardando corretor"): "Encaminhado: a Mora parou de movimentar esta
  oportunidade e está só registrando o que o cliente escreve."
- `human` ("Com o corretor"): "Um corretor assumiu. A Mora continua ouvindo, mas não age até
  alguém devolver o atendimento."

Cards (`apps/crm/src/paginas/OportunidadeDetalhe.tsx`):
- **O que o cliente procura**: Cidade, Bairros, Tipos, Orçamento (ou "Orçamento (custo mensal)"
  quando `budget_basis = monthly_total`), Quartos (mínimo), Vagas (mínimo), Exigências. Sem cidade
  e sem teto: "Preferências ainda incompletas — A qualificação exige cidade, finalidade e teto de
  orçamento. Enquanto faltar, a oportunidade não avança." Limites: até 20 bairros, 10 tipos, 20
  exigências; mínimo ≤ máximo; `monthly_total` só em aluguel (`esquemas.py`, `Preferencias`;
  `oportunidades_rt.py`, `salvar_preferencias`).
- **Imóveis apresentados**: título, código e etiqueta "apresentado" / "interessou" / "descartado".
  Imóvel e oportunidade precisam ter a mesma finalidade (`oportunidades_rt.py`,
  `registrar_interesse`).
- **Visitas**: data e status. Nota: "Confirmar, concluir e marcar falta são ações de uma pessoa —
  na tela de Visitas."
- **Tarefas**: título (riscado quando concluída), etiqueta "contato" (`follow_up`) ou "interno",
  prazo. A tela só lê; tarefa de contato é recusada para cliente bloqueado (`CONTACT_BLOCKED`), a
  interna passa (`api/routers/tarefas_rt.py`).

### 3.4 Imóveis — `/imoveis`

Descrição: "Custo mensal discriminado. Total incompleto aparece marcado, nunca como um número
menor." Botão **+ Novo imóvel** no cabeçalho.

**Card "Busca"** (tudo na URL; padrão Aluguel + Custo mensal total):

| Campo | Opções / regra |
|---|---|
| Finalidade | Aluguel (`rent`, padrão) · Compra (`buy`) |
| Comparar o orçamento com | Custo mensal total (`monthly_total`) · Só o valor do imóvel (`base_price`); desabilitado fora de Aluguel |
| Até (R$) | só dígitos; vira `max_price_cents` |
| Bairro | igualdade com o campo `neighborhood` |

Nota quando a base é custo mensal: "Custo mensal = aluguel + condomínio + IPTU + outros. Imóvel com
algum desses valores desconhecido aparece marcado como incompleto, e não é escondido do resultado."
Isso é feito no servidor: com `monthly_total`, o filtro de preço roda em Python e mantém o que
"não dá para afirmar" (`api/routers/imoveis_rt.py`, `listar`). A lista traz só `available`, salvo
busca por código (`listar`, parâmetro `status`).

**Ordenar por**: "Ordem do servidor (mais recentes)", "Preço — menor primeiro", "Preço — maior
primeiro", "Mais quartos", "Bairro (A–Z)". Vale para a página, com o aviso de ordem parcial.

**Cartão do imóvel** (`apps/crm/src/paginas/Imoveis.tsx`):
- Título; etiqueta de situação quando não é Disponível.
- Linha "código · bairro, cidade · N quarto(s) · N vaga(s)".
- Aluguel: valor grande "R$ X/mês" ou, em laranja, "total incompleto", com "aluguel R$ Y · falta:
  condomínio, IPTU, outros". Compra: preço abreviado ("R$ 1,2 mi").
- Etiqueta **"N clientes de olho"** quando **2 ou mais** clientes distintos têm interesse vivo
  (`presented` ou `interested`; descartado não conta). Com um só, não aparece
  (`imoveis_rt.py`, `_procura`; `Imoveis.tsx`).
- Botões **Mudar situação** e **Agenda**.

**Situação** (`formato.ts`, `SITUACAO_IMOVEL`; `imoveis_rt.py`, `mudar_situacao`):

| Valor | Etiqueta | Ajuda na tela | Para a Mora |
|---|---|---|---|
| `available` | Disponível | No catálogo. A Mora oferece. | aparece no índice |
| `reserved` | Reservado | Proposta aceita, antes da assinatura. Sai do catálogo e pode voltar. | não aparece |
| `unavailable` | Indisponível | Vendido ou alugado. Fora do catálogo. | não aparece |

Regras ao clicar em **Mudar situação** → seletor "Para…" → **Confirmar** / **Cancelar**:
- **Reversível.** Qualquer situação pode ir para qualquer outra; não há caminho só de ida.
  O servidor recusa apenas repetir a mesma ("O imóvel já está nesta situação.").
- **Motivo obrigatório para sair do catálogo** (para Reservado ou Indisponível); opcional para
  voltar a Disponível. A tela mostra "Motivo (obrigatório)" nesses casos; a API recusa com 422
  "tirar o imóvel do catálogo exige motivo" (`esquemas.py`, `SituacaoImovel.motivo_para_sair`).
  Máximo 500 caracteres.
- **Recusa com visita confirmada futura.** Sair do catálogo com visita `confirmed` cujo horário
  ainda não passou → 409: "Há visita confirmada no futuro para este imóvel. Cancele antes de
  tirá-lo do catálogo." (`imoveis_rt.py`, `mudar_situacao`).
- Não é automático a partir de "Ganho" no funil: a oportunidade é do cliente, o imóvel é do acervo.
- Só humano muda situação (`exigir_humano`). Fica em auditoria como `property.status_changed`.

#### Novo imóvel — `/imoveis/novo`

Descrição: "Cadastro é ação humana. O agente lê o catálogo e nunca escreve nele." Botão
**Cadastrar imóvel** fica desabilitado até código, título, bairro e preço (> 0) estarem
preenchidos. Ao salvar, volta para a lista (`apps/crm/src/paginas/NovoImovel.tsx`).

Card **Identificação**:

| Campo | Obrigatório | Tipo / limite | Observação |
|---|---|---|---|
| Código | sim | texto 1–40, **único** | vira maiúsculas ao digitar; dica: "A chave entre o CRM e a Mora — é por ele que ela pede horários deste imóvel." Duplicado → 409 "Já existe imóvel com este código." (`schema.sql`, `code UNIQUE`; `imoveis_rt.py`, `criar`) |
| Situação | — | Disponível / Reservado / Indisponível (padrão Disponível) | |
| Título | sim | texto 1–300 | |
| Cidade | sim | texto 1–120 | padrão "São Paulo" |
| Bairro | sim | texto 1–120 | dica: "A Mora deduz a região a partir daqui." |
| Tipo | — | apartamento, casa, studio, cobertura, sobrado, kitnet | padrão apartamento |
| Finalidade | — | Aluguel / Compra | padrão Aluguel |
| Descrição | não | texto até 4000 | dica: "O que a Mora vai ler para descrever o imóvel na conversa." |

Card **Valores e medidas** (reais digitados, gravados em centavos; aceita "3.500" e "3500,50"):

| Campo | Obrigatório | Limite | Observação |
|---|---|---|---|
| Aluguel (R$) / Preço (R$) | sim, > 0 na tela | 0 ≤ valor ≤ 10¹² centavos | `base_price_cents` |
| Área (m²) | não | > 0 e ≤ 100 000 | |
| Condomínio (R$) | não (só Aluguel) | ≥ 0 | "Em branco = desconhecido. Zero = afirma que não há." |
| IPTU mensal (R$) | não (só Aluguel) | ≥ 0 | "Em branco = desconhecido." |
| Outros custos (R$) | não (só Aluguel) | ≥ 0 | |
| Quartos | — | 0–30 | padrão 0 |
| Vagas | — | 0–30 | padrão 0 |

Em Compra os três custos mensais vão como nulos ("não se aplica"). Em branco grava **nulo**, e o
cartão mostra "total incompleto" em vez de um número menor (`esquemas.py`, `ImovelNovo`;
`schema.sql`, `properties`).

Card **Fotos** (botão **+ Adicionar**):
- Cada foto é uma **URL** ("https://…") e uma descrição opcional (`alt`, até 300 caracteres).
  A URL precisa começar com `http://` ou `https://` (8–2000 caracteres); a tela avisa "Precisa
  começar com http:// ou https://" e o banco também confere (`esquemas.py`, `FotoImovel`;
  `schema.sql`, `property_photos.url`).
- A **primeira é a capa** ("Capa — vai para o cartão e para a busca"); as demais são "Foto N".
  Setas movem para cima/baixo; a posição gravada é o índice da lista (`imoveis_rt.py`,
  `_gravar_fotos`).
- Máximo **20** fotos. A **mesma URL duas vezes** na lista → **422** "a mesma foto aparece duas
  vezes na lista" (`esquemas.py`, `_conferir_fotos`; `schema.sql`, `property_photos_unica`).
- Sem foto: "Sem foto, o imóvel aparece na vitrine com o espaço vazio — e não com uma imagem
  genérica". Linhas com URL vazia são descartadas ao salvar.
- Fotos e imóvel são gravados na mesma transação. Existe `PUT /v1/properties/{id}/photos` para
  trocar a galeria inteira, mas **não há tela** para isso ("não localizado" em `paginas/`).

Todo campo desconhecido no corpo é recusado com 422 (`esquemas.py`, `extra="forbid"`).

#### Agenda do imóvel — `/imoveis/:id/agenda`

Descrição: "Horário aberto é o que a Mora oferece ao cliente. Confirmar a visita continua sendo ato
humano." Trilha "Imóveis" (`apps/crm/src/paginas/AgendaImovel.tsx`).

Card **Abrir horário**:

| Campo | Regra |
|---|---|
| Corretor | lista de usuários ativos com papel admin ou broker ("(admin)" ao lado); dica "Só quem está ativo e pode receber visita." (`imoveis_rt.py`, `listar_corretores`) |
| Dia | data |
| Hora | passo de 15 min |
| Duração | 30, 45, 60 (padrão) ou 90 minutos |

- A tela mostra "Abre <início> até <fim>." antes de enviar. Dia e hora são interpretados no fuso
  do navegador e gravados em UTC.
- **Passado bloqueado**: "Esse horário já passou." e o botão **Abrir horário** fica desabilitado
  (`AgendaImovel.tsx`, `noPassado`). Início precisa ser anterior ao fim (`esquemas.py`,
  `SlotNovo`; `schema.sql`, `availability_intervalo_ck`).
- **Sobreposição do mesmo corretor → 409** "O corretor já tem horário neste intervalo." Vem da
  restrição de exclusão do banco sobre `[início, fim)`: 14h–15h e 15h–16h **não** se sobrepõem
  (`schema.sql`, `availability_sem_sobreposicao`; `imoveis_rt.py`, `criar_slot`).
- Corretor inativo ou sem papel → 409 "Horário precisa de um corretor ativo."
- Só humano abre horário (`exigir_humano`).

Card **Horários deste imóvel** ("N no futuro"): lista todos, inclusive ocupados (`only_free=false`),
cada um com data, corretor e etiqueta **"visita confirmada"** (há visita `confirmed`/`completed`
nele), **"passou"** (início no passado, linha esmaecida) ou **"livre"**. Nota: "Horário livre pode
ter solicitação pendente: solicitar não reserva nada. Ele só sai de circulação quando alguém
confirma — e quem confirma é uma pessoa, na tela de Visitas." Vazio: "Nenhum horário aberto".

### 3.5 Visitas — `/visitas`

Descrição: "Solicitar não agenda: o agente pede, quem confirma é uma pessoa." Filtro de situação
(na URL; padrão **Solicitadas**): Solicitadas, Confirmadas, Concluídas, Canceladas, Todas. Ordenar:
"Ordem do servidor (mais recentes)", "Mais próxima primeiro", "Mais distante primeiro", "Situação"
(`apps/crm/src/paginas/Visitas.tsx`). A API lista por horário de início.

**Estados** (`formato.ts`, `STATUS_VISITA`; `api/routers/visitas_rt.py`, `PERMITIDAS`):

| Estado | Etiqueta | Botões na tela | Vai para |
|---|---|---|---|
| `requested` | Solicitada | **Confirmar**, **Cancelar**, **Remarcar** | confirmed, cancelled |
| `confirmed` | Confirmada | **Concluir**, **Não compareceu**, **Cancelar**, **Remarcar** | completed, cancelled, no_show |
| `completed` | Concluída | — ("encerrada") | — |
| `cancelled` | Cancelada | — ("encerrada" ou "remarcada — a visita seguinte está na lista") | — |
| `no_show` | Não compareceu | — | — |

Cada linha: data/hora, etiqueta, link "oportunidade xxxxxxxx" e, se cancelada, "motivo: …" ou
"remarcada — …".

**Quem pode o quê** (`visitas_rt.py`):
- **Confirmar, Concluir, Não compareceu**: só humano (`exigir_humano`).
- **Cancelar**: humano cancela solicitada ou confirmada; o agente só cancela o que ainda está
  `requested` ("O agente só cancela visita ainda não confirmada."). **Motivo obrigatório**: a tela
  abre "Motivo do cancelamento" e o botão **Confirmar cancelamento** só habilita com texto; a API
  recusa "Cancelar exige motivo."
- **Confirmar** pode avançar a oportunidade de Qualificado para Visita marcada. **Cancelar** a
  última visita confirmada futura devolve Visita marcada → Qualificado; Negociação não regride
  (`dominio/funil.py`, `estagio_apos_cancelar_visita`).
- **Duas confirmações no mesmo horário não coexistem**: o índice único do banco decide, e quem
  perde recebe `SLOT_UNAVAILABLE` (`schema.sql`, `visits_slot_confirmado_uk`). A tela explica:
  "Outra visita foi confirmada nesse horário antes desta. O horário é de quem confirmou primeiro —
  escolha outro com o cliente."
- Transições usam `If-Match`: se a visita mudou no meio, `VERSION_CONFLICT`.
- **Solicitar** (só a Mora, via MCP; a tela não tem botão) exige oportunidade qualificada ou além,
  não encerrada, imóvel `available` com a mesma finalidade, horário do próprio imóvel e no
  futuro; com atendimento humano o agente não pede (`visitas_rt.py`, `solicitar`).

**Remarcar** (botão **Remarcar**, nas solicitadas e confirmadas):
- Escolhe **outro horário livre do mesmo imóvel** ("Novo horário… — data · corretor"), com
  "Motivo (obrigatório)" (1–500 caracteres), e **Confirmar remarcação**. Sem horário livre: "Não
  há outro horário livre para este imóvel — abra um na agenda antes de remarcar."
- É **uma operação só**: a antiga vira `cancelled` apontando para a nova (`rescheduled_to`), na
  mesma transação. Se o horário novo já tiver confirmação, nada acontece — nem o cancelamento
  (`visitas_rt.py`, `remarcar`; `schema.sql`, `rescheduled_to`).
- **Humano remarcando uma confirmada → a nova nasce confirmada.** Remarcando uma solicitada, ou
  vindo do agente, a nova nasce solicitada.
- **O agente só solicita**: não remarca visita já confirmada ("O agente não remarca visita já
  confirmada."), e não confirma nada.
- Mesmo horário da visita atual é recusado; horário no passado também.

### 3.6 Encaminhamentos — `/encaminhamentos`

Descrição: "Cliente que pediu uma pessoa. Aceitar é assumir o atendimento." Filtro (não vai para a
URL): **Na fila** (`pending`, padrão), **Assumidos** (`accepted`), **Resolvidos** (`resolved`)
(`apps/crm/src/paginas/Encaminhamentos.tsx`).

Cada cartão: nome do cliente (ou "Cliente"), estágio, etiqueta "na fila" / "com você" /
"resolvido", "Motivo: …", o resumo inteiro, links "ver o cliente" e "ver a oportunidade".

Ações (`api/routers/handoffs_rt.py`; humano em todas):
- **Assumir** (na fila): passa a `accepted`, a oportunidade vai para atendimento `human`, e o
  responsável passa a ser quem clicou (salvo destinatário já definido).
- **Resolver** (assumido) abre a escolha obrigatória: **Devolver para a Mora** (`return_to =
  agent`) ou **Continuo eu** (`return_to = human`), com o texto "Ao resolver, diga quem continua o
  atendimento. Não há padrão: devolver ao agente por omissão o faria escrever de novo sem ninguém
  ter pedido." A API recusa resolver sem `return_to`.
- Só existe **um** encaminhamento aberto por oportunidade; repetir o pedido devolve o que já
  existe (`schema.sql`, `handoffs_aberto_uk`). Enquanto houver um aberto ou aceito, o agente
  apenas registra o que o cliente escreve (`HUMAN_IN_CONTROL`).

Vazio: "Ninguém esperando — A Mora encaminha quando o cliente pede uma pessoa ou quando a conversa
sai do que ela resolve."

### 3.7 Auditoria — `/auditoria` (só administrador)

Descrição: "Quem fez o quê, quando, e o que mudou." Item de menu e rota só aparecem para admin;
a API exige o scope `admin` (`App.tsx`; `api/routers/dashboard_rt.py`, `auditoria`).

Filtro "Todas as entidades" / Clientes / Oportunidades / Visitas / Encaminhamentos / Tarefas /
Imóveis (não vai para a URL). Mostra os 100 eventos mais recentes; não há paginação na tela
(`apps/crm/src/paginas/Auditoria.tsx`).

Cada evento: etiqueta **agente** (`service`) / **pessoa** (`user`) / **sistema**, nome do ator,
ação (ex.: `opportunity.transitioned`, `visit.confirmed`, `property.status_changed`), tipo da
entidade, quando, e o JSON de mudanças. A tabela é somente acréscimo: nada no código edita ou apaga
um evento (`schema.sql`, `audit_events`).

## 4. Papéis e permissões

Três tipos de ator (`services/crm/sdr_crm/api/auth.py`):

| Ator | Como entra | Scopes | `humano` |
|---|---|---|---|
| **admin** | sessão (cookie) | todos + `admin` | sim |
| **broker** (corretor) | sessão | todos, sem `admin` | sim |
| **reader** | sessão | só `crm:read` | não (só lê; existe no banco, não no seed) |
| **credencial de serviço** (Mora) | `Authorization: Bearer` | os concedidos ao emitir; padrão: `crm:read leads:write opportunities:write interactions:write visits:request tasks:write handoffs:write` | **não** |

Scopes disponíveis: `crm:read`, `leads:write`, `opportunities:write`, `interactions:write`,
`visits:request`, `tasks:write`, `handoffs:write`, mais `admin` só para papel humano
(`auth.py`, `SCOPES`, `POR_PAPEL`). **Scope não é autorização**: diz o que a credencial pode
pedir; o papel diz o que o ator pode fazer.

**`exigir_humano`** — ações que exigem corretor ou administrador, mesmo com o scope certo. A Mora
recebe `FORBIDDEN` (403) com a mensagem "'<ação>' é ação humana: exige corretor ou administrador."
Lista, com o arquivo onde está:

| Ação | Fonte |
|---|---|
| cadastrar imóvel, mudar a situação, alterar fotos, abrir horário | `imoveis_rt.py` |
| confirmar, concluir e marcar falta em visita | `visitas_rt.py` |
| cancelar visita já confirmada; remarcar visita confirmada | `visitas_rt.py` |
| assumir e resolver encaminhamento | `handoffs_rt.py` |
| liberar contato (qualquer política que não seja `blocked`); arquivar cliente | `leads_rt.py` |
| qualified/visit_scheduled → negotiation; negotiation → won/lost; qualquer → lost; reabrir won/lost | `dominio/funil.py`, `SOMENTE_HUMANO` |

**Admin vs broker.** O corretor vê tudo da imobiliária e opera o funil; a única diferença na tela é
a Auditoria, e na API o scope `admin` (`auth.py`, comentário em `POR_PAPEL`).

**O que a Mora nunca faz**: cadastrar ou alterar imóvel, mudar situação, abrir horário, confirmar
visita, marcar ganho/perdido, mover para negociação, liberar contato, arquivar, assumir ou resolver
encaminhamento, ler auditoria. Ela também não age quando o atendimento está `human_pending` ou
`human` — só registra interações recebidas (`HUMAN_IN_CONTROL`; `funil.py`, `avaliar`;
`visitas_rt.py`; `oportunidades_rt.py`). O painel nunca embute o token de serviço (`api.ts`).

## 5. Como as coisas entram no CRM

| Entidade | Agente (MCP) | Pessoa (tela do CRM) | Seed (`make crm-reset`) |
|---|---|---|---|
| Cliente | `criar_lead`, `atualizar_lead` (só bloquear contato) | liberar/bloquear contato, arquivar | 4 usuários + clientes `clienteNNNN@example.com` |
| Oportunidade | `criar_oportunidade`, `atualizar_preferencias`, `mover_oportunidade` (dentro do permitido) | mover pelo funil (inclusive ganho/perdido/negociação) | distribuídas por estágio |
| Interação | `registrar_interacao` | não (só leitura) | sim |
| Interesse em imóvel | `registrar_interesse` | não | — |
| Imóvel | **não** (só `buscar_imoveis`) | Novo imóvel, Mudar situação | acervo de `data/imoveis/imoveis.json` |
| Fotos | não | no cadastro | conforme acervo |
| Horário | não (só `consultar_horarios`) | Agenda do imóvel | sim |
| Visita | `solicitar_visita`, `cancelar_visita` (só solicitada) | confirmar, concluir, falta, cancelar, remarcar | solicitadas e confirmadas |
| Tarefa | `criar_tarefa` | não (só leitura na oportunidade) | sim |
| Encaminhamento | `encaminhar_para_corretor` | assumir, resolver | pendentes e aceitos |

Nomes das ferramentas: `services/crm/sdr_crm/mcp/ferramentas.py`. O seed é determinístico (seed
42, data de referência `CRM_REF`, padrão `2026-09-17T12:00:00Z`), marca tudo com `dataset_id`, e o
reset recusa apagar registro sem marca sintética (`Makefile`, alvos `crm-seed`/`crm-reset`;
`seed/__main__.py`). Só roda com `CRM_APP_ENV` em `development` ou `test` (`config.py`, `sintetico`).

## 6. Erros que o usuário pode ver

Formato único: mensagem, código e `request_id` (`erros.py`; `ui.tsx`, `Erro`). Guarde o
`request_id` ao reportar.

| Código (HTTP) | Quando aparece | O que fazer |
|---|---|---|
| `API_INACESSIVEL` (sem status) | "Não consegui falar com a API em http://localhost:8100…" — API fora do ar **ou** bloqueio de CORS (o navegador não distingue) | Confira `docker compose ps crm-api`. Se a API está no ar, o endereço do painel precisa estar em `CRM_ALLOWED_ORIGINS` (padrão: `http://localhost:3000` e `http://127.0.0.1:3000`) (`config.py`; `api/main.py`; `api.ts`) |
| `SESSAO_NAO_PERSISTIU` | login deu 200 mas a sessão não colou | Use o mesmo host no painel e em `VITE_CRM_API` (`Entrar.tsx`) |
| `UNAUTHENTICATED` (401) | "E-mail ou senha inválidos." / "Sessão expirada." / "Sessão encerrada." | Entre de novo; sessão dura 12 h |
| `RATE_LIMITED` (429) | mais de 10 tentativas de login por minuto (por IP ou por e-mail), ou mais de 120 chamadas/min por credencial | Aguarde `retry_after_seconds`. O contador é em memória, por instância (`contexto.py`) |
| `FORBIDDEN` (403) | ação humana pedida por credencial de serviço; scope ausente | Faça pela tela, logado como corretor/admin |
| `VERSION_CONFLICT` (412) | alguém alterou o registro entre a leitura e o clique (`If-Match` antigo) | Recarregue a tela e refaça; a tela do funil já sugere isso (`protocolo.py`, `conferir_versao`) |
| `PRECONDITION_REQUIRED` (428) | chamada sem `If-Match` (só por API direta; a tela sempre envia) | Leia o recurso e envie a versão |
| `INVALID_TRANSITION` (409) | mover para estágio/estado não permitido; `allowed` nos detalhes | Consulte a tabela da seção 3.2 ou 3.5 |
| `REASON_REQUIRED` / `QUALIFICATION_INCOMPLETE` / `VISIT_NOT_CONFIRMED` (409) | motivo faltando; faltam cidade/propósito/teto; sem visita confirmada futura | Preencha o que falta; `missing_fields` diz quais |
| `HUMAN_IN_CONTROL` (409) | agente tentou agir com atendimento humano | Resolva o encaminhamento (Devolver para a Mora) |
| `SLOT_UNAVAILABLE` (409) | confirmar/remarcar em horário que outra visita já ocupou | Escolha outro horário com o cliente |
| `BUSINESS_RULE` (409) | código duplicado de imóvel; visita confirmada futura ao sair do catálogo; sobreposição de horário do corretor; horário no passado; mesma situação | A mensagem diz a causa; corrija e repita |
| `CONTACT_BLOCKED` (409) | tarefa de contato para cliente bloqueado | Use tarefa interna ou libere o contato (humano) |
| `LEAD_CONFLICT` (409) | identificadores apontam para clientes diferentes | Revisão manual; não há merge automático |
| `VALIDATION_ERROR` (422) | corpo inválido: campo desconhecido, limite estourado, foto repetida, URL sem `http(s)://`, motivo ausente ao sair do catálogo, início ≥ fim | Corrija o campo apontado em `details` (`api/main.py`; `esquemas.py`) |
| `NOT_FOUND` (404) | id inexistente; horário que não pertence ao imóvel | Confira o link |
| `DEPENDENCY_UNAVAILABLE` (503) | banco fora **ou schema incompleto** ("tabela ausente") | Rode `cd local && docker compose up -d` — **não** `restart`: o `restart` não executa o `db-init`, que aplica o schema (`api/main.py`, `/health/ready`; `local/docker-compose.yml`, `db-init`) |

Outras situações:
- **`make seed` "sem CRM"**: `make seed` indexa o acervo na Mora; com o CRM configurado, ele vem do
  CRM via `crm-mcp`. Se o `crm-mcp` não estiver no ar ou `CRM_API_TOKEN` não estiver no `.env`, a
  indexação cai para o arquivo `data/imoveis/imoveis.json` (`Makefile`, alvo `seed`). Emita o
  token com `make crm-token` e suba `docker compose up -d crm-mcp agent`.
- **Corpo acima de 256 KB** é recusado (`config.py`, `corpo_maximo_bytes`).
- **Clique duplo** não duplica ação: cada clique envia uma `Idempotency-Key`, e a repetição da
  mesma requisição devolve a resposta original (`api.ts`; `contexto.py`, `executar`).

## 7. FAQ

**Cadastrei fotos no CRM e no painel da Mora; qual aparece na vitrine?**
A ordem é **painel > CRM > arquivo**, e é determinística: foto enviada pelo painel da Mora
sobrevive a qualquer reindexação; sem ela, valem as URLs do CRM; sem nenhuma, o que veio do
arquivo do acervo. Ver [ADR-0015](../adr/0015-quem-manda-nas-fotos-do-imovel.md).

**Cadastrei um imóvel e a Mora ainda não oferece. Quanto demora?**
O agente busca no índice dele, que é sincronizado com o CRM a cada **15 minutos**
(`SDR_ACERVO_REFRESH_S`, padrão 900 s; `services/scheduler/sdr_scheduler/local_worker.py`;
`services/ingestion/sdr_ingestion/sincronia.py`). Para não esperar, rode `make seed`. Só imóveis
`available` chegam ao índice.

**Marquei o imóvel como Reservado. A Mora para de oferecer na hora?**
No próximo ciclo de sincronização (ou `make seed`). Reservado e Indisponível são iguais para a
Mora: nenhum dos dois aparece. A diferença é para a equipe — Reservado volta a Disponível se a
proposta cair (`imoveis_rt.py`, `mudar_situacao`).

**Por que não consigo tirar um imóvel do catálogo?**
Há visita confirmada no futuro para ele. Cancele essa visita na tela de Visitas (remarcar não
resolve: a remarcação é sempre para outro horário do mesmo imóvel) e tente de novo.

**A Mora marcou uma visita sem ninguém confirmar?**
Não. Ela só **solicita**; a visita fica em "Solicitada" até um corretor clicar em **Confirmar**.
Solicitação não reserva horário (`visitas_rt.py`, `solicitar`).

**Perdi a senha do seed.**
A senha só aparece na execução que a criou. Não há tela de troca de senha ("não localizado" em
`paginas/`). Para gerar outra é preciso zerar `password_hash` do usuário no banco e rodar
`make crm-seed` de novo, que gera e imprime uma nova (`seed/__main__.py`, `_senha_de_bootstrap`).

**Por que "N clientes de olho" só aparece a partir de 2?**
Um cliente interessado é o normal; dois ou mais mudam a prioridade do corretor. Descartes não
contam (`imoveis_rt.py`, `_procura`).

**Onde vejo quem mudou a situação de um imóvel?**
Auditoria (admin), filtro "Imóveis", ação `property.status_changed`, com `de`, `para` e `reason`.

**Por que a ordenação diz que "vale para esta página"?**
O servidor pagina por cursor em ordem de criação e não ordena por outro critério; a tela só
reordena o que já carregou. Sem página seguinte, o aviso não aparece (`filtros.ts`, `ordenar`).

Regras de negócio completas: [regras-de-negocio.md](../technical-reference/regras-de-negocio.md).
Painel da Mora: [painel.md](painel.md).
