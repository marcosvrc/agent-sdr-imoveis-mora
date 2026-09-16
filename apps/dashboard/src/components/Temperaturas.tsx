import { Link } from "react-router-dom";
import { ICONE_TEMPERATURA, cx } from "./ui";
import { Ic } from "./Icons";
import { num, pct } from "../lib/format";

type Chave = "quente" | "morno" | "frio";

/** Faixas de score definidas em services/agent/src/agent/scoring.py — mantidas em sincronia com o agente. */
const FAIXAS: { k: Chave; r: string; faixa: string; o_que: string; acao: string; cor: string; fundo: string; texto: string; anel: string }[] = [
  { k: "quente", r: "Quente", faixa: "score 60+", o_que: "cartão completo e urgência", acao: "falar agora", cor: "var(--status-bad)", fundo: "bg-bad-soft", texto: "text-bad-strong", anel: "ring-bad-line" },
  { k: "morno", r: "Morno", faixa: "score 30–59", o_que: "qualificando, sem pressa declarada", acao: "nutrir com opções", cor: "var(--status-warn)", fundo: "bg-warn-soft", texto: "text-warn-strong", anel: "ring-warn-line" },
  { k: "frio", r: "Frio", faixa: "score < 30", o_que: "pouca informação ou sem resposta", acao: "follow-up automático", cor: "var(--series-1)", fundo: "bg-info-soft", texto: "text-info-strong", anel: "ring-info-line" },
];

/** Leads por temperatura: quantos, que fatia do funil e o que fazer com cada grupo. Cada card filtra a lista de leads. */
export function LeadsPorTemperatura({ temperaturas }: { temperaturas: Record<string, number> }) {
  const total = Object.values(temperaturas).reduce((s, v) => s + v, 0);
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {FAIXAS.map((f) => {
        const n = temperaturas[f.k] ?? 0;
        const fatia = total ? n / total : 0;
        const Icone = ICONE_TEMPERATURA[f.k];
        return (
          <Link key={f.k} to={`/leads?temperatura=${f.k}`} title={`Ver leads ${f.k}s`}
            className="group rounded-xl border border-line bg-surface p-4 shadow-card transition hover:border-ink-faint hover:shadow-md">
            <div className="flex items-start justify-between gap-2">
              <span className={cx("grid h-10 w-10 place-items-center rounded-full ring-1", f.fundo, f.texto, f.anel)}><Icone size={20} /></span>
              <span className="flex items-center gap-1 text-[11px] text-ink-muted opacity-0 transition group-hover:opacity-100">ver leads <Ic.arrowRight size={12} /></span>
            </div>
            <p className="mt-3 flex items-baseline gap-2">
              <span className="text-3xl font-semibold tracking-tight tabular-nums text-ink">{num(n)}</span>
              <span className={cx("text-sm font-medium", f.texto)}>{f.r}</span>
              <span className="ml-auto text-xs tabular-nums text-ink-muted">{pct(fatia)}</span>
            </p>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-2">
              <div className="h-full rounded-full transition-[width] duration-500" style={{ width: `${fatia * 100}%`, background: f.cor }} />
            </div>
            <p className="mt-2.5 text-xs text-ink-muted">{f.o_que}</p>
            <p className="mt-1 flex items-center gap-1 text-[11px] text-ink-muted"><span className="rounded bg-surface-2 px-1.5 py-0.5 font-medium">{f.faixa}</span><span>·</span><span>{f.acao}</span></p>
          </Link>
        );
      })}
    </div>
  );
}
