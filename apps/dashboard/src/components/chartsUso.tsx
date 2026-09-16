// Gráficos da governança: consumo diário (tokens empilhados) e custo por dia. Mesmas specs do dataviz.
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Uso } from "../lib/api";
import { dataCurta, tokens as fmtTokens, usd } from "../lib/format";

const S1 = "var(--series-1)", S2 = "var(--series-2)", GRID = "var(--grid)";
const ORD = ["var(--ord-2)", "var(--ord-3)", "var(--ord-4)", "var(--ord-5)", "var(--ord-1)"];

function Box({ active, payload, label, fmt }: { active?: boolean; payload?: { name: string; value: number; color?: string }[]; label?: string; fmt: (v: number) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 font-medium text-ink">{label}</p>
      {payload.map((p) => <p key={p.name} className="flex items-center gap-2 text-ink-muted"><span className="h-2 w-2 rounded-sm" style={{ background: p.color }} />{p.name}<span className="ml-auto pl-3 font-medium tabular-nums text-ink">{fmt(p.value)}</span></p>)}
    </div>
  );
}

/** Tokens por dia, separando entrada (contexto) de saída (geração) — é a entrada que costuma explodir. */
export function TokensChart({ serie }: { serie: Uso["serie"] }) {
  const data = serie.map((d) => ({ ...d, rot: dataCurta(d.dia) }));
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -6, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="rot" axisLine={false} tickLine={false} minTickGap={24} />
        <YAxis axisLine={false} tickLine={false} width={56} tickFormatter={(v: number) => fmtTokens(v)} />
        <Tooltip content={<Box fmt={(v) => fmtTokens(v)} />} cursor={{ stroke: GRID }} />
        <Legend verticalAlign="top" align="right" height={28} iconType="plainline" wrapperStyle={{ fontSize: 12, color: "#6b6b66" }} />
        <Area type="monotone" dataKey="entrada" name="Entrada" stackId="1" stroke={S1} fill={S1} fillOpacity={0.1} strokeWidth={2} dot={false} />
        <Area type="monotone" dataKey="saida" name="Saída" stackId="1" stroke={S2} fill={S2} fillOpacity={0.1} strokeWidth={2} dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** Custo por dia em dólares. */
export function CustoChart({ serie }: { serie: Uso["serie"] }) {
  const data = serie.map((d) => ({ ...d, rot: dataCurta(d.dia) }));
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -6, bottom: 0 }} barCategoryGap={4}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="rot" axisLine={false} tickLine={false} minTickGap={24} />
        <YAxis axisLine={false} tickLine={false} width={60} tickFormatter={(v: number) => usd(v)} />
        <Tooltip content={<Box fmt={(v) => usd(v)} />} cursor={{ fill: "rgba(0,0,0,0.03)" }} />
        <Bar dataKey="custo" name="Custo" maxBarSize={18} radius={[4, 4, 0, 0]} fill={S1} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Distribuição por modelo/nó: custo com barra proporcional e chamadas. */
export function RankingUso({ linhas, rotulo, cotacao }: { linhas: { chave: string; chamadas: number; tokens: number; custo: number; latencia: number }[]; rotulo?: (k: string) => string; cotacao: number }) {
  if (!linhas.length) return <p className="py-6 text-center text-xs text-ink-muted">Sem chamadas no período.</p>;
  const max = Math.max(...linhas.map((l) => l.custo), 0.000001);
  return (
    <ul className="space-y-2.5">
      {linhas.map((l, i) => (
        <li key={l.chave} className="text-xs">
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="flex min-w-0 items-center gap-1.5"><span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: ORD[i % ORD.length] }} /><span className="truncate font-medium text-ink">{rotulo?.(l.chave) ?? l.chave}</span></span>
            <span className="shrink-0 tabular-nums text-ink">{usd(l.custo)} <span className="text-ink-muted">· R$ {(l.custo * cotacao).toFixed(2).replace(".", ",")}</span></span>
          </div>
          <div className="h-1.5 rounded-full bg-surface-2"><div className="h-1.5 rounded-full" style={{ width: `${(l.custo / max) * 100}%`, background: ORD[i % ORD.length] }} /></div>
          <p className="mt-1 text-[11px] text-ink-muted">{l.chamadas} chamadas · {fmtTokens(l.tokens)} tokens · {Math.round(l.latencia)} ms em média</p>
        </li>))}
    </ul>
  );
}
