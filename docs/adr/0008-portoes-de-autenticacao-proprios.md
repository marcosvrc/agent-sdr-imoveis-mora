# ADR-0008 — Cada porta privada carrega o seu próprio portão

**Status:** aceito · **Data:** 2026-09-12

## Contexto
Uma varredura de segurança do repositório encontrou um furo grave e alguns menores, todos com a
mesma raiz: **o desenho assumia que havia um portão único na frente de tudo que é privado** — um
gateway com autenticação centralizada, herdado do tempo em que a entrega tinha alvo de nuvem — e
havia portas que não passavam por ele. Com a infraestrutura hospedada removida
([ADR-0002](0002-runtime-do-agente-em-container.md)), esse portão único não existe mais em lugar
nenhum, o que transforma a premissa errada em premissa impossível.

O caso concreto: o WebSocket do perfil local (`services/channels/local/app.py`) atende dois papéis
na mesma rota. `papel=lead` é o widget do site, autenticado pela sessão assinada
(`seguranca/sessao.py`). `papel=dashboard` é o painel do corretor, que recebe o **espelho de todas
as mensagens de todos os leads**. A verificação estava escrita como `if papel == "lead" and not
validar(...)`, então qualquer valor diferente de `"lead"` — inclusive um typo — pulava a validação e
caía no ramo do painel. Bastava abrir `ws://host:8001/ws?papel=dashboard` para ler nome, telefone,
orçamento e conversa inteira de todos os leads, sem credencial nenhuma. Pior: a guarda que impede
uma conexão de falar pela sessão de outro (`if papel == "lead" and body.get("session_id") != id`)
tinha o mesmo formato, então essa conexão também podia **publicar mensagens no nome de qualquer
lead**, alimentando o agente e envenenando o cartão de qualificação.

Dois outros achados na mesma família:
- O `state` do OAuth do Google Agenda era o `corretor_id` em texto puro, e o callback só conferia se
  aquele corretor existia. Como o id é derivado do nome (`cor_ana-souza`), quem adivinhasse podia
  rodar o consentimento com a própria conta Google e sobrescrever a credencial do corretor — dali em
  diante as visitas dele seriam criadas na agenda do atacante.
- A mesma página de callback interpolava o parâmetro `error` cru no HTML: XSS refletido num endpoint
  público.

## Decisão
**Toda porta privada carrega o seu próprio portão, e ele nega por padrão.**

1. `papel` no WebSocket vira lista fechada (`{"lead", "dashboard"}`). Valor desconhecido fecha a
   conexão em vez de escorregar para um ramo permissivo. A guarda de escrita passou a ser
   `if papel != "lead" or ...`: painel ali é somente leitura, e quem responde ao cliente é o
   `/handoff` da API, que é auditado.
2. `papel=dashboard` exige credencial da equipe, validada por `seguranca/painel.py`. A credencial
   sai de `SDR_PAINEL_TOKEN`; **vazia, só vale no perfil local** (cai em `dev-token`), e fora dele
   não vale nada — fail-closed. A API passou a usar a mesma função, para não existirem duas
   verdades sobre "quem é da equipe".
3. O `state` do OAuth passa a ser assinado com prazo de 10 min (`seguranca/oauth.py`), reusando a
   chave HMAC da sessão. O callback só aceita `state` emitido por nós, para aquele corretor.
4. `_pagina()` do callback escapa o que interpola.

Junto, duas correções de mesma natureza encontradas na varredura: `notificacoes.marcar_lida` não
filtrava por dono (o id é sequencial — dava para marcar o aviso de outro corretor iterando números),
e nome/telefone/e-mail e os campos livres do cartão passaram a ser limpos de caracteres de controle
e limitados em tamanho no próprio modelo (`models/lead.py`), porque são interpolados no prompt de
sistema **fora** do envelope de conteúdo não confiável de `prompts/__init__.py` — uma quebra de
linha ali faz o texto do cliente parecer uma instrução nova.

## Consequências
- (+) O painel deixa de ser uma porta aberta na rede local; em uma demo com o serviço exposto (o
  compose publica em `0.0.0.0`), isso era vazamento de dado pessoal de todos os leads.
- (+) Fora do perfil local, fica fail-closed por construção: sem `SDR_PAINEL_TOKEN`, nada entra.
  É a única coisa que `SDR_PROFILE` ainda decide, e é por isso que ele continua no código.
- (−) O painel agora precisa do token na conexão WebSocket (`apps/dashboard/src/lib/ws.ts` manda o
  mesmo token do `localStorage`). Quem subir o ambiente com o `local/.env` antigo não precisa mudar
  nada: sem `SDR_PAINEL_TOKEN`, o perfil local continua aceitando `dev-token`.
- (−) O link de consentimento do Google agora expira em 10 min; conectar a agenda exige clicar em
  "conectar" e concluir na sequência, não reaproveitar um link velho.

## O que esta ADR NÃO resolve
A varredura também mostrou que **não existe separação entre corretores**: qualquer corretor
autenticado lê e altera os leads, clientes, visitas e configurações de todos, e `/config`,
`/governanca` e `/corretores` não distinguem admin de corretor comum. Isso é uma decisão de modelo
de permissão, não um bug pontual, e continua em aberto — aceitável enquanto a POC representa uma
imobiliária de escritório único, mas é o próximo passo antes de qualquer uso real com mais de uma
equipe. Também segue em aberto: o token da sessão do chat trafega na querystring do WebSocket (vai
para log de proxy), e `POST /sessao` não tem limite por IP (o teto de gasto hoje é o guardrail de
orçamento, não o de sessões).
