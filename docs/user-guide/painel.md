---
title: Manual do painel administrativo
description: Tela a tela do painel da Mora — login por token, tempo real, leads e handoff, corretores, fotos de imóveis, configurações do agente, governança de custos, auditoria e saúde — com rótulos, limites e regras copiados do código.
---

# Manual do painel administrativo

O painel é a interface da equipe sobre **como a Mora está atendendo**. Ele não é o CRM: ficha de
cliente, funil comercial em R$, agenda de visitas e oportunidades vivem no CRM (ver [CRM](crm.md)).
O que fica aqui é o que só a Mora sabe: conversas, qualificação, quem está com corretor, custo de
modelo e saúde do serviço.

> Nota técnica: rotas e menu em `apps/dashboard/src/main.tsx` e `apps/dashboard/src/components/Shell.tsx`;
> chamadas à API em `apps/dashboard/src/lib/api.ts`.

## Acesso e login

Endereço local: <http://localhost:5174>. A tela de login tem dois campos:

| Campo | O que fazer |
| --- | --- |
| **E-mail** | Só rótulo. Vem preenchido com `corretor@verticeimoveis.com.br`; o valor não é conferido. |
| **Token do painel** | O valor de `SDR_PAINEL_TOKEN` do `local/.env`. Placeholder: *em branco usa o dev-token*. |

Regras:

- O painel valida o token contra a API (`GET /config`) **antes** de guardá-lo. Token errado mostra
  **"Token do painel inválido"** ali mesmo, em vez de abrir o painel e cair em 401 na primeira tela.
- **Perfil local** (`SDR_PROFILE=local`) com `SDR_PAINEL_TOKEN` vazio: vale `dev-token`, que é o
  que o campo em branco envia.
- **Fora do perfil local**: sem segredo configurado, ninguém entra. O `dev-token` não é aceito.
- O token fica no `localStorage` do navegador. Não há expiração: revogar o acesso significa trocar o
  `SDR_PAINEL_TOKEN` e reiniciar os serviços.
- Qualquer resposta 401 da API redireciona para `/login`.
- **Sair** (ícone no canto superior direito) apaga o token do navegador.

Toda ação autenticada é registrada com o ator `corretor-dev` / `corretor@local` — o painel tem um
login único de equipe, não um por corretor.

> Nota técnica: `apps/dashboard/src/lib/auth.ts`, `services/api/src/api/auth.py`.

## Tempo real

O painel abre um WebSocket com o canal web (`VITE_WS_URL`, padrão `ws://localhost:8001/ws`) com
`papel=dashboard`. A credencial vai no **primeiro quadro** após abrir a conexão (`{"token": "..."}`),
nunca na URL. O servidor responde `{"evento": "pronto"}` quando aceita e fecha com código **4403**
quando recusa.

- Indicador no topo: **"ao vivo"** (ponto verde) depois do `pronto`; **"conectando…"** antes ou após
  uma queda. Título ao passar o mouse: *Conexão em tempo real com os canais*.
- Queda de rede reconecta em 2 s; credencial recusada espera 30 s antes de tentar de novo.
- Cada evento de mensagem invalida as consultas de leads, métricas, atividade, funil e notificações.
  Independentemente do WebSocket, as consultas se renovam a cada 15 s.
- O botão **Atualizar dados** (ícone de setas circulares) força a recarga de tudo.

> Nota técnica: `apps/dashboard/src/lib/ws.ts`, `services/channels/local/app.py`.

## Tema

O ícone de sol/lua no topo abre um menu com três opções:

| Opção | Dica exibida |
| --- | --- |
| **Claro** | Sempre claro |
| **Escuro** | Sempre escuro |
| **Sistema** | Acompanha o macOS/Windows |

**Sistema** é o padrão de quem nunca escolheu e acompanha o anoitecer sem recarregar a aba. A escolha
fica no navegador (`localStorage`), não na conta. O ícone do botão mostra o tema **em vigor**; o item
marcado no menu mostra a **escolha** — com "Sistema" à noite, o botão mostra a lua e a marca fica em
Sistema ([ADR-0014](../adr/0014-tema-claro-e-escuro-no-painel.md)).

## Menu e navegação

A barra lateral tem dois grupos. Ela pode ser recolhida (**Recolher menu** / **Expandir menu**) e a
preferência é lembrada no navegador; no celular vira um menu deslizante (**Abrir menu**).

| Grupo | Rota | Título |
| --- | --- | --- |
| Atendimento | `/` | Visão geral |
| Atendimento | `/leads` | Leads |
| Atendimento | `/leads/:id` | Lead (detalhe) |
| Atendimento | `/conversas` | Conversas |
| Administração | `/imoveis` | Imóveis |
| Administração | `/corretores` | Corretores |
| Administração | `/governanca` | Governança de IA |
| Administração | `/auditoria` | Auditoria |
| Administração | `/saude` | Saúde do sistema |
| Administração | `/configuracoes` | Configurações |

Endereços que saíram para o CRM continuam respondendo por redirecionamento: `/clientes` → `/leads`,
`/agenda` → `/`. Qualquer outra rota desconhecida volta à Visão geral.

Elementos comuns às tabelas: paginação com **10, 20, 50 ou 100** itens por página (o tamanho é
lembrado por tabela), texto **"Mostrando X–Y de N"**, e botões **Página anterior** / **Próxima página**.

### Notificações (sino)

O sino no topo mostra o número de avisos não lidos (**9+** acima de nove) e abre a lista **Avisos**.
Cada aviso leva à ficha do lead ao clicar e é marcado como lido. Há um botão **Marcar todos como lidos**.
Tipos de aviso: `lead.encaminhado`, `lead.respondeu`, `visita.agendada`, `briefing.pronto` e
`lead.transferido` (quando um corretor é desativado). Texto quando não há nada: *"Você é avisado
quando um lead for encaminhado, responder ou marcar visita."* No perfil local o login único vê os
avisos de todos os corretores. A lista se renova a cada 20 s.

> Nota técnica: `apps/dashboard/src/components/Notificacoes.tsx`, `services/api/src/api/routers/notificacoes.py`.

## Visão geral (`/`)

Descrição no cabeçalho: *"N leads atendidos pela Mora · N imóveis no índice"*. Seletor de período:
**7 dias**, **14 dias**, **30 dias**, **90 dias** (a API aceita de 1 a 90).

Indicadores do período, cada um com um botão de ajuda que explica o cálculo:

| Indicador | O que conta |
| --- | --- |
| **Leads novos** | Pessoas que iniciaram conversa no período, pela data de entrada. Comparação com a janela anterior de mesmo tamanho. |
| **Taxa de qualificação** | Dos leads do período, quantos estão hoje em *qualificado*, *agendado* ou *com corretor*. |
| **Visitas reservadas** | Horários que a Mora **reservou** no período. Reservado não é confirmado: quem confirma é o corretor, no CRM. |
| **Tempo de 1ª resposta** | Média entre a primeira mensagem do cliente e a primeira resposta. Queda aparece em verde. |
| **Encaminhados ao corretor** | Leads do período que estão **agora** com um corretor. Se foi devolvido à Mora, sai da conta. |

Demais blocos:

- **Leads por temperatura** — três cartões (Quente `score 60+`, Morno `score 30–59`, Frio
  `score < 30`) sobre a **base inteira**, não o período. Cada cartão filtra a lista de leads.
- **Atividade por dia · últimos N dias** e **Funil de leads** (com a taxa de visita).
- **Leads por região**, **Por intenção**, **Por canal**.
- **Reativação · avisos de imóvel novo** — janela fixa de 30 dias: **Avisos enviados**,
  **Responderam** (só quem voltou em até N h após o aviso), **Viraram visita**, **Pediram para sair**.
  Lista dos últimos avisos com o motivo que a Mora escreveu. Vazio: *"Nenhum aviso enviado ainda"*.
- **Prioridade agora** — até 6 leads quentes; **ver todos** abre `/leads?temperatura=quente`.
- **Atividade recente** — últimas mensagens dos canais (*disse* / *Mora respondeu* / *corretor respondeu*).

Pipeline em R$, ticket médio e valor em visitas não aparecem aqui: são leitura comercial, do CRM.

> Nota técnica: `apps/dashboard/src/pages/VisaoGeral.tsx`, `services/api/src/api/routers/dashboard.py` (`/dashboard/metricas`, `/dashboard/reativacao`).

## Leads (`/leads`)

Lista de todas as oportunidades atendidas pela Mora. Botão do cabeçalho: **Sincronizar CRM** — exporta
leads em *qualificado*, *agendado* ou *handoff* para um destino simulado e mostra **"CRM: N exportados"**.

Filtros (os três seletores ficam na URL, então o link pode ser compartilhado):

| Controle | Opções |
| --- | --- |
| Busca — *Buscar por nome, telefone, região…* | Filtra por nome, id, telefone, região ou intenção. |
| **Todos os estágios** | Novo, Qualificando, Qualificado, Visita reservada, Com corretor, Inativo, Frio |
| **Toda temperatura** | quente, morno, frio |
| **Todos os corretores** | Lista do cadastro |
| Ordenar | **Maior score**, **Mais recente**, **Nome** |
| **Limpar** | Aparece quando há filtro ativo |

O estágio interno `agendado` aparece como **Visita reservada**, e `handoff` como **Com corretor**.

Colunas: **Lead**, **Intenção**, **Região**, **Orçamento**, **Estágio**, **Temp.**, **Score**,
**Corretor**, **Canal**, **Último contato**. O score é colorido: vermelho a partir de 70, amarelo a
partir de 40. Um lead em handoff sem responsável aparece como **sem corretor** em amarelo.

### Como o lead é nomeado (`NomeLead`)

O id nunca ocupa a linha do nome. A ordem é: nome → telefone → descrição do canal (**Visitante do site**,
**Contato do Telegram** ou **Contato sem identificação**) mais os 4 últimos caracteres do id, em
itálico e apagado (*"Este lead ainda não disse o nome"*). O id completo só aparece na ficha do lead,
no chip **`IdCopiavel`**: clique para copiar; se o navegador não permitir (fora de HTTPS/localhost),
o chip vira um campo selecionável.

Listar a carteira é acesso a dado de cliente: a API registra `lead.listado` na auditoria no máximo
uma vez a cada 10 minutos por corretor e combinação de filtros.

> Nota técnica: `apps/dashboard/src/pages/Leads.tsx`, `apps/dashboard/src/lib/format.ts` (`nomeDoLead`), `services/api/src/api/routers/leads.py`.

## Lead — detalhe (`/leads/:id`)

Cabeçalho: nome, estágio, temperatura, canais com identificador (*Telegram: … · Site: …*), *entrou há X*,
o chip do id e uma faixa de leitura rápida com **Busca / Onde / Até / Quartos / Prazo** (ou, para
investidor, **Busca / Perfil / Ticket / Retorno**), além de **score**, **follow-ups** e **último contato**.
Se o cartão estiver vazio: *"Qualificação em andamento — a Mora ainda está descobrindo o que o lead busca."*

Quando a mesma pessoa já teve outras oportunidades, aparece a faixa **"Cliente recorrente — N
oportunidades no total"** com o link **ver a ficha do cliente** (que hoje redireciona para Leads; a
ficha da pessoa é do CRM).

### Conversa e handoff

A coluna **Conversa** mostra a transcrição (lead à esquerda; Mora e corretor à direita, com hora e
canal) e o estado: **"Mora respondendo automaticamente"** ou **"<Corretor> no comando · Mora em silêncio"**.

| Botão | Quando aparece | O que faz |
| --- | --- | --- |
| **Assumir conversa** / **Assumir como <Nome>** | Lead fora de handoff | Põe o lead em `handoff`, cancela o follow-up agendado e fixa o responsável: o corretor já vinculado → senão o roteamento por região e menor carga → senão fila da equipe. |
| **Enviar** (campo *Responder como corretor…*) | Só em handoff | Envia o texto por **todos** os canais do lead, sem passar pelo agente. Se o lead não tem canal vinculado, a API devolve 409 *"lead sem canal vinculado"*. |
| **Devolver à Mora** | Em handoff | Volta o lead para `qualificado` (cartão completo) ou `qualificando`. |

Fora do handoff o campo de resposta é substituído por *"Assuma a conversa para responder ao lead por aqui."*

!!! warning "Ações com efeito real"
    Assumir, responder e devolver enviam mensagens reais ao cliente. Enquanto está em handoff, a Mora
    não responde nada — inclusive a mensagens novas do lead.

### Abas

**Perfil**

- **Qualificação** — o cartão (`CartaoLead`): mostra só o que o lead já disse (Intenção, Região,
  Bairros, Orçamento, Quartos, Tipo, Prazo, Perfil de investidor, Ticket, Retorno esperado) e, em
  amarelo, **"Ainda falta perguntar:"** com os campos obrigatórios que faltam. Para compra/aluguel são
  intenção, região, orçamento, quartos e prazo; para investimento, intenção, perfil de investidor,
  ticket e retorno esperado. Também lista **Imóveis que viu no site** e **Pediu para visitar um imóvel**.
- **Briefing da Mora** — texto do resumo. Botão **Gerar** / **Atualizar**; enquanto processa, **Gerando…**
  e a nota *"o worker `resumidor` está processando"*. Se passar de 90 s sem resposta:
  *"O pedido foi enviado há X e não houve resposta. O serviço que gera o briefing (worker resumidor)
  provavelmente está parado — reinicie-o e peça de novo."* O briefing também é gerado sozinho quando o
  lead fica qualificado, agenda visita ou é encaminhado.

**Imóveis** — *"Imóveis desta conversa"*: cada vínculo lead↔imóvel com preço, motivo da sugestão e o
seletor de situação **Interessado**, **Descartado** ou **Visita marcada**. **Mora mostrou** (`sugerido`)
não pode ser escolhido de volta: a API recusa com 422 — para desfazer um descarte marque **Interessado**.
Marcar **Descartado** tira o imóvel das próximas sugestões da Mora; a mudança é publicada no CRM.

**Análise** — *Análise da conversa*: resumo do perfil, **Sentimento** (com tendência), **Engajamento**,
**Perfil de decisão**, **Confiança da leitura**, **Como se comunica**, **O que move a decisão**,
**Objeções e dúvidas**, **Sinais de alerta**, **Como abordar**. Rodapé: *"Leitura inferida do texto
da conversa pela Mora… Não é avaliação psicológica clínica."* Botão **Gerar análise** / **Atualizar**.

**Atendimento**

- **Corretor responsável** — seletor com os corretores **ativos** (*Sem corretor atribuído* quando
  vazio). Trocar aqui move também as visitas futuras. Corretor inativo é recusado pela API (422
  *"corretor inexistente ou inativo"*).
- **Avisos de imóvel novo** — interruptor **"A Mora pode avisar sobre imóveis novos"** /
  **"Não avisar — pedido do cliente"**, com *"último aviso há X"*. Vale só para o aviso proativo;
  não afeta follow-up nem respostas. A mudança é auditada (`lead.preferencia_reativacao`).
- **Acompanhamento** — Estágio, Temperatura, Score, Follow-ups enviados, Primeiro contato, Último contato.

Visitas não têm bloco próprio nesta tela: o horário reservado aparece na conversa e no CRM.

> Nota técnica: `apps/dashboard/src/pages/LeadDetalhe.tsx`, `components/{CartaoLead,AnaliseLead,Interesses}.tsx`, `services/api/src/api/routers/{handoff,leads,interesses}.py`.

## Conversas (`/conversas`)

Caixa de entrada: à esquerda os leads com mensagem, ordenados pela última (busca *Buscar conversa…*
por nome); à direita a transcrição do selecionado, renovada a cada 5 s, com **score** e *com a Mora* /
*com corretor*, e o link **abrir lead**. É somente leitura — responder é na ficha do lead. Vazio:
*"Assim que um lead escrever no site ou no Telegram, ele aparece aqui."*

## Imóveis (`/imoveis`)

Descrição: *"Catálogo indexado para o RAG da Mora — o que o agente pode oferecer aos leads"*. Alternância
**tabela** / **cards**. Indicadores sobre o recorte atual: **Imóveis no filtro**, **À venda**,
**Para alugar**, **Mediana venda**, **Mediana aluguel** (a base carrega até 200 imóveis por vez).

Filtros: busca *Buscar por código, bairro, descrição…*, **Venda e aluguel** (Venda / Aluguel),
**Todas as regiões**, **Todos os tipos** (Apartamento / Casa / Studio), **Quartos** (1+ a 4+), **Limpar**.
Colunas da tabela: **Código**, **Imóvel**, **Operação**, **Região**, **Quartos** (`Nq · Ns · Nv`),
**Área**, **Preço**, **Cond.**, **Detalhes**. Vazio: *"Rode `make seed` para carregar a base simulada
ou ajuste os filtros."*

### Cadastro e edição

Não há cadastro nem edição de imóvel no painel: a API expõe apenas leitura e gestão de fotos
(`services/api/src/api/routers/imoveis.py` não tem `POST`/`PUT` de imóvel). O cadastro é feito no
CRM ou pelo arquivo do acervo (ver [CRM](crm.md)).

### Ficha e fotos

O botão **Ver detalhes** abre a ficha: carrossel, preço (com **+ R$ cond.**), Quartos, Suítes, Vagas,
Área, R$/m², Cidade, **Descrição (texto que alimenta o embedding)**, **Quem está de olho** (interessados,
do mais quente ao mais frio, 5 por página, descartados fora) e **Quem a Mora avisaria** (ver Reativação).

Gestão de fotos:

| Ação | Regra |
| --- | --- |
| **Adicionar fotos** (ou arrastar) | *JPEG, PNG, WebP; reduzimos para 1280 px*. O navegador redimensiona antes de enviar; a API recusa outro formato (422) e imagem acima de **1,5 MB** (413 *"imagem acima de 1,5 MB — reduza antes de enviar"*). |
| Limite | **12 fotos** por imóvel. Excedentes na seleção: *"Limite de 12 fotos por imóvel — as excedentes foram ignoradas."* A API responde 409 ao passar do limite. |
| Capa | No carrossel, definir capa move a foto para a primeira posição (`PUT …/fotos` com a nova ordem; a lista precisa conter exatamente as fotos atuais). |
| Remover | Diálogo **Remover esta foto?** → **Remover foto**. Apaga do imóvel e do servidor; não pode ser desfeito. |

Precedência entre origens de foto ([ADR-0015](../adr/0015-quem-manda-nas-fotos-do-imovel.md)):
**painel > CRM > arquivo do acervo**. Enquanto o imóvel tiver ao menos uma foto enviada pelo painel
(`/fotos/…`), a reindexação preserva o conjunto do painel e as fotos do CRM não aparecem. Sem foto de
painel, valem as do CRM; sem nenhuma das duas, as do arquivo.

> Nota técnica: `apps/dashboard/src/pages/Imoveis.tsx`, `apps/dashboard/src/lib/imagem.ts`, `services/api/src/api/routers/imoveis.py`.

## Reativação (simulação e acompanhamento)

O aviso de imóvel novo é a única mensagem que a Mora manda sem ninguém ter escrito
([ADR-0013](../adr/0013-reativacao-proativa-de-leads-adormecidos.md)). No painel ele aparece em dois lugares:

- Na ficha do imóvel, o botão **Simular aviso de imóvel novo** mostra *"N de M leads seriam avisados"*
  (ou *"Nenhum lead seria avisado (M avaliados)"*), sempre com *"Simulação: nada é enviado."* Cada
  candidato traz pontos e os motivos que virariam a primeira frase da mensagem; **Ver N fora da lista**
  abre os excluídos com o motivo (por exemplo *"já recebeu um aviso nos últimos 7 dias"* ou
  *"conversou há menos de 3 dias"*). A simulação varre até 500 leads e lista até 50 candidatos.
- Na Visão geral, o bloco **Reativação · avisos de imóvel novo** (ver acima).

O opt-out por lead fica em **Lead → Atendimento → Avisos de imóvel novo**.

> Nota técnica: `apps/dashboard/src/components/{SimularReativacao,ReativacaoResumo}.tsx`, `services/api/src/api/routers/reativacao.py`, `shared/sdr_shared/reativacao.py`.

## Corretores (`/corretores`)

Descrição: *"Quem recebe os handoffs e as visitas — as regiões orientam o roteamento"*. Busca
*Buscar por nome, e-mail, telefone…* e contador *"N ativos · N no total"*.

Colunas: **Corretor** (nome e id), **Contato**, **Regiões** (*todas* quando vazio), **Em atendimento**
(link para `/leads?corretor=<id>&estagio=handoff`), **Visitas**, **Agenda** (ícone verde
*Google Agenda conectada* ou apagado *Usando a grade interna*), **Status** (interruptor ativo/inativo),
ações **Editar** e **Desativar <Nome>**.

### Formulário (**Novo corretor** / **Editar corretor**)

| Campo | Regra |
| --- | --- |
| **Foto do corretor** | *PNG, JPEG ou WebP; recortamos em quadrado e reduzimos para 256 px.* A API aceita `data:image/(png|jpeg|webp);base64` ou URL `https://` e recusa acima de **300 KB** (*"foto acima de 300 KB — reduza a imagem"*). Botões **Escolher arquivo** / **Remover**. |
| **Nome** | Obrigatório, mínimo 2 caracteres. Gera o id `cor_<slug>`; nome repetido devolve 409 *"já existe um corretor com esse nome"*. |
| **E-mail**, **Telefone** | Opcionais. |
| **ID no CRM** | `users.id` desta pessoa no CRM. Dica: *"Vazio: o encaminhamento fica na fila para quem aceitar."* |
| **Regiões que atende** | Zona Sul, Zona Oeste, Zona Norte, Zona Leste, Centro. *Sem seleção = atende todas.* |
| **Ativo (recebe handoffs e visitas)** | Interruptor. |
| **Google Agenda** | Só na edição: **Conectar agenda** abre a janela de consentimento do Google; **Desconectar** volta à grade interna (eventos já criados continuam no Google). Se `SDR_GOOGLE_CLIENT_ID`/`SDR_GOOGLE_CLIENT_SECRET` não estiverem configurados, aparece o aviso de integração não configurada e a Mora usa a grade interna. |

Botões: **Cancelar**, **Salvar** (desabilitado sem nome).

### Desativar e remover

O ícone de lixeira abre **Desativar <Nome>**. A tela consulta a carteira e mostra
**"Este corretor tem trabalho em aberto"** com *N leads em atendimento* e *N visitas futuras*, ou
*"Sem leads abertos nem visitas futuras. Nada a transferir."*

Campo **Para onde vai a carteira**: **Fila da equipe (sem dono, qualquer corretor assume)**,
**Distribuir automaticamente (por região e menor carga)** ou um corretor ativo específico.

- **Desativar corretor** marca `ativo = false`, move leads abertos e visitas futuras para o destino
  e cria um aviso `lead.transferido` por lead movido. O cadastro **não** é apagado; para reativar, use
  o interruptor da lista.
- **Apagar cadastro** só aparece com carteira vazia. A API recusa a remoção com carteira aberta (409).
- Recusas da API: destino inexistente (422), destino igual ao próprio corretor (422), destino inativo
  (422 *"<Nome> está inativo e não pode receber a carteira"*), carteira aberta sem destino (409).

> Nota técnica: `apps/dashboard/src/pages/Corretores.tsx`, `components/{DesativarCorretor,ConexaoAgenda}.tsx`, `services/api/src/api/routers/{corretores,calendario}.py`.

## Configurações (`/configuracoes`)

Descrição: *"Parâmetros da Mora. O follow-up vale no próximo turno do agente; as demais seções ainda
são declarativas."* Cada seção tem **Restaurar padrão**, **Descartar** e **Salvar alterações**; o selo
**personalizado** indica valor diferente do padrão e **salvo** confirma a gravação. A API recusa
campos desconhecidos (422 *"campos desconhecidos em <seção>"*).

### Persona do agente

**Nome do agente** (padrão Mora), **Empresa** (Vértice Imóveis), **Tom de voz** (*cordial e direto*),
**Máximo de frases por mensagem** (1–6, padrão 3), **Uso de emojis** (Nunca / Raros / Moderado),
**Apresentar-se sempre como assistente virtual, nunca como pessoa**.

### Follow-up automático

É a única seção lida pelo agente em tempo de execução hoje.

| Campo | Validação da API |
| --- | --- |
| **Follow-up automático ligado** | Desligado, *"a Mora só responde quando o cliente escreve"*. |
| **Tentativas** (minutos desde a última mensagem) | Ao menos 1 e no máximo **10**; cada uma **≥ 5 minutos**. |
| **Ritmo por temperatura** (Quente / Morno / Frio) | Multiplicador entre **0,05 e 10**. Menor que 1 volta mais cedo. |
| **Janela de envio** | `HH:MM`; o início precisa ser antes do fim (*"a janela precisa começar antes de terminar"*). |
| **Somente em dias úteis** | Interruptor. |

O quadro **Como está valendo agora** simula, para um lead morno, quando cada tentativa cairia com a
configuração **salva** — *"Salve para atualizar."*

### Agenda de visitas

**Horários oferecidos** (8h a 18h, clicar para ativar), **Duração da visita (min)** (mínimo 15, passo 15),
**Antecedência oferecida (dias)** (1–14), **Somente em dias úteis**. Padrão: 10h, 14h e 16h, 60 min, 5 dias.

### Área de cobertura

**Cidade** e **Regiões atendidas** (*"Fora dessas regiões a Mora avisa o cliente e sugere a mais próxima"*).

### Handoff para corretor

**Palavras que acionam o handoff** (separadas por vírgula; padrão `corretor, atendente, humano, pessoa de verdade`)
e **Encaminhar automaticamente leads quentes ao corretor**.

### Modelos de IA ([ADR-0010](../adr/0010-modelo-por-nivel-e-troca-pelo-painel.md))

Três níveis, cada um com **Provedor**, **Modelo** e **Testar**:

| Nível | Uso |
| --- | --- |
| **Conversa** | O que o cliente lê: qualificador, consultor e agendador. |
| **Roteamento e extração** | Supervisor e leitura do cartão. Roda em toda mensagem. |
| **Briefing e análise** | Resumo para o corretor. *Vazio = usa o de conversa.* |

Regras da tela e da API:

- **Provedor antes do modelo**: o provedor (`usa o do ambiente`, `anthropic`, `openai`, `ollama`) decide
  quais modelos existem. Trocar o provedor limpa um modelo que não exista na lista nova.
- A lista de modelos vem do catálogo do servidor **por provedor**, ordenada do mais barato para o
  mais caro, com o custo estimado ao lado (*"— US$ 0,0123"*, com *est.* quando ainda não há uso
  gravado). A opção **outro — digitar o ID…** abre campo livre; **voltar para a lista** desfaz.
- O botão de moedas abre o modal **Modelos para <papel>**: **US$ por 1M entrada · saída**,
  **Latência mediana** (das chamadas reais deste ambiente; *"— nunca usado aqui"* sem amostra),
  **Custo · N dias** ou **Custo estimado**, **Projeto usa para**. Clicar numa linha escolhe o modelo.
  Janela de contexto não aparece porque o projeto não guarda esse dado.
- **Testar** faz uma chamada real e curta (*"Responda apenas: ok"*) e mostra *"Respondeu em N ms"* ou
  *"Falhou: …"*. Trocar o modelo apaga o resultado do teste anterior.
- **Modelo sem preço é recusado** ao salvar (422): *"sem preço cadastrado para '<modelo>'. Cadastre em
  Configurações → preços antes de usá-lo, senão o custo é contabilizado como zero e o teto de orçamento
  para de valer."* O teste também avisa: *"Sem preço cadastrado… cadastre em Governança antes de salvar."*
- **Ollama dispensa preço** (roda local, sem custo) e não tem lista: *"vale o que a máquina baixou com
  `ollama pull`"*.
- ID com espaço ou acima de 120 caracteres: 422 *"não parece um identificador de modelo"*.
- **Provedor de reserva** (*Quem assume a queda*): `usa o do ambiente (.env)`, um provedor, ou
  **nenhum — sem reserva**. Reserva igual ao provedor da conversa é recusada (422).
- Salvar vale no próximo turno do agente; o cache de modelos é invalidado na hora. **Restaurar padrão**
  também vale imediatamente — é o caminho de recuperação de um modelo ruim.

A faixa **em uso agora: <modelo> · <provedor>** e o selo `painel` / `ambiente` mostram o que vale de
fato. **Vazio ≠ desligado**: campo vazio significa *usa o do `.env`* — o `.env` é o piso, e o painel
sobrepõe. Preços são cadastrados em **Governança de IA → Preços**.

### Operação

Aviso da seção: *"Campo vazio usa o valor do `.env`. Um valor explícito — inclusive 0 e desligada —
vale no próximo ciclo, sem reiniciar nada."*

| Campo | Validação da API |
| --- | --- |
| **Timeout do LLM (segundos)** | Entre **5 e 180** (*"Abaixo de 5 o modelo não termina de responder; acima de 180 o cliente já desistiu."*) |
| **Transcrição de áudio** | `usa o do ambiente`, **ligada (faster-whisper)** (`auto`), **desligada** (`off`). A API aceita `auto`, `whisper_local` ou `off`. |
| **Refresh do acervo (segundos)** | **0 desliga; mínimo 60** (*"abaixo de 60s a reindexação pega o worker ainda ocupado com o follow-up"*). Com 0 aparece o aviso: *"preço e status mudados no CRM só chegam ao índice com `make seed`."* |

Orçamento e ação ao estourar não ficam aqui: estão em **Governança de IA → Limites**.

### Canais e modelos (somente leitura)

**Chat do site**, **Telegram** (*bot @usuario* ou *"preencha SDR_TELEGRAM_BOT_TOKEN no local/.env"*),
**LLM · <provedor>** (conversa e roteamento) e **Embeddings · <provedor>**, com selos **configurado** / **pendente**.

> Nota técnica: `apps/dashboard/src/pages/Configuracoes.tsx`, `components/{ModelosForm,ComparacaoModelos,FollowupForm}.tsx`, `services/api/src/api/routers/config.py`.

## Governança de IA (`/governanca`)

Descrição: *"Quanto a Mora consome de modelos e tokens, quanto isso custa e os limites da operação"*.
A faixa do topo mostra o estado do agente e o modo (`normal`, `degradado`, `bloqueado`):

- *"Operando normalmente dentro do orçamento."*
- *"Consumo em N% do limite — perto do teto configurado."* (em alerta)
- *"Orçamento estourado: a Mora está respondendo com o modelo econômico (Haiku) até o próximo ciclo."* (degradado)
- *"Orçamento esgotado: a Mora não está chamando o modelo — novas conversas vão direto para um corretor."* (bloqueado)

### Consumo

Período **7 / 30 / 90 dias** (a API aceita 1–180). Indicadores: **Tokens**, **Custo do período**
(com equivalente em R$ pela cotação configurada), **Custo por lead atendido**, **Latência média**,
**Chamadas ao modelo**, **Tokens de entrada**, **Tokens de saída**, **Chamadas com erro**. Gráficos
**Tokens por dia** e **Custo por dia**; rankings **Por modelo**, **Por etapa do agente**, **Por papel**;
tabela **Chamadas recentes** (Quando, Etapa, Modelo, Entrada, Saída, Custo, Latência, Lead; linhas com
erro em vermelho).

### Limites

| Campo | Validação da API |
| --- | --- |
| **Orçamento mensal (US$)** | ≥ 0; *0 = sem teto* |
| **Teto de tokens por dia** | ≥ 0; *0 = sem teto* |
| **Alertar a partir de (%)** | 1 a 100 |
| **Cotação do dólar (R$)** | > 0 e ≤ 100; *usada só para exibir custos em real* |
| **Ao estourar o limite** | **Degradar para o modelo econômico**, **Apenas alertar (não muda o atendimento)**, **Bloquear e encaminhar ao corretor** |

Medidores **Orçamento do mês** e **Tokens de hoje** com a marca do alerta. Explicação da tela:
*Degradar* troca o modelo de conversa pelo econômico e, passando de 150% do limite, entrega a conversa
a um corretor; *Alertar* só avisa; *Bloquear* para de chamar o modelo e encaminha. **Salvar limites**
vale na hora para o agente.

### Preços

Tabela por modelo: **Entrada / 1M**, **Saída / 1M**, **Leitura de cache**, em US$ (com o equivalente
em R$). Editar salva entrada e saída (≥ 0); linhas alteradas ganham o selo **ajustado** e o botão
**Voltar ao preço padrão**. É esta tabela que libera um modelo para ser escolhido em Configurações.

> Nota técnica: `apps/dashboard/src/pages/Governanca.tsx`, `services/api/src/api/routers/governanca.py`.

## Auditoria (`/auditoria`)

Descrição: *"Trilha de tudo que muda o sistema e dos acessos a dados de clientes"*. Período
**7 / 30 / 90 dias** (a API aceita 1–365) e botão **Exportar CSV** (separador `;`, arquivo
`auditoria-<dias>d.csv`, até 5 000 linhas). A exportação é ela própria registrada (`auditoria.exportada`).

Indicadores: **Registros**, **Ações sensíveis**, **Ações com erro**, **Ações distintas**. A tabela
mostra no máximo os 300 registros mais recentes, então **Registros** pode ser maior que a lista.

Filtros: *Buscar por ator, id ou conteúdo*, **Todas as ações** (rótulos legíveis, por exemplo
*Corretor assumiu o lead*, *Foto de imóvel enviada*, *Limites de IA alterados*, *Agente bloqueado por
orçamento*), **Todas as entidades**, **Todos os atores** (Corretores / Mora / Sistema), **Só sensíveis**,
**Limpar**. Colunas: **Quando**, **Quem**, **Ação** (selo **sensível** quando for o caso), **Alvo**
(lead vira link para a ficha), **Resultado** (ok / erro), detalhes.

O detalhe abre um modal com Quando, Ator, Ação (rótulo e nome técnico), Entidade, Resultado, Origem,
a mensagem de erro (se houver) e os **Dados registrados** em JSON. Ações sensíveis são as que tocam
dado pessoal ou removem cadastro: a trilha registra que o acesso ocorreu; o conteúdo fica só no cadastro.

> Nota técnica: `apps/dashboard/src/pages/Auditoria.tsx`, `services/api/src/api/routers/auditoria.py`.

## Saúde do sistema (`/saude`)

Observabilidade leve, lida do Postgres ([ADR-0011](../adr/0011-observabilidade-leve-no-postgres.md)).
Período **6h / 24h / 72h** (a API aceita 1–168); a tela se renova a cada 15 s.

### Veredito

A faixa do topo diz **Operando normalmente**, **Degradado** ou **Com problema**, seguida dos motivos
que a produziram. Regras aplicadas na tela:

| Condição | Tom |
| --- | --- |
| Serviço sem batimento | problema — *"<serviço> sem dar sinal — mensagens ficam na fila sem ser processadas"* |
| p95 > 30 s | problema — *"1 em cada 20 clientes espera mais de Ns"* |
| p95 > 10 s | degradado — *"acima de 10s o cliente percebe"* |
| Turnos com falha > 10% / > 5% | problema / degradado |
| Fila > 50 / > 10 mensagens | problema / degradado |
| Provedor com erro > 20% / > 5% | problema / degradado — *"<provedor> recusou N% das chamadas"* |
| Nenhuma amostra de fila | degradado — *"o laço do scheduler não está gravando"* |

### Indicadores e gráficos

**Turnos atendidos**, **Espera típica (p50)**, **Espera ruim (p95)**, **Turnos com falha**, **Na fila agora**.

- **Espera por hora** — barra clara = volume, barra escura = p95, linha vermelha = falhas.
- **Espera por canal** e **Espera por estágio do lead** — p50 · p95 com barra relativa ao pior da tabela.
- **Onde o tempo está indo** — presença de cada nó do grafo nos turnos lentos vs. nos demais. É
  **presença, não duração**: o corte é o p95 do próprio período, não um limiar fixo.
- **Fila e conexões ao longo do tempo** — dois painéis (mensagens na fila e conexões no banco), pico
  por intervalo, amostrado a cada 30 s pelo scheduler.
- **Serviços** — batimentos de cada worker (*parado há N min* quando morto) e o que cada um conta de si.
- **Provedores de LLM** — chamadas, taxa de erro e p95 por provedor (*disponibilidade, não custo*).
- **Como cada turno terminou** — contagem por resultado (`ok`, `handoff`, falhas) e o pior caso do período.

> Nota técnica: `apps/dashboard/src/pages/Saude.tsx`, `components/chartsSaude.tsx`, `services/api/src/api/routers/dashboard.py` (`/dashboard/saude`).

## Clientes

A tela **Clientes** saiu do painel: `/clientes` redireciona para **Leads**. A ficha da pessoa — quem é,
quantas oportunidades tem, com quem já falou — é do CRM. As rotas `GET /clientes` e
`GET /clientes/{id}` continuam na API (`services/api/src/api/routers/clientes.py`) sem tela que as
consuma; no painel, o que resta é a faixa **Cliente recorrente** na ficha do lead.

## Segurança operacional

!!! danger "Não use credenciais reais"
    Gere o `SDR_PAINEL_TOKEN` como qualquer segredo forte
    (`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`) e mantenha-o só no `local/.env`.

- O painel só lê o WebSocket; toda escrita passa pela API autenticada e auditada.
- O token é compartilhado pela equipe e de longa duração — por isso nunca vai em URL.
- Regras de negócio que o painel aplica estão reunidas em
  [Regras de negócio](../technical-reference/regras-de-negocio.md); o fluxo do agente que essas telas
  observam está em [Fluxo do agente](../architecture/fluxo-agente.md).
