// Links "adicionar à agenda" — sem credencial, sem API: o próprio usuário confirma no Google Agenda ou importa o .ics.
export type EventoAgenda = { titulo: string; inicio: string; duracao_min?: number; local?: string; descricao?: string };

const fmtGoogle = (d: Date) => d.toISOString().replace(/[-:]|\.\d{3}/g, "");   // 20260915T170000Z

export function googleCalendarUrl(e: EventoAgenda): string {
  const ini = new Date(e.inicio), fim = new Date(ini.getTime() + (e.duracao_min ?? 60) * 60_000);
  const q = new URLSearchParams({ action: "TEMPLATE", text: e.titulo, dates: `${fmtGoogle(ini)}/${fmtGoogle(fim)}`,
    details: e.descricao ?? "Visita agendada pela Mora — Vértice Imóveis", location: e.local ?? "", ctz: "America/Sao_Paulo" });
  return `https://calendar.google.com/calendar/render?${q}`;
}

export function icsDataUrl(e: EventoAgenda): string {
  const ini = new Date(e.inicio), fim = new Date(ini.getTime() + (e.duracao_min ?? 60) * 60_000);
  const ics = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Mora//Vértice//PT", "BEGIN:VEVENT",
    `UID:${ini.getTime()}@vertice`, `DTSTAMP:${fmtGoogle(new Date())}`, `DTSTART:${fmtGoogle(ini)}`, `DTEND:${fmtGoogle(fim)}`,
    `SUMMARY:${e.titulo}`, `LOCATION:${e.local ?? ""}`, `DESCRIPTION:${e.descricao ?? "Visita agendada pela Mora"}`,
    "END:VEVENT", "END:VCALENDAR"].join("\r\n");
  return `data:text/calendar;charset=utf-8,${encodeURIComponent(ics)}`;
}

export const fmtDataHora = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" });
