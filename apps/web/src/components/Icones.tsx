/** Ícones inline (sem biblioteca: são 16 traços, não vale 40 kB de dependência).
 *  Todos herdam `currentColor` e recebem aria-hidden — quem nomeia a ação é o rótulo do botão. */
type P = { size?: number; className?: string; strokeWidth?: number };

const I = ({ size = 18, className, strokeWidth = 1.8, children }: P & { children: React.ReactNode }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden focusable="false">
    {children}
  </svg>
);

export const Ic = {
  busca: (p: P) => <I {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.2-3.2" /></I>,
  filtro: (p: P) => <I {...p}><path d="M4 6h16M7 12h10M10 18h4" /></I>,
  local: (p: P) => <I {...p}><path d="M12 21s7-5.6 7-11a7 7 0 1 0-14 0c0 5.4 7 11 7 11z" /><circle cx="12" cy="10" r="2.5" /></I>,
  cama: (p: P) => <I {...p}><path d="M3 18v-6h18v6" /><path d="M3 12V7" /><path d="M21 18v2M3 18v2" /><path d="M7 12V9h6v3" /></I>,
  regua: (p: P) => <I {...p}><rect x="3" y="8" width="18" height="8" rx="1.5" /><path d="M7 8v3M11 8v4M15 8v3M19 8v4" /></I>,
  carro: (p: P) => <I {...p}><path d="M5 16h14" /><path d="M6 16v2M18 16v2" /><path d="M4 16v-3l2-4h12l2 4v3z" /><circle cx="8" cy="13.5" r=".6" fill="currentColor" /><circle cx="16" cy="13.5" r=".6" fill="currentColor" /></I>,
  banho: (p: P) => <I {...p}><path d="M4 12h16v3a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z" /><path d="M7 12V6a2 2 0 0 1 4 0" /><path d="M6 19l-1 2M18 19l1 2" /></I>,
  coracao: ({ cheio, ...p }: P & { cheio?: boolean }) => (
    <svg width={p.size ?? 18} height={p.size ?? 18} viewBox="0 0 24 24" className={p.className}
         fill={cheio ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8" aria-hidden focusable="false">
      <path d="M12.1 20.5s-7.6-4.6-9.9-9.1C.6 8 2 4.5 5.4 4c2-.3 3.9.7 5.7 2.8C12.9 4.7 14.8 3.7 16.8 4c3.4.5 4.8 4 3.2 7.4-2.3 4.5-9.9 9.1-9.9 9.1z" />
    </svg>
  ),
  compartilhar: (p: P) => <I {...p}><circle cx="18" cy="5" r="2.5" /><circle cx="6" cy="12" r="2.5" /><circle cx="18" cy="19" r="2.5" /><path d="m8.3 10.8 7.4-4.1M8.3 13.2l7.4 4.1" /></I>,
  chat: (p: P) => <I {...p}><path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7A8.4 8.4 0 0 1 4 11.5 8.5 8.5 0 0 1 12.5 3 8.5 8.5 0 0 1 21 11.5z" /></I>,
  telefone: (p: P) => <I {...p}><path d="M5 3h3l2 5-2.5 1.5a12 12 0 0 0 5 5L14 12l5 2v3a2 2 0 0 1-2.2 2A16.5 16.5 0 0 1 3 5.2 2 2 0 0 1 5 3z" /></I>,
  telegram: (p: P) => <I {...p}><path d="m21 4-3 16-6-4.5L21 4z" /><path d="m21 4-15 8 3.5 1.5L21 4z" /><path d="M9.5 13.5V18l2.5-2.5" /></I>,
  calendario: (p: P) => <I {...p}><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></I>,
  seta: (p: P) => <I {...p}><path d="M5 12h14M13 6l6 6-6 6" /></I>,
  esquerda: (p: P) => <I {...p}><path d="m15 6-6 6 6 6" /></I>,
  direita: (p: P) => <I {...p}><path d="m9 6 6 6-6 6" /></I>,
  fechar: (p: P) => <I {...p}><path d="M6 6l12 12M18 6L6 18" /></I>,
  check: (p: P) => <I {...p}><path d="m5 13 4 4L19 7" /></I>,
  escudo: (p: P) => <I {...p}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="m9 12 2 2 4-4" /></I>,
  info: (p: P) => <I {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></I>,
  relogio: (p: P) => <I {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></I>,
  casa: (p: P) => <I {...p}><path d="m3 11 9-7 9 7" /><path d="M5 10v10h14V10" /><path d="M10 20v-6h4v6" /></I>,
  copiar: (p: P) => <I {...p}><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h8" /></I>,
};
