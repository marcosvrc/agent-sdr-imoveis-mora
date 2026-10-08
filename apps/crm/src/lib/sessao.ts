/** "A sessão caiu no meio do uso" — compartilhado entre o QueryClient (main.tsx), que percebe o 401
 *  em qualquer consulta ou ação, e o App, que troca a tela pelo login com o aviso.
 *
 *  Antes só a consulta `eu` decidia se havia sessão: se o cookie expirava com a tela aberta, cada
 *  chamada seguinte falhava com "não autenticado" dentro da página, e o painel continuava de pé
 *  como se nada tivesse acontecido até alguém recarregar. */
import { useSyncExternalStore } from "react";

let expirou = false;
const ouvintes = new Set<() => void>();
const avisar = () => ouvintes.forEach((f) => f());

export function marcarSessaoExpirada() { if (!expirou) { expirou = true; avisar(); } }
export function limparSessaoExpirada() { if (expirou) { expirou = false; avisar(); } }

export const useSessaoExpirada = () => useSyncExternalStore(
  (f) => { ouvintes.add(f); return () => { ouvintes.delete(f); }; },
  () => expirou,
);
