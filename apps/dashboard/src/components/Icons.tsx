// Ícones SVG inline (traço 1.75, estilo lucide) — sem dependência externa.
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement> & { size?: number };
const I = ({ size = 18, children, ...p }: P) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden {...p}>{children}</svg>
);

export const Ic = {
  overview: (p: P) => <I {...p}><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></I>,
  leads: (p: P) => <I {...p}><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></I>,
  chat: (p: P) => <I {...p}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></I>,
  calendar: (p: P) => <I {...p}><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" /></I>,
  building: (p: P) => <I {...p}><rect x="4" y="2" width="16" height="20" rx="2" /><path d="M9 22v-4h6v4M8 6h.01M16 6h.01M12 6h.01M12 10h.01M12 14h.01M16 10h.01M16 14h.01M8 10h.01M8 14h.01" /></I>,
  badge: (p: P) => <I {...p}><path d="M16 11l2 2 4-4" /><circle cx="9" cy="7" r="4" /><path d="M2 21v-2a4 4 0 0 1 4-4h6" /></I>,
  contato: (p: P) => <I {...p}><path d="M4 4h16v16H4z" /><circle cx="10" cy="10" r="2.5" /><path d="M6 17c.8-1.8 2.3-2.8 4-2.8s3.2 1 4 2.8" /><path d="M16 9h2M16 13h2" /></I>,
  sino: (p: P) => <I {...p}><path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></I>,
  shield: (p: P) => <I {...p}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="m9 12 2 2 4-4" /></I>,
  gauge: (p: P) => <I {...p}><path d="M12 14 4.5 9.5" /><circle cx="12" cy="14" r="1.5" fill="currentColor" stroke="none" /><path d="M3 18a9 9 0 1 1 18 0" /></I>,
  coins: (p: P) => <I {...p}><circle cx="8" cy="8" r="5" /><path d="M18.09 10.37A6 6 0 1 1 10.34 18" /><path d="M7 6h1v4M16.71 13.88l.7.71-2.82 2.82" /></I>,
  settings: (p: P) => <I {...p}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></I>,
  logout: (p: P) => <I {...p}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="M16 17l5-5-5-5M21 12H9" /></I>,
  menu: (p: P) => <I {...p}><path d="M4 6h16M4 12h16M4 18h16" /></I>,
  panelLeft: (p: P) => <I {...p}><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M9 3v18" /></I>,
  chevronLeft: (p: P) => <I {...p}><path d="M15 18l-6-6 6-6" /></I>,
  chevronRight: (p: P) => <I {...p}><path d="M9 18l6-6-6-6" /></I>,
  chevronDown: (p: P) => <I {...p}><path d="M6 9l6 6 6-6" /></I>,
  search: (p: P) => <I {...p}><circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" /></I>,
  plus: (p: P) => <I {...p}><path d="M12 5v14M5 12h14" /></I>,
  x: (p: P) => <I {...p}><path d="M18 6L6 18M6 6l12 12" /></I>,
  edit: (p: P) => <I {...p}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></I>,
  trash: (p: P) => <I {...p}><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" /></I>,
  arrowUp: (p: P) => <I {...p}><path d="M12 19V5M5 12l7-7 7 7" /></I>,
  arrowDown: (p: P) => <I {...p}><path d="M12 5v14M19 12l-7 7-7-7" /></I>,
  arrowRight: (p: P) => <I {...p}><path d="M5 12h14M12 5l7 7-7 7" /></I>,
  refresh: (p: P) => <I {...p}><path d="M21 12a9 9 0 1 1-2.64-6.36" /><path d="M21 3v6h-6" /></I>,
  external: (p: P) => <I {...p}><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /><path d="M15 3h6v6M10 14L21 3" /></I>,
  flame: (p: P) => <I {...p}><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z" /></I>,
  thermometer: (p: P) => <I {...p}><path d="M14 14.76V4.5a2.5 2.5 0 0 0-5 0v10.26a4.5 4.5 0 1 0 5 0z" /><path d="M11.5 14.5V9" /></I>,
  snowflake: (p: P) => <I {...p}><path d="M12 2v20M20.66 7 3.34 17M3.34 7l17.32 10" /><path d="m9.5 4.5 2.5-2.5 2.5 2.5M9.5 19.5 12 22l2.5-2.5" /><path d="m6.1 6.4-2.76.6.6 2.76M17.9 17.6l2.76-.6-.6-2.76M17.9 6.4l2.76.6-.6 2.76M6.1 17.6l-2.76-.6.6-2.76" /></I>,
  clock: (p: P) => <I {...p}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></I>,
  check: (p: P) => <I {...p}><path d="M20 6L9 17l-5-5" /></I>,
  bolt: (p: P) => <I {...p}><path d="M13 2L3 14h9l-1 8 10-12h-9z" /></I>,
  handoff: (p: P) => <I {...p}><path d="M12 5v14M5 12l7-7 7 7" transform="rotate(90 12 12)" /><path d="M4 21h16" /></I>,
  whatsapp: (p: P) => <I {...p}><path d="M20.5 11.5a8.5 8.5 0 0 1-12.6 7.4L3 20l1.2-4.6A8.5 8.5 0 1 1 20.5 11.5z" /><path d="M9 9.5c0 3 2.5 5.5 5.5 5.5l1-1.5-2-1-1 1a4 4 0 0 1-2-2l1-1-1-2z" /></I>,
  telegram: (p: P) => <I {...p}><path d="M21 3 2 10.5l6 2.2M21 3l-3 17-8-6.3M21 3l-12.7 11.4M9 13.4V19l3-3.4" /></I>,
  globe: (p: P) => <I {...p}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" /></I>,
  eye: (p: P) => <I {...p}><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></I>,
  info: (p: P) => <I {...p}><circle cx="12" cy="12" r="9" /><path d="M12 8h.01M11 12h1v4h1" /></I>,
  spark: (p: P) => <I {...p}><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /></I>,
  sol: (p: P) => <I {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></I>,
  lua: (p: P) => <I {...p}><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></I>,
  monitor: (p: P) => <I {...p}><rect x="2" y="4" width="20" height="13" rx="2" /><path d="M8 21h8M12 17v4" /></I>,
  dot: (p: P) => <I {...p}><circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" /></I>,
};
export type IconName = keyof typeof Ic;
