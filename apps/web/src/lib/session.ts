// A sessão do chat é emitida pelo SERVIDOR, não pelo navegador: vem com uma assinatura que prova
// a origem. Sem isso, bastava saber o id de outro visitante para ler e escrever na conversa dele.
const CHAVE = "sdr_sessao";
const CANAL = import.meta.env.VITE_CANAL_URL ?? "http://localhost:8001";

export type Sessao = { session_id: string; token: string; expira_em: number };

let memoria: Sessao | null = null;
let pedido: Promise<Sessao> | null = null;

function ler(): Sessao | null {
  if (memoria) return memoria;
  try {
    const cru = sessionStorage.getItem(CHAVE);
    if (!cru) return null;
    const s = JSON.parse(cru) as Sessao;
    return s.expira_em * 1000 > Date.now() ? (memoria = s) : null;   // expirada: pede outra
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
      try { sessionStorage.setItem(CHAVE, JSON.stringify(s)); } catch { /* aba anônima: fica em memória */ }
      return s;
    })
    .finally(() => { pedido = null; });
  return pedido;
}

/** Só para quem já tem a sessão em mãos (evita await em caminho síncrono). */
export const sessaoAtual = (): Sessao | null => ler();
