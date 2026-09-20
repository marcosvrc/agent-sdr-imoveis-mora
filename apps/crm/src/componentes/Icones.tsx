// Ícones SVG inline (traço 1.75, estilo lucide) — sem dependência externa.
//
// Subconjunto: só o que o CRM usa. Copiar a folha inteira do painel traria 40 ícones mortos para
// dentro do bundle que o corretor baixa, e um deles acabaria usado por acaso só porque estava lá.
//
// `aria-hidden` em todos, sem exceção: ícone aqui sempre acompanha um rótulo de texto. Se algum dia
// um ícone precisar ficar sozinho, o rótulo vai no `aria-label` do botão, não no SVG.
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement> & { size?: number };
const I = ({ size = 18, children, ...p }: P) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}
       strokeLinecap="round" strokeLinejoin="round" aria-hidden {...p}>{children}</svg>
);

export const Ic = {
  visao: (p: P) => <I {...p}><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></I>,
  funil: (p: P) => <I {...p}><path d="M3 4h18l-7 8v7l-4 2v-9z" /></I>,
  clientes: (p: P) => <I {...p}><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></I>,
  imoveis: (p: P) => <I {...p}><rect x="4" y="2" width="16" height="20" rx="2" /><path d="M9 22v-4h6v4M8 6h.01M16 6h.01M12 6h.01M12 10h.01M12 14h.01M16 10h.01M16 14h.01M8 10h.01M8 14h.01" /></I>,
  visitas: (p: P) => <I {...p}><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></I>,
  encaminhamentos: (p: P) => <I {...p}><path d="M4 12h12" /><path d="m13 7 5 5-5 5" /><path d="M20 4v16" /></I>,
  auditoria: (p: P) => <I {...p}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="m9 12 2 2 4-4" /></I>,
  procurar: (p: P) => <I {...p}><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></I>,
  limpar: (p: P) => <I {...p}><path d="M18 6L6 18M6 6l12 12" /></I>,
  voltar: (p: P) => <I {...p}><path d="M19 12H5" /><path d="m12 19-7-7 7-7" /></I>,
  anterior: (p: P) => <I {...p}><path d="m15 18-6-6 6-6" /></I>,
  proximo: (p: P) => <I {...p}><path d="m9 18 6-6-6-6" /></I>,
  subindo: (p: P) => <I {...p}><path d="m18 15-6-6-6 6" /></I>,
  descendo: (p: P) => <I {...p}><path d="m6 9 6 6 6-6" /></I>,
  marcado: (p: P) => <I {...p}><path d="M20 6L9 17l-5-5" /></I>,
  sair: (p: P) => <I {...p}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="m16 17 5-5-5-5M21 12H9" /></I>,
  sol: (p: P) => <I {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></I>,
  lua: (p: P) => <I {...p}><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></I>,
  sistema: (p: P) => <I {...p}><rect x="2" y="4" width="20" height="13" rx="2" /><path d="M8 21h8M12 17v4" /></I>,
  menu: (p: P) => <I {...p}><path d="M4 6h16M4 12h16M4 18h16" /></I>,
};
