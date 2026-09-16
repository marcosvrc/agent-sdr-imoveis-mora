# apps/web — Site vitrine (porta de entrada do agente)

Mobile-first, PWA instalável. Três páginas, nada mais (escopo deliberado):

| Rota | Página | Papel |
|---|---|---|
| `/` | Landing "Me ajude a encontrar meu imóvel" | Chat como interface principal; imóveis aparecem como cards na conversa |
| `/imoveis` | Listagem com filtros (operação, região, preço, quartos) | Lê `GET /imoveis` (API pública, cache CloudFront) |
| `/imoveis/:id` | Detalhe do imóvel | Dois CTAs: **WhatsApp** (`wa.me/<num>?text=Olá! Vi o IMOVEL-<id>`) e **Conversar agora** (widget) |

Toda navegação relevante dispara `POST /eventos` (`viewed_imovel`, `filtered`, `clicked_telegram`)
com o `session_id` — o agente usa isso para pré-preencher o cartão do lead.

Estrutura:
```
src/
├── pages/        Landing, Imoveis, ImovelDetalhe
├── components/   ImovelCard, Filtros, CtaWhatsApp
├── chat/         ChatWidget (WebSocket), MensagemBolha, CardImovelChat, BotoesOpcoes
└── lib/          api.ts (fetch), ws.ts (WebSocket client), session.ts (session_id), tracking.ts (eventos)
```
