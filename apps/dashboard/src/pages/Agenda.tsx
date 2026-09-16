import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Visita } from "../lib/api";
import { googleCalendarUrl, fmtDataHora } from "../lib/calendario";
import { Button, Card, PageHeader, EmptyState, Paginacao, usePaginacao } from "../components/ui";
import { Ic } from "../components/Icons";

const TZ = "America/Sao_Paulo";
const SLOTS = [10, 14, 16];                                   // mesma grade da agenda simulada (dias úteis)
const DIAS = ["seg", "ter", "qua", "qui", "sex"];

// Data local (Brasília) como "YYYY-MM-DD" e hora inteira, a partir de um ISO em UTC
function local(iso: string) {
  const p = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", hour12: false }).formatToParts(new Date(iso));
  const g = (t: string) => p.find((x) => x.type === t)?.value ?? "";
  return { dia: `${g("year")}-${g("month")}-${g("day")}`, hora: Number(g("hour")) };
}
function segundaDaSemana(base: Date) {
  const d = new Date(base); d.setHours(12, 0, 0, 0);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));           // domingo=0 → volta 6; segunda → 0
  return d;
}
const chave = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export function Agenda() {
  const { data } = useQuery({ queryKey: ["visitas"], queryFn: api.visitas, refetchInterval: 15_000 });
  const pg = usePaginacao(data ?? [], 10, "visitas");
  const [semana, setSemana] = useState(() => segundaDaSemana(new Date()));
  const dias = useMemo(() => DIAS.map((_, i) => { const d = new Date(semana); d.setDate(semana.getDate() + i); return d; }), [semana]);
  const hoje = chave(new Date());

  const grade = useMemo(() => {
    const m = new Map<string, Visita[]>();
    for (const v of data ?? []) { const { dia, hora } = local(v.inicio); const k = `${dia}|${hora}`; m.set(k, [...(m.get(k) ?? []), v]); }
    return m;
  }, [data]);
  const foraDaGrade = (data ?? []).filter((v) => !SLOTS.includes(local(v.inicio).hora));

  return (
    <div className="space-y-4">
      <PageHeader titulo="Agenda" descricao={`${data?.length ?? 0} visitas confirmadas · grade de 10h, 14h e 16h em dias úteis`}
        acoes={<div className="flex items-center gap-1.5">
          <Button tamanho="sm" onClick={() => setSemana((s) => { const d = new Date(s); d.setDate(d.getDate() - 7); return d; })} aria-label="Semana anterior"><Ic.chevronLeft size={14} /></Button>
          <Button tamanho="sm" onClick={() => setSemana(segundaDaSemana(new Date()))}>Hoje</Button>
          <Button tamanho="sm" onClick={() => setSemana((s) => { const d = new Date(s); d.setDate(d.getDate() + 7); return d; })} aria-label="Próxima semana"><Ic.chevronRight size={14} /></Button>
          <span className="ml-2 text-sm text-ink-muted">{dias[0].toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })} – {dias[4].toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}</span>
        </div>} />

      <div className="overflow-x-auto rounded-xl border border-line bg-surface shadow-card">
        <div className="grid min-w-[640px] grid-cols-[64px_repeat(5,1fr)] text-sm">
          <div className="border-b border-line" />
          {dias.map((d, i) => (
            <div key={i} className={`border-b border-l border-line px-2 py-2 text-center ${chave(d) === hoje ? "bg-info-soft font-semibold text-brand-accent" : "text-ink-muted"}`}>
              <div className="uppercase text-xs">{DIAS[i]}</div><div>{d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}</div>
            </div>
          ))}
          {SLOTS.map((h) => (
            <RowSlot key={h} hora={h}>
              {dias.map((d, i) => {
                const vs = grade.get(`${chave(d)}|${h}`) ?? [];
                return (
                  <div key={i} className="min-h-[72px] space-y-1 border-l border-t border-line p-1.5">
                    {vs.map((v) => <CardVisita key={v.id} v={v} />)}
                  </div>
                );
              })}
            </RowSlot>
          ))}
        </div>
      </div>

      <Card titulo="Próximas visitas" semPadding>
        <ul className="divide-y divide-line">
          {pg.fatia.map((v) => (
            <li key={v.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-sm">
              <div>
                <p className="font-medium">{fmtDataHora(v.inicio)}{foraDaGrade.includes(v) ? <span className="ml-2 rounded bg-warn-soft px-1.5 text-xs text-warn-strong">fora da grade</span> : null}</p>
                <p className="text-ink-muted">{v.tipo} · {v.bairro ?? v.imovel_id ?? "imóvel a definir"} · <Link to={`/leads/${v.lead_id}`} className="hover:underline">{v.nome ?? v.lead_id}</Link>{v.corretor_nome ? <> · corretor <b className="font-medium text-ink">{v.corretor_nome}</b></> : <span className="text-warn-strong"> · sem corretor</span>}</p>
              </div>
              <a href={googleCalendarUrl(evento(v))} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-ink-muted hover:bg-surface-2"><Ic.external size={12} /> Google Agenda</a>
            </li>
          ))}
          {data?.length === 0 && <li><EmptyState icone="calendar" titulo="Nenhuma visita agendada" descricao="Quando um lead confirmar um horário com a Mora, a visita aparece aqui." /></li>}
        </ul>
        <Paginacao {...pg} />
      </Card>
    </div>
  );
}

function RowSlot({ hora, children }: { hora: number; children: React.ReactNode }) {
  return <>
    <div className="border-t border-line px-2 py-2 text-right text-xs font-medium text-ink-muted">{hora}h</div>
    {children}
  </>;
}

const evento = (v: Visita) => ({ titulo: `Visita ${v.tipo === "visita" ? "ao imóvel" : v.tipo} — ${v.nome ?? v.lead_id}`, inicio: v.inicio, duracao_min: 60,
  local: v.bairro ? `${v.bairro}, São Paulo` : "São Paulo", descricao: `Lead ${v.lead_id}${v.imovel_id ? ` · imóvel ${v.imovel_id}` : ""}${v.corretor_nome ? ` · corretor ${v.corretor_nome}` : ""} · agendado pela Mora` });

function CardVisita({ v }: { v: Visita }) {
  return (
    <div className="rounded-md border-l-2 border-[var(--series-1)] bg-info-soft px-2 py-1.5 text-xs">
      <Link to={`/leads/${v.lead_id}`} className="block truncate font-medium text-ink hover:underline">{v.nome ?? v.lead_id}</Link>
      <div className="truncate text-ink-muted">{v.bairro ?? v.imovel_id ?? "a definir"}{v.corretor_nome ? ` · ${v.corretor_nome.split(" ")[0]}` : ""}</div>
      <a href={googleCalendarUrl(evento(v))} target="_blank" rel="noreferrer" className="text-[11px] text-ink-muted hover:underline">+ Google Agenda</a>
    </div>
  );
}
