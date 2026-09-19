# apps/web — Site vitrine (porta de entrada do agente)

Mobile-first, PWA instalável. Três páginas principais (escopo deliberado):

| Rota | Página | Papel |
|---|---|---|
| `/` | Landing "Me ajude a encontrar meu imóvel" | Chat como interface principal; imóveis aparecem como cards na conversa |
| `/imoveis` | Listagem com filtros (operação, região, preço, quartos) | Lê `GET /imoveis` (API pública) |
| `/imoveis/:id` | Detalhe do imóvel | Dois CTAs: **Continuar no Telegram** (`t.me/<bot>?start=IMOVEL-<id>`, o bot já abre falando daquele imóvel) e **Conversar agora** (widget) |

Toda navegação relevante dispara `POST /eventos` (`viewed_imovel`, `filtered`, `clicked_telegram`,
`opened_chat`) com o `session_id` — o agente usa isso para pré-preencher o cartão do lead.

Estrutura:
```
src/
├── pages/        Landing, Imoveis, ImovelDetalhe, Favoritos, Privacidade, NaoEncontrada
├── components/   ImovelCard, Filtros, CtaTelegram, GaleriaFotos, ChatLauncher, …
├── chat/         ChatWidget (WebSocket), MensagemBolha, CardImovelChat, CardVisita, BotoesOpcoes
└── lib/          api.ts (fetch), ws.ts (WebSocket client), session.ts (session_id), tracking.ts (eventos)
```
