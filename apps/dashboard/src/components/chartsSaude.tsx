// Gráficos da tela de Saúde, nas mesmas specs dos demais: marca fina, grid recessivo, tooltip
// sempre, texto em token de texto e nunca na cor da série.
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line,
         ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { type Saude } from "../lib/api";
import { num } from "../lib/format";

const S1 = "var(--series-1)", S2 = "var(--series-2)";
const GRID = "var(--grid)";
const RUIM = "var(--status-bad)";

const hhmm = (iso: string) => new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
const seg = (ms: number) => (ms >= 10_000 ? `${(ms / 1000).toFixed(0)}s` : `${(ms / 1000).toFixed(1)}s`);

function Caixa({ active, payload, label, fmt = num }: {
  active?: boolean; payload?: { name: string; value: number; color?: string }[]; label?: string; fmt?: (v: number) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 font-medium text-ink">{label}</p>
      {payload.map((p) => (
        <p key={p.name} className="flex items-center gap-2 text-ink-muted">
          <span className="h-2 w-2 rounded-sm" style={{ background: p.color }} />{p.name}
          <span className="ml-auto pl-3 font-medium tabular-nums text-ink">{fmt(p.value)}</span>
        </p>))}
    </div>
  );
}

/** Espera por hora: p95 em barra, p50 em linha, volume ao fundo.
 *
 *  Os três juntos porque separados mentem. p95 sozinho assusta numa hora de dois turnos; volume
 *  sozinho não diz se alguém esperou; p50 sozinho esconde a cauda, que é onde o cliente desiste. */
export function EsperaPorHora({ serie }: { serie: Saude["turnos"]["serie"] }) {
  const data = serie.map((p) => ({ ...p, rot: hhmm(p.hora), p95: p.p95_ms, turnos_: p.turnos }));
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="rot" axisLine={false} tickLine={false} minTickGap={24} />
        <YAxis yAxisId="ms" axisLine={false} tickLine={false} width={44} tickFormatter={(v) => seg(Number(v))} />
        <YAxis yAxisId="n" orientation="right" axisLine={false} tickLine={false} width={32} allowDecimals={false} />
        <Tooltip content={<Caixa fmt={(v) => (v > 1000 ? seg(v) : num(v))} />} cursor={{ fill: "rgba(0,0,0,0.03)" }} />
        <Legend verticalAlign="top" align="right" height={28} wrapperStyle={{ fontSize: 12, color: "#6b6b66" }} />
        <Bar yAxisId="n" dataKey="turnos_" name="Turnos" fill={GRID} maxBarSize={22} radius={[3, 3, 0, 0]} />
        <Bar yAxisId="ms" dataKey="p95" name="Espera p95" fill={S1} maxBarSize={10} radius={[3, 3, 0, 0]} />
        <Line yAxisId="n" type="monotone" dataKey="falhas" name="Com falha" stroke={RUIM} strokeWidth={2} dot={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

/** Fila e conexões ao longo do tempo, em dois painéis empilhados.
 *
 *  Dois painéis e não dois eixos no mesmo: profundidade de fila e conexões do banco não têm
 *  relação de escala, e sobrepor as duas curvas convidaria a ler correlação onde não há. */
export function FilasNoTempo({ serie }: { serie: Saude["serie_filas"] }) {
  const data = serie.map((p) => ({ ...p, rot: hhmm(p.em) }));
  return (
    <div className="space-y-2">
      <ResponsiveContainer width="100%" height={120}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="rot" axisLine={false} tickLine={false} minTickGap={32} />
          <YAxis allowDecimals={false} axisLine={false} tickLine={false} width={36} />
          <Tooltip content={<Caixa />} cursor={{ stroke: GRID }} />
          <Area type="monotone" dataKey="filas" name="Mensagens na fila (pico)" stroke={S1} fill={S1}
                fillOpacity={0.12} strokeWidth={2} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
      <ResponsiveContainer width="100%" height={100}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="rot" axisLine={false} tickLine={false} minTickGap={32} />
          <YAxis allowDecimals={false} axisLine={false} tickLine={false} width={36} />
          <Tooltip content={<Caixa />} cursor={{ stroke: GRID }} />
          <Area type="monotone" dataKey="conexoes" name="Conexões no banco (pico)" stroke={S2} fill={S2}
                fillOpacity={0.12} strokeWidth={2} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Presença de cada nó nos turnos lentos vs. nos demais.
 *
 *  Duas barras lado a lado, e não uma só com "% nos lentos": um nó que roda em todo turno marcaria
 *  100% nos lentos e pareceria o culpado. O que informa é a DIFERENÇA entre as duas barras. */
export function NosLentos({ nos }: { nos: Saude["nos_lentos"]["nos"] }) {
  const data = nos.slice(0, 8).map((n) => ({ ...n, rot: n.no }));
  return (
    <ResponsiveContainer width="100%" height={Math.max(140, data.length * 34)}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 36, top: 4, bottom: 4 }} barCategoryGap={8}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" domain={[0, 100]} axisLine={false} tickLine={false} tickFormatter={(v) => `${v}%`} />
        <YAxis type="category" dataKey="rot" width={96} axisLine={false} tickLine={false} />
        <Tooltip content={<Caixa fmt={(v) => `${v.toString().replace(".", ",")}%`} />} cursor={{ fill: "rgba(0,0,0,0.03)" }} />
        <Legend verticalAlign="top" align="right" height={28} wrapperStyle={{ fontSize: 12, color: "#6b6b66" }} />
        <Bar dataKey="pct_lentos" name="Nos turnos lentos" fill={RUIM} maxBarSize={10} radius={[0, 3, 3, 0]} />
        <Bar dataKey="pct_rapidos" name="Nos demais" fill={GRID} maxBarSize={10} radius={[0, 3, 3, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
