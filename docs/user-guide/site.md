---
title: Manual do site
description: Rotas, busca e filtros, ficha do imóvel, widget de chat (sessão, conversa restaurada, reconexão, botões, recibos), eventos de navegação, Telegram, PWA, acessibilidade e SEO do site vitrine da Vértice Imóveis.
---

# Manual do site

O site é a vitrine pública da Vértice Imóveis com a Mora embutida: catálogo, ficha de imóvel e um
widget de chat que fala com o mesmo agente do Telegram. Não exige login. Endereço local:
<http://localhost:5173>.

> Nota técnica: `apps/web/src/main.tsx` (rotas), `apps/web/src/lib/api.ts` (API), `apps/web/src/chat/` (widget).

## Rotas

| Rota | Página |
| --- | --- |
| `/` | Início: busca (**Bairro, região ou palavra-chave**, botão **Ver imóveis**), **Imóveis em destaque**, **Você viu recentemente** (até 8 imóveis, guardados no navegador), **Prefere continuar no Telegram?** |
| `/imoveis` | Catálogo com filtros na URL (`?operacao=venda&bairro=…`) |
| `/imoveis/:operacao/:bairro` | Página fixa por bairro e operação (ex.: `/imoveis/venda/perdizes`), feita para ser indexada |
| `/imovel/:slug` | Ficha do imóvel; o slug termina com o código (`apartamento-2-quartos-perdizes-sp-0001`) |
| `/imoveis/:id` | Endereço antigo da ficha — redireciona para `/imovel/<id>` |
| `/favoritos` | **Meus favoritos**, guardados no navegador (`localStorage`, chave `sdr_favoritos`) |
| `/privacidade` | **Privacidade e uso de dados** |
| qualquer outra | Página não encontrada |

Só a página inicial entra no pacote inicial; as demais carregam quando abertas. O rodapé leva a
**Catálogo completo**, **Privacidade e uso de dados** e **Meus favoritos**.

## Busca e filtros (`/imoveis`)

A busca chama `GET /imoveis/busca`, que devolve a página, o **total** (para escrever *"38 imóveis
encontrados"*) e a lista de bairros com contagem. Página de **12** itens, com **Anterior** / **Próxima**
e *"Página N de M"*. A página fica na URL (`pagina`, começando em 1): voltar da ficha de um imóvel
retorna à mesma página, e o link pode ser compartilhado. Trocar filtro ou ordenação volta para a
página 1 numa única busca. `pagina` inválida (texto, zero, negativa) vira a 1ª; acima da última, leva
à última.

Barra de filtros (**Filtros de busca**):

| Controle | Valores | Parâmetro |
| --- | --- | --- |
| **Bairro, tipo ou palavra-chave** | texto livre, com autocompletar de bairros; espera 350 ms após parar de digitar | `texto` (até 80 caracteres) |
| **Operação** | Comprar ou alugar / **Comprar** / **Alugar** | `operacao` = `venda` \| `aluguel` |
| **Para** | **Tudo** / **Para morar** / **Para o negócio** | `segmento` = `residencial` \| `comercial` |
| **Tipo** | a lista muda com o segmento: residencial (Apartamento, Casa, Sobrado, Studio, Kitnet, Cobertura) ou comercial (Sala comercial, Conjunto comercial, Loja, Galpão, Laje corporativa); em **Tudo**, os dez | `tipo` |
| **Mais filtros** → **Região** | Toda a cidade / Zona Sul / Zona Oeste / Zona Norte / Zona Leste / Centro | `regiao` |
| **Quartos (mínimo)** | Qualquer, 1+ a 4+ — **oculto em "Para o negócio"** | `quartos` (0–10) |
| **Suítes (mínimo)**, **Vagas (mínimo)** | Qualquer, 1+ a 3+ — **ocultos em "Para o negócio"** | `suites`, `vagas` (0–10) |
| **Preço mínimo**, **Preço máximo** | número, passo de R$ 50 000 | `preco_min`, `preco_max` (≥ 0) |
| **Área mínima (m²)** | número | `area_min` (≥ 0) |
| **Bairro exato** | lista com contagem | `bairro` |
| **Ordenar por** | **Mais relevantes**, **Menor preço**, **Maior preço**, **Maior área** | `ordenar` = `relevancia` \| `preco_asc` \| `preco_desc` \| `area_desc` |

Trocar o segmento **zera o tipo escolhido**: "Studio" não existe no comercial, e um tipo do outro
segmento devolveria lista vazia sem explicar por quê. Em **Para o negócio** os campos de quartos,
suítes e vagas saem da tela — sala comercial e galpão se medem em metros, e a **Área mínima** é o
critério de tamanho que vale.

Filtros ativos viram chips removíveis (*Operação: Comprar*, *Até: R$ 800.000*…) com **Limpar todos**.
Sem resultado: **"Nenhum imóvel com esses filtros"**, com **Perguntar à Mora** (abre o chat) e
**Limpar filtros**. `ordenar` na URL fora da lista é ignorado pelo site (vale **Mais relevantes**);
a API, por sua vez, recusa ordenação fora da lista (422 *"ordenação inválida"*).

O título da página descreve a busca (*"Apartamentos de 2+ quartos à venda em Perdizes"*). Uma
combinação livre de filtros recebe `noindex`; só as páginas de bairro são indexadas.

> Nota técnica: `apps/web/src/pages/Imoveis.tsx`, `apps/web/src/components/Filtros.tsx`, `services/api/src/api/routers/imoveis.py` (`/imoveis/busca`).

## Ficha do imóvel (`/imovel/:slug`)

Título canônico *"Apartamento de 2 quartos em Perdizes"* (o código de cadastro não aparece no título).
Galeria com **Foto anterior** / **Próxima foto**, contador *"foto N de M"*, miniaturas e tela cheia
(**Fechar galeria**). Blocos: **Sobre o imóvel**, **O que tem por perto** (pontos de referência do
bairro), **Custo mensal** e **Simulação de financiamento** (estimativas locais, sem envio de dados),
imóveis **parecidos**, botões **Compartilhar** e favorito.

Chamadas para a conversa:

- **Falar sobre este imóvel** — abre o widget já com o contexto do imóvel (ver `imovel_origem`).
- **Continuar no Telegram** — abre `https://t.me/<bot>?start=IMOVEL-<id>`.
- No celular, uma barra fixa repete as duas ações.

Abrir a ficha registra o evento `viewed_imovel` e guarda o imóvel em **Você viu recentemente**.

> Nota técnica: `apps/web/src/pages/ImovelDetalhe.tsx`, `apps/web/src/lib/vistos.ts`.

## Widget de chat

O botão flutuante **Abrir conversa com a Mora**, com o retrato ilustrado da Mora, fica em todas as
páginas; após 5 s sem abrir, aparece o convite *"Posso ajudar a achar o imóvel certo — me conta o
que você procura?"*. O painel é um diálogo (**Conversa com a Mora, assistente virtual**): Escape
fecha e o foco volta ao botão. A conversa sobrevive à navegação entre páginas — o widget só monta (e
conecta) na primeira abertura e, daí em diante, **fica conectado com o chat fechado**: fechar só
esconde o painel. A resposta que chega com o chat fechado já está lá ao reabrir, uma vez só.
Trocar de imóvel com o chat aberto também mantém a mesma conexão; a próxima mensagem leva o imóvel
novo como `imovel_origem`.

Acessibilidade: **expandido no celular** (tela cheia), o painel é um diálogo modal
(`aria-modal="true"`) e o Tab circula só dentro dele; no computador, expandido ou não, é um painel
ao lado da página e não prende o foco. O leitor de tela anuncia **só a fala nova** da Mora (e avisos
de falha) — a conversa restaurada do histórico não é lida em sequência.

### Aparência e uso

- **Cabeçalho** com o retrato da Mora, "assistente virtual" e o estado da conexão; botões
  **Expandir/Reduzir o chat** (a preferência fica no navegador) e **Fechar** (a conversa continua
  salva). O retrato também acompanha a última bolha de cada sequência da Mora, junto com o horário.
- **Atalhos na abertura**: **Comprar**, **Alugar** e **Investir**; aberto a partir de uma ficha, a
  saudação já cita o imóvel e os atalhos são **Me conte mais sobre ele**, **Ver opções parecidas** e
  **Agendar visita**.
- **"Digitando"** com três pontos animados (respeita *reduzir movimento*).
- **Rolagem que não arrasta quem está lendo**: se a pessoa subiu na conversa, a resposta nova não a
  puxa para baixo — aparece o botão **Nova mensagem ↓**.
- **Campo multilinha**: cresce até cerca de 5 linhas; Enter envia, Shift+Enter quebra a linha;
  limite de **1 000 caracteres**, com contador nos últimos 150.
- **Falar com um corretor** fica sempre visível sob o campo, não só quando algo dá errado.
- Mensagem que falhou ganha o botão **Tentar de novo**, que reenvia exatamente o mesmo conteúdo.

### Conversa restaurada ao recarregar

Ao abrir, o widget pede `POST /historico` ao canal web com a própria sessão (`session_id` e `token`
no corpo, nunca na URL) e redesenha as últimas **60** mensagens daquela sessão no canal web — falas
do cliente, da Mora e do corretor, com os cartões de imóvel. Os botões de opção só voltam na última
mensagem da Mora (os anteriores já foram respondidos). Sessão inválida recebe 401 e lista vazia; sem
histórico, a conversa segue do ponto em que está.

Uma resposta que chegou enquanto a página recarregava vem duas vezes — no histórico e na
reentrega dos pendentes do canal. O widget funde as duas: o histórico é a base e, do que chegou ao
vivo enquanto ele carregava, só fica o que ele ainda não tem (mesmo autor e mesmo texto, nos últimos
10 minutos).

> Nota técnica: `apps/web/src/lib/historico.ts`, `services/channels/local/app.py::historico`
> (`test_app.py::test_historico_devolve_a_conversa_da_propria_sessao`,
> `::test_historico_de_sessao_inventada_nao_le_nada`).

**Modo de teste** (`SDR_CHAT_NOVA_CONVERSA=true` no `local/.env`): a sessão vive só em memória, cada
carregamento da página é um cliente novo e o cabeçalho mostra o botão **Nova conversa**. Em produção
fica desligado. Ver [Configuração](../getting-started/configuracao.md).

### Sessão emitida pelo servidor

Antes de conectar, o widget pede `POST /sessao` ao canal web (`VITE_CANAL_URL`, padrão
`http://localhost:8001`). O servidor emite `session_id`, um `token` assinado e `expira_em`
(validade de 12 horas). A sessão fica no `sessionStorage` da aba (chave `sdr_sessao`): recarregar a
página mantém a conversa; fechar a aba ou expirar inicia outra. O navegador nunca escolhe o próprio id — sem isso bastaria saber o
id de outro visitante para ler a conversa dele. O WebSocket abre em `VITE_WS_URL?papel=lead`, **sem
credencial na URL** (URL vai para log de proxy e de acesso): o primeiro quadro é
`{"session_id": …, "token": …}`, e o servidor responde `{"evento": "pronto"}`. Só depois do `pronto`
o widget mostra **online** e envia a fila. Sessão inválida ou expirada — ou silêncio por 5 s — é
fechada com código **4401**; o widget então descarta a sessão guardada e pede outra (antes, ficava
*"reconectando…"* para sempre com o mesmo token). A sessão em memória também é conferida contra
`expira_em` antes de cada conexão.

O canal limita o uso (contagem na memória do processo do canal):

| Limite | Valor | Ao passar |
| --- | --- | --- |
| Sessões novas (`POST /sessao`) por IP | 20 por hora | 429 com `Retry-After`; o widget tenta de novo com espera crescente |
| Mensagens por sessão | 15 por minuto | `falha_envio` *"Recebi muitas mensagens em pouco tempo…"* com **Tentar de novo** |
| Mensagens por IP (todas as sessões) | 200 por hora | idem |
| Tamanho do quadro | 8 KiB | conexão fechada com 1009 |
| Texto | 1 000 caracteres | `falha_envio` pedindo para resumir |

### Conexão, reconexão e pendentes

- Cabeçalho: ponto verde e **online**, ou ponto âmbar e **reconectando…**, sobre o retrato (o texto
  acompanha a cor).
- Queda de conexão reconecta com espera crescente: 1 s, 2 s, 4 s… até 15 s.
- Mensagens digitadas offline entram numa fila local e são enviadas na reconexão; o campo mostra
  *"Sem conexão — enviaremos ao reconectar"*. Nada é descartado em silêncio. O `session_id` é
  preenchido no envio real, com a sessão da conexão aberta — inclusive para o que foi digitado antes
  de existir sessão. Mensagem com `session_id` diferente do da conexão recebe `falha_envio`
  (*"Sua conversa foi renovada…"*), não some.
- Respostas da Mora que chegaram com o visitante offline (refresh, queda) ficam guardadas no servidor
  por 10 minutos e são entregues ao reconectar com a mesma sessão.

### Recibos: `recebido` e `falha_envio`

Cada envio leva uma referência (`ref`). O servidor responde `{"evento": "recebido", "ref": …}` assim
que enfileira a mensagem — só então o widget mostra o *"…"* de digitação, e só para o `ref` da última
mensagem enviada (offline, sem `recebido`, não há "digitando"). Se não conseguir enfileirar,
responde `{"evento": "falha_envio"}` e o widget exibe **"Não consegui registrar sua mensagem. Pode
tentar de novo?"** com o botão **Tentar de novo**. Quadro ilegível vindo do servidor é ignorado sem
derrubar a conexão.

Espera pela resposta: após 10 s aparece *"Ainda estou procurando as melhores opções para você…"*;
após 60 s, *"Desculpe a demora — estou com dificuldade para responder agora. Um corretor pode te
atender na hora:"* com **Falar no Telegram** (`?start=humano`, palavra-gatilho de handoff) e
**Tentar de novo aqui** (envia *"Quero falar com um corretor"*).

### Botões de opção e cartões

A Mora pode responder com **opções** (por exemplo **Agendar visita**, **Ver outros**, **Falar com
corretor**). Clicar envia o id da opção como mensagem de botão — o mesmo contrato do Telegram. Horários
(`slot:<data>|ter 15/09 às 14h`) são agrupados por dia. Também aparecem cartões de imóvel (foto,
título, preço, motivo) e, após a reserva, o cartão **Horário reservado** com *"O corretor confirma
com você antes do dia."* e **Adicionar ao Google Agenda** / **Apple / Outlook (.ics)**. O cartão diz
*reservado*, nunca *confirmado*. Quando há imóveis na tela e o cliente pede visita, a Mora pergunta
antes **qual deles** (um botão por imóvel); escolhido o horário sem telefone informado, ela segura o
horário e pede nome e telefone antes de reservar. Sem imóvel no bairro pedido, ela oferece botões
para **ampliar a busca** (acima do valor, bairros vizinhos, menos quartos). O cartão da visita traz o
botão **Ver a região no mapa** (bairro, nunca endereço).

### Limites de texto

O campo do widget aceita até **1 000 caracteres**, e o canal web recusa acima disso (ver a tabela
de limites acima). Do `meta` que o navegador manda, o canal só repassa ao agente `imovel_origem`
(no formato de id de imóvel, `[A-Za-z0-9_-]{1,64}`) e `saudacao_exibida`; `botao` vira o tipo da
mensagem e qualquer outra chave (inclusive `nome` e `telefone`) é descartada. Do lado do servidor, o contrato de entrada do
agente trunca o conteúdo em **4 000 caracteres** (`MAX_CONTEUDO`) e remove caracteres de controle e
invisíveis; acima de 1 200 caracteres a mensagem é recusada pelo porteiro de escopo com o pedido de
resumir (ver [Manual do agente](agente.md)) — limites que valem para qualquer canal. Sob o campo de
texto: *"Seus dados servem só a este atendimento."*, com o link **Como tratamos**.

> Nota técnica: `apps/web/src/chat/ChatWidget.tsx`, `apps/web/src/lib/{ws,session}.ts`, `services/channels/local/app.py`, `shared/sdr_shared/messaging/contracts.py`.

## Eventos de navegação e `imovel_origem`

O site envia telemetria mínima a `POST /eventos`, sempre acompanhada da sessão assinada — sem ela o
servidor descarta em silêncio. Tipos: `viewed_imovel`, `filtered`, `clicked_telegram`, `opened_chat`.
O payload é fechado: `imovel_id` precisa casar com `^[A-Za-z0-9_-]{1,64}$`, no máximo 12 campos e
200 caracteres por valor.

Esses eventos alimentam o cartão do lead: os imóveis vistos aparecem em `imoveis_visualizados`.
Quando o visitante clica **Falar sobre este imóvel**, cada mensagem do widget leva `meta.imovel_origem`
com o código do imóvel — a saudação já nasce falando dele (*"Vi que você está de olho no apartamento
em Perdizes, por R$ …"*) e o agente registra o interesse como **declarado** (origem `site`), diferente
de apenas ter passado pela ficha. Se o chat já estiver aberto e a pessoa clicar em outra ficha, uma
bolha avisa a mudança de contexto em vez de reiniciar a conversa.

> Nota técnica: `apps/web/src/lib/tracking.ts`, `apps/web/src/store/chat.ts`, `services/api/src/api/routers/eventos.py`.

## Telegram

Os botões **Continuar no Telegram** apontam para `https://t.me/<VITE_TELEGRAM_BOT_USERNAME>` (padrão
`mora_vertice_bot`). Com `?start=IMOVEL-<id>`, o bot lê o código no `/start` e a Mora abre falando
daquele imóvel; com `?start=humano`, a primeira mensagem já aciona o handoff. O histórico do site
**não** é transferido para o Telegram: o que passa é o contexto do imóvel, não a conversa.

> Nota técnica: `apps/web/src/components/CtaTelegram.tsx`, `services/channels/telegram/canal_telegram/adapter.py`.

## PWA

O site pode ser instalado como aplicativo (`vite-plugin-pwa`, atualização automática): nome
**Vértice Imóveis**, nome curto **Vértice**, ícones de 192 e 512 px (com variante *maskable*),
`display: standalone`, `start_url: /`. Sem JavaScript, a página mostra um aviso pedindo para ativá-lo
ou falar pelo Telegram.

## Acessibilidade e SEO ([ADR-0012](../adr/0012-vitrine-encontravel-e-acessivel.md))

Acessibilidade:

- Rótulos em todos os controles e botões de ícone (**Abrir menu**, **Ver foto N**, **Remover filtro …**).
- O chat é `role="dialog"`; a lista de mensagens é `role="log"` com `aria-live="polite"`, então o
  leitor de tela anuncia as respostas. Estado da conexão em texto, não só em cor.
- Contagem de resultados em `aria-live`; convite do chat respeita *reduzir movimento*.
- `npm run a11y` roda axe-core (WCAG 2.2 AA) nas rotas principais — cobre cerca de um terço dos
  problemas; ordem de foco e clareza de rótulo seguem em teste manual.

SEO:

- Cada rota reescreve `title`, `description`, `canonical`, Open Graph e Twitter Card
  (`apps/web/src/lib/seo.ts`); o build grava as mesmas tags no HTML de cada rota indexável
  (`apps/web/scripts/gerar-paginas.mjs`) para rastreadores que não executam JavaScript.
- JSON-LD: `RealEstateListing` com `Offer` e `Apartment`/`House` na ficha; `BreadcrumbList` no
  catálogo e na ficha; `RealEstateAgent` para a organização — só com campos reais, sem CRECI ou
  telefone inventados (os dados institucionais são placeholders marcados como tal).
- `sitemap.xml` gerado no build com a home, o catálogo, a página de privacidade, uma página por
  **bairro × operação** e uma por ficha. `robots.txt` libera tudo e bloqueia `/favoritos`.
- Páginas de bairro: `/imoveis/<venda|aluguel>/<bairro-em-slug>` com título e descrição próprios.

Quando o catálogo não estiver no ar durante o build, o script gera só as rotas fixas e avisa — o
build não quebra.
