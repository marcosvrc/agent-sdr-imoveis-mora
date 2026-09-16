/** Tema do painel: claro, escuro ou o que o sistema operacional estiver usando (ADR-0014).
 *
 *  Dois atributos no <html>, de propósito:
 *   - `data-tema`         = a ESCOLHA da pessoa (claro | escuro | sistema);
 *   - `data-tema-efetivo` = o que está pintado na tela agora (claro | escuro).
 *
 *  O CSS só olha o segundo. Assim existe uma única cópia da paleta escura (nada de repetir tudo
 *  dentro de um `@media (prefers-color-scheme)` para alguém esquecer de atualizar depois), e o
 *  controle na tela consegue mostrar "Sistema" selecionado mesmo estando escuro no momento.
 */
export type Tema = "claro" | "escuro" | "sistema";

const CHAVE = "tema";
export const TEMAS: { k: Tema; r: string; dica: string }[] = [
  { k: "claro", r: "Claro", dica: "Sempre claro" },
  { k: "escuro", r: "Escuro", dica: "Sempre escuro" },
  { k: "sistema", r: "Sistema", dica: "Acompanha o macOS/Windows" },
];

const consulta = () => window.matchMedia?.("(prefers-color-scheme: dark)");

export function temaSalvo(): Tema {
  try {
    const v = localStorage.getItem(CHAVE);
    return v === "claro" || v === "escuro" || v === "sistema" ? v : "sistema";
  } catch {
    return "sistema";      // navegação privada / storage bloqueado: nada de quebrar por causa disso
  }
}

export function efetivo(t: Tema): "claro" | "escuro" {
  if (t !== "sistema") return t;
  return consulta()?.matches ? "escuro" : "claro";
}

export function aplicar(t: Tema): void {
  const raiz = document.documentElement;
  raiz.setAttribute("data-tema", t);
  raiz.setAttribute("data-tema-efetivo", efetivo(t));
}

export function salvar(t: Tema): void {
  aplicar(t);
  try { localStorage.setItem(CHAVE, t); } catch { /* preferência só desta aba, então */ }
}

/** Enquanto a escolha for "sistema", o painel acompanha o anoitecer sem ninguém recarregar a aba. */
export function observarSistema(aoMudar: () => void): () => void {
  const mq = consulta();
  if (!mq) return () => {};
  const handler = () => { if (temaSalvo() === "sistema") { aplicar("sistema"); aoMudar(); } };
  mq.addEventListener("change", handler);
  return () => mq.removeEventListener("change", handler);
}
