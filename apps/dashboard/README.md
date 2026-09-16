# apps/dashboard — Painel do corretor

Login Cognito (aws-amplify). Responsivo → PWA no celular do corretor.

| Rota | Tela | Dados |
|---|---|---|
| `/` | Funil (novo → qualificando → qualificado → agendado → handoff) + leads por temperatura | `GET /dashboard/funil` (Recharts) |
| `/leads` | Lista com score, temperatura, estágio, último contato; filtros | `GET /leads` |
| `/leads/:id` | Transcrição ao vivo + cartão de qualificação + resumo do Resumidor + botão **Assumir conversa** | `GET /leads/:id`, WS `papel=dashboard`, `POST /handoff/:id/assumir` |
| `/agenda` | Visitas e reuniões marcadas | `GET /dashboard/visitas` |

Tempo real: mesma API WebSocket dos canais, conectando com `?papel=dashboard` (JWT no authorizer).
Cada mensagem trocada com qualquer lead chega como `{evento: "mensagem", ...}` e atualiza a tela aberta.

```
src/
├── pages/        Funil, Leads, LeadDetalhe, Agenda, Login
├── components/   FunilChart, LeadRow, Transcricao, CartaoLead, ResumoCorretor, BotaoAssumir
└── lib/          api.ts (fetch + JWT), ws.ts, auth.ts (Amplify/Cognito)
```
