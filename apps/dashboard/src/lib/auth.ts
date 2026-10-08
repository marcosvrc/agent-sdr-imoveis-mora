// Autenticação do painel: token estático, o mesmo `SDR_PAINEL_TOKEN` que a API e o WebSocket
// exigem (services/api/src/api/auth.py). Havia aqui um caminho Cognito via aws-amplify; saiu com o
// resto da AWS. Em desenvolvimento, com o token em branco, vale o `dev-token`.
//
// A senha digitada É o token — por isso validamos contra a API antes de guardar. Guardar sem
// conferir deixaria o painel abrir e cair em 401 na primeira chamada, com um redirecionamento de
// volta ao login que não explica nada.
const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// Cópia em memória para quando o navegador recusa o localStorage (aba anônima de alguns
// navegadores, cota cheia, bloqueio por política): o `setItem` solto lançava exceção, o login
// "falhava" com o token certo, e a mensagem dizia "token inválido".
let emMemoria: string | null = null;

export async function login(_email: string, senha: string): Promise<string> {
  const candidato = senha.trim() || "dev-token";
  const r = await fetch(`${BASE}/config`, { headers: { Authorization: `Bearer ${candidato}` } });
  if (!r.ok) throw new Error("token do painel inválido");
  emMemoria = candidato;
  try { localStorage.setItem("token", candidato); } catch { /* sem armazenamento: vale só nesta aba */ }
  return candidato;
}

export const token = () => { try { return localStorage.getItem("token") ?? emMemoria; } catch { return emMemoria; } };
export const logout = () => { emMemoria = null; try { localStorage.removeItem("token"); } catch { /* noop */ } };

/** Token recusado pela API (trocado no servidor, revogado). Antes, o 401 só redirecionava: o token
 *  velho continuava salvo, o Guard deixava entrar de novo, a primeira chamada dava 401 — e o
 *  corretor ficava preso entre o login e o painel. Apaga primeiro, depois manda ao login. */
export function sessaoExpirada(): never {
  logout();
  window.location.href = "/login?expirou=1";
  throw new Error("não autenticado");
}
