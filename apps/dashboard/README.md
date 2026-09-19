# apps/dashboard — Painel do corretor

Login por token do painel (`SDR_PAINEL_TOKEN`): a senha digitada **é** o token, validado contra a API
antes de ser guardado. Em branco, no perfil local, vale `dev-token`. Não há provedor de identidade —
havia um login Cognito via `aws-amplify`, removido com o resto da AWS. Responsivo → PWA no celular do
corretor.

| Rota | Tela | Dados |
|---|---|---|
| `/` | Visão geral: funil (novo → qualificando → qualificado → agendado → handoff), temperaturas e reativação | `GET /dashboard/funil`, `GET /dashboard/reativacao` (Recharts) |
| `/leads` | Lista com score, temperatura, estágio, último contato; filtros | `GET /leads` |
| `/leads/:id` | Transcrição ao vivo + cartão de qualificação + resumo do Resumidor + botão **Assumir conversa** | `GET /leads/:id`, WS `papel=dashboard`, `POST /handoff/:id/assumir` |
| `/conversas` | Conversas ao vivo de todos os leads | WS `papel=dashboard` |
| `/imoveis`, `/corretores`, `/configuracoes` | Cadastros e configuração do agente | `GET/POST` da API |
| `/governanca`, `/auditoria`, `/saude` | Custo de LLM, trilha de auditoria e saúde do sistema | `routers/governanca.py`, `routers/auditoria.py`, `routers/dashboard.py` |

Tempo real: mesma API WebSocket dos canais, conectando com `?papel=dashboard&token=<token do painel>`.
O servidor recusa com o código 4403 quem chega sem credencial — a conexão espelha as conversas de
todos os leads. Cada mensagem trocada com qualquer lead chega como `{evento: "mensagem", ...}` e
atualiza a tela aberta.

```
src/
├── pages/        VisaoGeral, Leads, LeadDetalhe, Conversas, Imoveis, Corretores,
│                 Governanca, Auditoria, Saude, Configuracoes, Login
├── components/   Shell, CartaoLead, Transcricao, Interesses, ReativacaoResumo, SeletorTema, charts…
└── lib/          api.ts (fetch + token), ws.ts, auth.ts (token do painel), tema.ts
```
