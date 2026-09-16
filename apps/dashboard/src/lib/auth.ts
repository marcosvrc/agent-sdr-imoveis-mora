// Perfil aws: Cognito via aws-amplify. Perfil local: token estático "dev-token" (services/api/src/api/auth.py).
const POOL = import.meta.env.VITE_COGNITO_USER_POOL_ID;

export async function login(email: string, senha: string): Promise<string> {
  if (!POOL) { localStorage.setItem("token", "dev-token"); return "dev-token"; }
  const { Amplify } = await import("aws-amplify");
  const { signIn, fetchAuthSession } = await import("aws-amplify/auth");
  Amplify.configure({ Auth: { Cognito: { userPoolId: POOL, userPoolClientId: import.meta.env.VITE_COGNITO_CLIENT_ID! } } });
  await signIn({ username: email, password: senha });
  const token = (await fetchAuthSession()).tokens?.idToken?.toString() ?? "";
  localStorage.setItem("token", token);
  return token;
}

export const token = () => { try { return localStorage.getItem("token"); } catch { return null; } };
export const logout = () => { try { localStorage.removeItem("token"); } catch { /* noop */ } };
