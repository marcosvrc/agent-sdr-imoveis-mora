import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "../lib/auth";
import { Button, Field, Input } from "../components/ui";
import { Ic } from "../components/Icons";

export function Login() {
  const [email, setEmail] = useState("corretor@verticeimoveis.com.br"); const [senha, setSenha] = useState(""); const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);
  const nav = useNavigate();
  const local = !import.meta.env.VITE_COGNITO_USER_POOL_ID;
  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas p-4">
      <form className="w-full max-w-sm space-y-4 rounded-2xl border border-line bg-surface p-7 shadow-card" onSubmit={async (e) => { e.preventDefault(); setCarregando(true); try { await login(email, senha); nav("/"); } catch { setErro("Credenciais inválidas"); } finally { setCarregando(false); } }}>
        <div className="flex items-center gap-2.5"><span className="grid h-9 w-9 place-items-center rounded-lg bg-brand text-brand-ink"><Ic.spark size={18} /></span><div><h1 className="text-base font-semibold">Vértice Imóveis</h1><p className="text-xs text-ink-muted">Painel administrativo</p></div></div>
        <Field label="E-mail"><Input value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></Field>
        <Field label="Senha"><Input type="password" value={senha} onChange={(e) => setSenha(e.target.value)} placeholder={local ? "qualquer senha no modo local" : ""} autoComplete="current-password" /></Field>
        {erro && <p className="rounded-lg bg-bad-soft px-3 py-2 text-xs text-bad-strong">{erro}</p>}
        <Button variante="primario" className="w-full" type="submit" disabled={carregando}>Entrar</Button>
        {local && <p className="text-center text-[11px] text-ink-muted">Perfil local: autenticação simulada (token de desenvolvimento)</p>}
      </form>
    </div>
  );
}
