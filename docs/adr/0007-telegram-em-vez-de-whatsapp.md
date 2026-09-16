# ADR-0007 — Telegram substitui WhatsApp como canal externo ativo

**Status:** aceito · **Data:** 2026-09-11

## Contexto
O WhatsApp Cloud API (Meta) exige criar um app no Meta for Developers e, para uso além do número de
teste, verificação de negócio — processo que travou na prática (conta recusada/pendente). Isso bloqueava
qualquer teste de ponta a ponta pelo canal de mensageria além do chat do site.

## Decisão
`services/channels/telegram` (novo, mesmo contrato do ADR-0003) substitui `services/channels/whatsapp`
como canal ativo no perfil local. Um bot do Telegram é criado na hora, falando com **@BotFather** —
sem app review, sem verificação de negócio, sem prazo de espera.

Além disso, o perfil local passa a usar **long polling** (`getUpdates`) em vez de webhook: o worker
`telegram-in` puxa mensagens ativamente, então não precisa de URL pública nem do túnel cloudflared que
o webhook do WhatsApp exigia (`tunnel` saiu do compose). Isso também simplifica o ambiente de
desenvolvimento — um serviço a menos no ar, uma dependência de rede a menos.

O adapter do WhatsApp **não foi apagado** — só saiu do `docker-compose.yml` local. `Canal.WHATSAPP`
continua no enum, os testes continuam passando, e religar é reabilitar o serviço no compose e
preencher `SDR_WHATSAPP_*`, se um número de negócio verificado aparecer depois.

## O que muda para quem usa o sistema
- Site (`apps/web`): o CTA que antes abria `wa.me/...` agora abre `t.me/<bot>?start=...`. Deep link
  com imóvel de origem funciona igual (`IMOVEL-<id>` no payload do `/start`).
- Painel do corretor: a tela de Configurações mostra o status do Telegram; a coluna de canal de cada
  lead aceita `telegram` ao lado de `whatsapp`/`web`.
- Botões: Telegram usa teclado inline (`inline_keyboard`), sem o limite de 3 botões do WhatsApp — o
  agente pode oferecer mais opções por mensagem sem precisar do formato de lista.

## Riscos e limitações aceitas por ora
- **Áudio não transcreve ainda.** O adapter já marca a mensagem como `TipoMensagem.AUDIO` com o
  `file_id` do Telegram, mas `tools/transcricao.py` só sabe buscar mídia da Meta Cloud API — falha
  graciosamente (`handler.py` já trata isso: cai para "áudio não compreendido"). Estender a
  transcrição para o Telegram (`getFile` + o mesmo pipeline de Transcribe) fica como próximo passo,
  não bloqueia o resto.
- **Long polling não escala como webhook** (um processo, uma conexão longa por vez) — aceitável para
  demo e para o volume de uma POC; em produção real valeria voltar a webhook (Telegram suporta os dois).

## Alternativas consideradas
- **Insistir na verificação de negócio da Meta:** sem prazo previsível, travava a entrega.
- **Manter só o chat do site, sem canal de mensageria externo:** perderia a demonstração de
  "atender leads automaticamente" fora do navegador, que é parte do valor do produto.
