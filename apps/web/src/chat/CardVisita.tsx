import { googleCalendarUrl, icsDataUrl, fmtDataHora, type EventoAgenda } from "../lib/calendario";

export type Visita = EventoAgenda & { imovel_id?: string; rotulo?: string };

// Confirmação de visita: o agente devolve `dados.visita`; aqui vira um card com "adicionar à agenda".
export function CardVisita({ visita }: { visita: Visita }) {
  return (
    <div className="max-w-[85%] rounded-2xl bg-white p-3 text-sm shadow-sm ring-1 ring-green-200">
      <p className="font-medium text-green-700">✓ Visita confirmada</p>
      <p className="text-slate-700">{fmtDataHora(visita.inicio)}{visita.local ? ` · ${visita.local}` : ""}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <a href={googleCalendarUrl(visita)} target="_blank" rel="noreferrer" className="rounded-full bg-brand px-3 py-1 text-xs font-medium text-white">Adicionar ao Google Agenda</a>
        <a href={icsDataUrl(visita)} download="visita-vertice.ics" className="rounded-full border px-3 py-1 text-xs font-medium text-slate-600">Apple / Outlook (.ics)</a>
      </div>
    </div>
  );
}
