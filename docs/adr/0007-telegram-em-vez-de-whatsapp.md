# ADR-0007 — Telegram substitui WhatsApp como canal externo ativo

**Status:** aceito · **Data:** 2026-09-11

## Contexto
O WhatsApp Cloud API (Meta) exige criar um app no Meta for Developers e, para uso além do número de
teste, verificação de negócio — processo que travou na prática (conta recusada/pendente). Isso bloqueava
qualquer teste de ponta a ponta pelo canal de mensageria além do chat do site.

## Decisão
`services/channels/telegram` (novo, mesmo contrato do ADR-0003) substitui `services/channels/whatsapp`
como canal externo. Um bot do Telegram é criado na hora, falando com **@BotFather** — sem app review,
sem verificação de negócio, sem prazo de espera.

Além disso, o canal passa a usar **long polling** (`getUpdates`) em vez de webhook: o worker
`telegram-in` puxa mensagens ativamente, então não precisa de URL pública nem do túnel cloudflared que
o webhook do WhatsApp exigia (`tunnel` saiu do compose). Isso também simplifica o ambiente de
desenvolvimento — um serviço a menos no ar, uma dependência de rede a menos.

**Atualização:** o WhatsApp saiu do código por completo. `services/channels/whatsapp` e o worker de
envio foram removidos, e `Canal` tem hoje só `telegram`, `web` e `sistema`
(`shared/sdr_shared/messaging/contracts.py`). Não é caso de "religar no compose": voltar ao WhatsApp
significa escrever o adaptador de novo, contra a Cloud API da Meta, com a verificação de negócio que
travou aqui. Manter um adaptador morto no repositório custava manutenção e teste por uma opção que
ninguém ia exercer.

## O que muda para quem usa o sistema
- Site (`apps/web`): o CTA que antes abria `wa.me/...` agora abre `t.me/<bot>?start=...`. Deep link
  com imóvel de origem funciona igual (`IMOVEL-<id>` no payload do `/start`).
- Painel do corretor: a tela de Configurações mostra o status do Telegram; a coluna de canal de cada
  lead mostra `telegram` ou `web`.
- Botões: Telegram usa teclado inline (`inline_keyboard`), sem o limite de 3 botões do WhatsApp — o
  agente pode oferecer mais opções por mensagem sem precisar do formato de lista.

## Riscos e limitações aceitas por ora
- **Áudio — resolvido depois.** Quando este ADR foi escrito, o adapter marcava a mensagem como
  `TipoMensagem.AUDIO` com o `file_id` do Telegram mas nada sabia baixá-la. Hoje
  `agent/tools/transcricao.py` faz `getFile` + download e transcreve com `faster-whisper` no próprio
  processo (`SDR_TRANSCRICAO_PROVIDER` ∈ `auto` | `whisper_local` | `off`), sem serviço externo e sem
  custo por minuto. Continua falhando graciosamente quando desligado: o `handler.py` pede texto.
- **Long polling não escala como webhook** (um processo, uma conexão longa por vez) — aceitável para
  demo e para o volume de uma POC. Voltar a webhook (o Telegram suporta os dois) exigiria uma URL
  pública, e hoje nada está implantado: a entrega roda inteira em `docker compose`.

## Alternativas consideradas
- **Insistir na verificação de negócio da Meta:** sem prazo previsível, travava a entrega.
- **Manter só o chat do site, sem canal de mensageria externo:** perderia a demonstração de
  "atender leads automaticamente" fora do navegador, que é parte do valor do produto.
