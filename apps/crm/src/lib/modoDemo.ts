/**
 * Modo demonstração: mascara todo telefone que aparece na tela — lista de leads, conversa,
 * notificações, CRM — como "(11) 9••••-••21". Serve para gravar ou compartilhar a tela sem expor o
 * número de ninguém; os dados no banco não mudam, e o corretor continua vendo o número quando o
 * modo está desligado.
 *
 * Liga com `?demo=1` na URL e desliga com `?demo=0`; a escolha fica lembrada neste navegador.
 * Age sobre o TEXTO da página (um MutationObserver reescreve cada nó de texto que muda), então vale
 * para qualquer tela sem tocar em componente nenhum. Campos de formulário não são alterados.
 */
const CHAVE = "mora.demo";

function ligado(): boolean {
  try {
    const p = new URLSearchParams(window.location.search).get("demo");
    if (p === "1") localStorage.setItem(CHAVE, "1");
    if (p === "0") localStorage.removeItem(CHAVE);
    return localStorage.getItem(CHAVE) === "1";
  } catch {
    return false;
  }
}

const DDD = new Set([11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 24, 27, 28, 31, 32, 33, 34, 35, 37, 38, 41, 42,
  43, 44, 45, 46, 47, 48, 49, 51, 53, 54, 55, 61, 62, 63, 64, 65, 66, 67, 68, 69, 71, 73, 74, 75, 77, 79, 81, 82,
  83, 84, 85, 86, 87, 88, 89, 91, 92, 93, 94, 95, 96, 97, 98, 99]);

// Com DDD, em qualquer formato: +55 11 98765-4321, (11) 98765-4321, 5511987654321, 1133334444…
const COM_DDD = /(?<![0-9A-Za-z_\-/])(\+?\s*55[\s().-]*)?\(?([1-9][0-9])\)?[\s.-]*(9?[0-9]{4})[\s.-]?([0-9]{4})(?![0-9A-Za-z_\-/])/g;
// Celular sem DDD, só quando escrito com hífen: 98765-4321
const SEM_DDD = /(?<![0-9A-Za-z_\-/])9[0-9]{4}-([0-9]{2})([0-9]{2})(?![0-9A-Za-z_\-/])/g;

function mascarar(texto: string): string {
  if (!/\d{4}/.test(texto)) return texto;
  return texto
    .replace(COM_DDD, (tudo, pais: string | undefined, ddd: string, meio: string, fim: string) => {
      const ass = meio + fim;
      const celular = ass.length === 9 && ass[0] === "9";
      const fixo = ass.length === 8 && "2345".includes(ass[0]);
      if (!DDD.has(Number(ddd)) || !(celular || fixo)) return tudo;
      return `${pais ? "+55 " : ""}(${ddd}) ${celular ? "9••••" : "••••"}-••${fim.slice(-2)}`;
    })
    .replace(SEM_DDD, (_t, _a: string, fim: string) => `9••••-••${fim}`);
}

function tratar(no: Node) {
  if (no.nodeType === Node.TEXT_NODE) {
    const v = no.nodeValue ?? "";
    const m = mascarar(v);
    if (m !== v) no.nodeValue = m;
    return;
  }
  if (no.nodeType !== Node.ELEMENT_NODE) return;
  const tag = (no as Element).tagName;
  if (tag === "SCRIPT" || tag === "STYLE" || tag === "TEXTAREA") return;
  const w = document.createTreeWalker(no, NodeFilter.SHOW_TEXT);
  for (let t = w.nextNode(); t; t = w.nextNode()) tratar(t);
}

if (typeof window !== "undefined" && ligado()) {
  const iniciar = () => {
    tratar(document.body);
    new MutationObserver((mudancas) => {
      for (const m of mudancas) {
        if (m.type === "characterData") tratar(m.target);
        m.addedNodes.forEach(tratar);
      }
    }).observe(document.body, { subtree: true, childList: true, characterData: true });
  };
  if (document.body) iniciar();
  else document.addEventListener("DOMContentLoaded", iniciar);
}

export {};
