import { getSessao } from "./session";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// fetch com keepalive sobrevive à navegação como o sendBeacon, mas sem mandar credenciais:
// sendBeacon usa sempre credentials=include, o que o navegador rejeita com Access-Control-Allow-Origin "*".
export function track(tipo: "viewed_imovel" | "filtered" | "clicked_telegram" | "opened_chat", dados: Record<string, unknown> = {}) {
  // A sessão assinada acompanha o evento: sem ela o servidor descarta, e é o que impede um terceiro
  // de plantar "imóveis vistos" no contexto da conversa de outro visitante.
  getSessao()
    .then((s) => fetch(`${BASE}/eventos`, {
      method: "POST", keepalive: true, headers: { "content-type": "application/json" },
      body: JSON.stringify({ session_id: s.session_id, token: s.token, tipo, dados }),
    }))
    .catch(() => { /* tracking é best-effort */ });
}
