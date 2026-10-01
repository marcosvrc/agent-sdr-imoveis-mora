import { useId } from "react";

/** Retrato da Mora: ilustrado de propósito. Ela é assistente virtual e diz isso na primeira
 *  mensagem — uma foto de pessoa real prometeria um atendimento humano que não está ali. O
 *  telhado atrás da cabeça é o mesmo traço do logo da Vértice.
 *  Desenhado para continuar legível com 24 px (bolha do chat) e até 128 px. */
export function MoraAvatar({ tamanho = 32, className = "" }: { tamanho?: number; className?: string }) {
  const recorte = useId();
  return (
    <svg width={tamanho} height={tamanho} viewBox="0 0 64 64" className={`shrink-0 ${className}`}
         role="img" aria-label="Mora, assistente virtual">
      <defs><clipPath id={recorte}><circle cx="32" cy="32" r="32" /></clipPath></defs>
      <g clipPath={`url(#${recorte})`}>
        <rect width="64" height="64" fill="#dbeafe" />
        <path d="M9 30 32 11l23 19" fill="none" stroke="#2563eb" strokeWidth="4.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M18.5 37c-1.6-11 4-19.5 13.5-19.5S47.1 26 45.5 37c-.6 4.4-1.4 9-3 12H21.5c-1.6-3-2.4-7.6-3-12z" fill="#0f172a" />
        <path d="M10 66c1.5-9.5 9-15 22-15s20.5 5.5 22 15z" fill="#2563eb" />
        <path d="M28 44h8v8.5c-2.6 1.6-5.4 1.6-8 0z" fill="#d9a07a" />
        <ellipse cx="32" cy="35.5" rx="10.2" ry="11.6" fill="#ecbd96" />
        <path d="M21.6 34.5c.4-8.2 5-12.7 11.2-12.7 5.4 0 9.5 3.4 10.6 9.4-5.6-.4-10.6-2.6-13.9-6.2-1.6 4.4-4.4 7.6-7.9 9.5z" fill="#0f172a" />
        <ellipse cx="28.2" cy="36.4" rx="1.25" ry="1.5" fill="#0f172a" />
        <ellipse cx="35.8" cy="36.4" rx="1.25" ry="1.5" fill="#0f172a" />
        <circle cx="25.6" cy="40" r="1.9" fill="#f0a08a" opacity=".55" />
        <circle cx="38.4" cy="40" r="1.9" fill="#f0a08a" opacity=".55" />
        <path d="M29.3 41.3c1.6 1.3 3.8 1.3 5.4 0" fill="none" stroke="#9a4a3a" strokeWidth="1.4" strokeLinecap="round" />
        <circle cx="21.9" cy="40.3" r="1.3" fill="#2563eb" />
      </g>
    </svg>
  );
}
