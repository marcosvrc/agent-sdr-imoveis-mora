// Autenticação do painel: token estático, o mesmo `SDR_PAINEL_TOKEN` que a API e o WebSocket
// exigem (services/api/src/api/auth.py). Havia aqui um caminho Cognito via aws-amplify; saiu com o
// resto da AWS. Em desenvolvimento, com o token em branco, vale o `dev-token`.
//
// A senha digitada É o token — por isso validamos contra a API antes de guardar. Guardar sem
// conferir deixaria o painel abrir e cair em 401 na primeira chamada, com um redirecionamento de
// volta ao login que não explica nada.
const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function login(_email: string, senha: string): Promise<string> {
  const candidato = senha.trim() || "dev-token";
  const r = await fetch(`${BASE}/config`, { headers: { Authorization: `Bearer ${candidato}` } });
  if (!r.ok) throw new Error("token do painel inválido");
  localStorage.setItem("token", candidato);
  return candidato;
}

export const token = () => { try { return localStorage.getItem("token"); } catch { return null; } };
export const logout = () => { try { localStorage.removeItem("token"); } catch { /* noop */ } };
