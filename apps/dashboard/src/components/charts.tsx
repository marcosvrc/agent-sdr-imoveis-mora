// Gráficos do painel (Recharts) seguindo as specs do dataviz: marcas finas, grid recessivo, tooltip por padrão,
// legenda para ≥2 séries, texto sempre em tokens de texto (nunca na cor da série).
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ESTAGIOS, ROTULO, type Metricas } from "../lib/api";
import { dataCurta, num } from "../lib/format";

const S1 = "var(--series-1)", S2 = "var(--series-2)", S3 = "var(--series-3)";
const ORD = ["var(--ord-1)", "var(--ord-2)", "var(--ord-3)", "var(--ord-4)", "var(--ord-5)"];
const GRID = "var(--grid)";

function TooltipBox({ active, payload, label, fmt }: { active?: boolean; payload?: { name: string; value: number; color?: string }[]; label?: string; fmt?: (v: number) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 font-medium text-ink">{label}</p>
      {payload.map((p) => <p key={p.name} className="flex items-center gap-2 text-ink-muted"><span className="h-2 w-2 rounded-sm" style={{ background: p.color }} />{p.name}<span className="ml-auto pl-3 font-medium tabular-nums text-ink">{fmt ? fmt(p.value) : num(p.value)}</span></p>)}
    </div>
  );
}

/** Série diária: leads e visitas (mesma escala, contagens) — área a 10%, linha 2px. */
export function SerieChart({ serie }: { serie: Metricas["serie"] }) {
  const data = serie.map((d) => ({ ...d, rot: dataCurta(d.dia) }));
  return (
    <ResponsiveContainer width="100%" height={240}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="rot" axisLine={false} tickLine={false} minTickGap={24} />
        <YAxis allowDecimals={false} axisLine={false} tickLine={false} width={40} />
        <Tooltip content={<TooltipBox />} cursor={{ stroke: GRID }} />
        <Legend verticalAlign="top" align="right" height={28} iconType="plainline" wrapperStyle={{ fontSize: 12, color: "#6b6b66" }} />
        <Area type="monotone" dataKey="leads" name="Leads novos" stroke={S1} fill={S1} fillOpacity={0.1} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }} />
        <Area type="monotone" dataKey="visitas" name="Visitas reservadas" stroke={S2} fill={S2} fillOpacity={0.1} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }} />
        <Area type="monotone" dataKey="mensagens" name="Mensagens recebidas" stroke={S3} fill={S3} fillOpacity={0.08} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "#fff" }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

/** Funil por estágio: rampa ordinal azul (uma cor, claro→escuro), valor na ponta. */
export function FunilChart({ estagios }: { estagios: Record<string, number> }) {
  const ordem = ["novo", "qualificando", "qualificado", "agendado", "handoff"];
  const data = ordem.map((e, i) => ({ k: e, estagio: ROTULO[e], n: estagios[e] ?? 0, cor: ORD[i] }));
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 40, top: 4, bottom: 4 }} barCategoryGap={6}>
        <XAxis type="number" allowDecimals={false} hide />
        <YAxis type="category" dataKey="estagio" width={96} axisLine={false} tickLine={false} />
        <Tooltip content={<TooltipBox />} cursor={{ fill: "rgba(0,0,0,0.03)" }} />
        <Bar dataKey="n" name="Leads" maxBarSize={18} radius={[0, 4, 4, 0]} label={{ position: "right", fontSize: 11, fill: "#121212" }}>
          {data.map((d) => <Cell key={d.k} fill={d.cor} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Distribuição em barras horizontais simples (HTML) — para poucos itens, mais legível que pizza. */
export function Distribuicao({ dados, rotulos, cor = S1, fmt = num }: { dados: Record<string, number>; rotulos?: Record<string, string>; cor?: string; fmt?: (v: number) => string }) {
  const itens = Object.entries(dados).sort((a, b) => b[1] - a[1]);
  const total = itens.reduce((s, [, v]) => s + v, 0) || 1;
  const max = Math.max(...itens.map(([, v]) => v), 1);
  if (!itens.length) return <p className="py-6 text-center text-xs text-ink-muted">Sem dados ainda.</p>;
  return (
    <ul className="space-y-2">
      {itens.map(([k, v]) => (
        <li key={k} className="grid grid-cols-[96px_1fr_auto] items-center gap-2 text-xs" title={`${rotulos?.[k] ?? k}: ${fmt(v)} (${Math.round((v / total) * 100)}%)`}>
          <span className="truncate text-ink-muted">{rotulos?.[k] ?? k.replace(/_/g, " ")}</span>
          <span className="h-2 rounded-r-sm bg-surface-2"><span className="block h-2 rounded-r-sm" style={{ width: `${(v / max) * 100}%`, background: cor }} /></span>
          <span className="w-16 text-right tabular-nums text-ink">{fmt(v)} <span className="text-ink-muted">· {Math.round((v / total) * 100)}%</span></span>
        </li>
      ))}
    </ul>
  );
}
