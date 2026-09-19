# ADR-0006 — Site vitrine (`apps/web`) com o agente embutido, ao lado do Telegram

**Status:** aceito (retroativo — valida uma decisão já implementada) · **Data:** 2026-09-11

## Contexto
A pergunta que motivou este ADR foi "vale a pena ter um site da imobiliária servindo de vitrine para os
imóveis, com a opção de uso do agente?". A resposta parte de um fato: `apps/web` já existe e já faz
isso — `Landing` (chat da Mora embutido + CTA do Telegram lado a lado), `Imoveis` (catálogo navegável)
e `ImovelDetalhe` (ficha do imóvel), com rastreamento de navegação (`viewed_imovel`, `filtered`,
`clicked_telegram`, `opened_chat`) via `POST /eventos`. Este ADR registra por que vale manter esse
canal — não é uma proposta de construir algo novo.

Sem o site, o único ponto de entrada é o canal de mensageria: exige que o visitante abra o bot (ou
clique num link `t.me`), não mostra catálogo navegável (fotos, filtro por preço/bairro, ficha do
imóvel) e não gera sinal de comportamento antes da primeira mensagem. Quando este ADR foi escrito
esse canal era o WhatsApp; o [ADR-0007](0007-telegram-em-vez-de-whatsapp.md) o trocou pelo Telegram,
e o argumento não muda — o texto abaixo já está atualizado para o canal de hoje.

**Não confundir com `apps/dashboard`.** São dois frontends com público e propósito opostos:

| | `apps/web` (este ADR) | `apps/dashboard` |
|---|---|---|
| Para quem | cliente/lead, público, sem login | corretor/admin, autenticado |
| O que mostra | vitrine de imóveis + chat do agente | funil de leads, temperatura, agenda, governança, auditoria |
| Papel do agente | conversa com o lead | nenhum — é onde o corretor acompanha o que o agente já fez |
| Como roda | container `web` do compose (Vite) | container `dashboard` do compose, atrás do token do painel |

O hint/paginação e a integração de calendário implementados nas rodadas anteriores são todos em
`apps/dashboard` — não têm relação com a decisão deste ADR, que é só sobre o canal do lado do cliente.

## Decisão
Manter e priorizar `apps/web` como canal de captação, com o agente acessível diretamente na página
(`ChatWidget`) e o Telegram como alternativa igualmente visível (`CtaTelegram`) — não como substituto
um do outro.

Arquiteturalmente, o site é só mais um canal sob o ADR-0003 (canais são adaptadores sem lógica de
negócio): o `ChatWidget` traduz para `MensagemNormalizada`/`RespostaAgente` como qualquer outro canal,
zero lógica de negócio nova, o mesmo agente responde. Na entrega de hoje ele é servido pelo container
`web` do `docker compose`, ao lado dos demais serviços — nada está implantado fora da máquina.

## Motivos
- **Reforça requisitos do hackathon que o canal de mensageria sozinho não cobre bem:** "integrar com base
  simulada de imóveis" fica concreto quando o lead navega o catálogo de verdade (`Imoveis`,
  `ImovelDetalhe`), não só quando o agente descreve um imóvel em texto.
- **Navegação é sinal de qualificação de graça.** `EventoNavegacaoRepository` já registra
  `viewed_imovel`/`filtered` por sessão assinada — dado comportamental que reforça "coletar informações
  relevantes" antes mesmo da primeira mensagem do lead.
- **Sem fricção de app instalado:** captura quem chegou por busca orgânica, anúncio ou link direto
  do corretor — tráfego que o bot não alcança sozinho.
- **Migração de canal sem perda:** alguém começa no chat do site e continua no Telegram (ou o inverso)
  preservando histórico via `lead_id`, cenário que só existe porque o site é um canal de verdade e não
  uma página estática à parte.
- **Custo marginal baixo:** é só mais um serviço Vite no compose, sem infraestrutura própria.

## Riscos e como já foram endereçados
Site público com evento aberto por sessão é vetor natural de abuso. Já mitigado, sem trabalho novo
necessário:
- Sessão assinada (`validar(session_id, token)`) — evento sem token válido é descartado em silêncio.
- Formato de evento fechado por regex/limites (`ID_IMOVEL`, `MAX_CAMPOS`, `MAX_VALOR`) em vez de campo livre.
- Mesmo rate limiter do agente (`vazao.py`) e CORS restrito (`SDR_CORS_ORIGINS`) valem para este canal,
  por passarem pelo mesmo `handler`.

## Gap identificado (não é decisão deste ADR, é trabalho futuro)
Os eventos de navegação são gravados mas o `qualificador` ainda não os lê ao montar o contexto do
card do lead — o agente reage ao que a pessoa digita, não ao que ela navegou antes de abrir o chat.
Fechar esse gap (citar na abertura da conversa o que o lead já viu) é uma melhoria de humanização
barata e correlata a este ADR, não uma consequência automática dele.

## Alternativas consideradas
- **Só o canal de mensageria, sem site:** mais simples, mas perde o catálogo navegável e o sinal de
  navegação; depende de o visitante já conhecer o bot.
- **Site institucional estático, sem o agente embutido (só formulário de contato):** perde a resposta
  imediata que é o diferencial da Mora; o lead sai do site sem qualificação nenhuma acontecendo.
