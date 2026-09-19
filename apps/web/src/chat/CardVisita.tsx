import { googleCalendarUrl, icsDataUrl, fmtDataHora, type EventoAgenda } from "../lib/calendario";

export type Visita = EventoAgenda & { imovel_id?: string; rotulo?: string };

// Reserva de visita: o agente devolve `dados.visita`; aqui vira um card com "adicionar à agenda".
//
// Diz RESERVADO, e não "confirmada". A Mora reserva o horário; quem confirma a visita é o corretor,
// e é isso que o texto dela diz na mesma mensagem — um card verde com "✓ confirmada" ao lado
// contradizia a própria resposta, e o que fica na memória de quem lê é o card. Quem aparece no
// imóvel no sábado é uma pessoa: prometer em nome do corretor cria um cliente esperando na porta.
export function CardVisita({ visita }: { visita: Visita }) {
  return (
    <div className="max-w-[85%] rounded-2xl bg-white p-3 text-sm shadow-sm ring-1 ring-amber-200">
      <p className="font-medium text-amber-700">Horário reservado</p>
      <p className="text-slate-700">{fmtDataHora(visita.inicio)}{visita.local ? ` · ${visita.local}` : ""}</p>
      <p className="mt-0.5 text-xs text-slate-500">O corretor confirma com você antes do dia.</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <a href={googleCalendarUrl(visita)} target="_blank" rel="noreferrer" className="rounded-full bg-brand px-3 py-1 text-xs font-medium text-white">Adicionar ao Google Agenda</a>
        <a href={icsDataUrl(visita)} download="visita-vertice.ics" className="rounded-full border px-3 py-1 text-xs font-medium text-slate-600">Apple / Outlook (.ics)</a>
      </div>
    </div>
  );
}
