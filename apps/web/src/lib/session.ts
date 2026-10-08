// A sessão do chat é emitida pelo SERVIDOR, não pelo navegador: vem com uma assinatura que prova
// a origem. Sem isso, bastava saber o id de outro visitante para ler e escrever na conversa dele.
const CHAVE = "sdr_sessao";
const CANAL = import.meta.env.VITE_CANAL_URL ?? "http://localhost:8001";

export type Sessao = { session_id: string; token: string; expira_em: number };

/** Modo de teste (SDR_CHAT_NOVA_CONVERSA no local/.env): a sessão vive só em memória, então cada
 *  carregamento da página é uma conversa nova, e o chat ganha o botão "Nova conversa". Desligado,
 *  vale a regra de produção: uma sessão por aba, que sobrevive ao recarregar. */
export const NOVA_CONVERSA_A_CADA_VISITA = import.meta.env.VITE_CHAT_NOVA_CONVERSA === "true";

let memoria: Sessao | null = null;
let pedido: Promise<Sessao> | null = null;

/** Folga para não conectar com um token que vence no meio do aperto de mão. */
const MARGEM_MS = 60_000;
const valida = (s: Sessao) => s.expira_em * 1000 - MARGEM_MS > Date.now();

function ler(): Sessao | null {
  // A memória também vence: com a aba aberta mais de 12 h, devolvê-la sem conferir fazia o widget
  // reconectar para sempre com um token que o servidor já recusava.
  if (memoria) {
    if (valida(memoria)) return memoria;
    memoria = null;
  }
  if (NOVA_CONVERSA_A_CADA_VISITA) return null;
  try {
    const cru = sessionStorage.getItem(CHAVE);
    if (!cru) return null;
    const s = JSON.parse(cru) as Sessao;
    return valida(s) ? (memoria = s) : null;   // expirada: pede outra
  } catch { return null; }
}

/** Uma sessão por aba, renovada quando expira. Chamadas simultâneas compartilham o mesmo pedido. */
export async function getSessao(): Promise<Sessao> {
  const atual = ler();
  if (atual) return atual;
  pedido ??= fetch(`${CANAL}/sessao`, { method: "POST" })
    .then((r) => { if (!r.ok) throw new Error(`sessão ${r.status}`); return r.json() as Promise<Sessao>; })
    .then((s) => {
      memoria = s;
      if (!NOVA_CONVERSA_A_CADA_VISITA) {
        try { sessionStorage.setItem(CHAVE, JSON.stringify(s)); } catch { /* aba anônima: fica em memória */ }
      }
      return s;
    })
    .finally(() => { pedido = null; });
  return pedido;
}

/** Esquece a sessão atual: a próxima conexão pede outra ao servidor, e o agente vê um lead novo.
 *  Com `soSe`, só descarta se a sessão guardada ainda for aquela — o 4401 de uma conexão antiga
 *  não apaga a sessão nova que outra parte do código já obteve. */
export function descartarSessao(soSe?: string) {
  if (soSe && memoria && memoria.session_id !== soSe) return;
  memoria = null;
  pedido = null;
  try { sessionStorage.removeItem(CHAVE); } catch { /* sem armazenamento: nada a apagar */ }
}

/** Só para quem já tem a sessão em mãos (evita await em caminho síncrono). */
export const sessaoAtual = (): Sessao | null => ler();
