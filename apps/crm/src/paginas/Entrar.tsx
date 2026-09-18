import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Botao, Campo, Erro, FaixaSintetica, entradaCls } from "../componentes/ui";
import { BASE, ErroApi, api } from "../lib/api";

/** Login.
 *
 *  A mensagem de erro é a MESMA para usuário inexistente, senha errada e conta inativa — a API já
 *  responde assim, e a tela não pode ser mais específica que ela. Distinguir os casos diria a um
 *  estranho quais e-mails existem na base, e num CRM a lista de quem trabalha na imobiliária já é
 *  informação.
 */
export function Entrar({ erro }: { erro?: unknown }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [falha, setFalha] = useState<unknown>(erro);
  const [ocupado, setOcupado] = useState(false);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setFalha(null);
    setOcupado(true);
    try {
      await api.entrar(email, senha);
      // Confere que a sessão REALMENTE colou antes de sair da tela.
      //
      // Existe uma armadilha silenciosa aqui: se o painel e a API estiverem em hosts diferentes
      // (`127.0.0.1` de um lado, `localhost` do outro), o navegador trata como sites distintos e
      // simplesmente NÃO guarda o cookie `SameSite=Lax`. O login devolve 200, a sessão não existe,
      // e sem esta checagem a tela voltaria ao formulário em branco — o clássico "cliquei e não
      // aconteceu nada". Descoberto abrindo o painel de verdade.
      await api.eu();
      await qc.invalidateQueries({ queryKey: ["eu"] });
    } catch (x) {
      setFalha(x instanceof ErroApi && x.status === 401 && !x.message.includes("inválidos")
        ? new ErroApi(0, "SESSAO_NAO_PERSISTIU",
            `Entrei, mas o navegador não guardou a sessão. Isso acontece quando o painel e a API ` +
            `estão em hosts diferentes (por exemplo 127.0.0.1 e localhost): use o MESMO em ` +
            `${window.location.origin} e em VITE_CRM_API (${BASE}).`)
        : x);
    } finally {
      setOcupado(false);
    }
  }

  const expirada = falha instanceof ErroApi && falha.code === "UNAUTHENTICATED"
    && falha.message.includes("expirada");

  return (
    <div className="flex min-h-screen flex-col">
      <FaixaSintetica />
      <div className="flex flex-1 items-center justify-center p-4">
        <form onSubmit={enviar} className="w-full max-w-sm space-y-4 rounded-xl border border-line bg-surface p-6 shadow-card">
          <div>
            <h1 className="text-lg font-semibold text-ink">CRM da imobiliária</h1>
            <p className="mt-1 text-xs text-inkMuted">
              {expirada ? "Sua sessão expirou. Entre de novo para continuar." : "Entre com seu e-mail e senha."}
            </p>
          </div>
          <Campo rotulo="E-mail">
            <input className={entradaCls} type="email" autoComplete="username" required
                   value={email} onChange={(e) => setEmail(e.target.value)} />
          </Campo>
          <Campo rotulo="Senha">
            <input className={entradaCls} type="password" autoComplete="current-password" required
                   value={senha} onChange={(e) => setSenha(e.target.value)} />
          </Campo>
          {falha && !expirada ? <Erro erro={falha} /> : null}
          <Botao type="submit" variante="primario" ocupado={ocupado} className="w-full justify-center">
            Entrar
          </Botao>
        </form>
      </div>
    </div>
  );
}
