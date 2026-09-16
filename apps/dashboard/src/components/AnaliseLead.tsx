import type { AnaliseLead as T } from "../lib/api";
import { relativo } from "../lib/format";
import { Badge, Button, cx } from "./ui";
import { Ic } from "./Icons";

const SENT: Record<string, { r: string; tom: "good" | "neutro" | "bad" | "warn" | "info" }> = {
  positivo: { r: "Positivo", tom: "good" }, entusiasmado: { r: "Entusiasmado", tom: "good" }, neutro: { r: "Neutro", tom: "neutro" },
  ansioso: { r: "Ansioso", tom: "warn" }, negativo: { r: "Negativo", tom: "bad" }, frustrado: { r: "Frustrado", tom: "bad" } };
const TEND: Record<string, string> = { melhorando: "↗ melhorando", estavel: "→ estável", piorando: "↘ piorando" };
const PERFIL: Record<string, { r: string; d: string }> = {
  objetivo: { r: "Objetivo", d: "quer resolver rápido" }, analitico: { r: "Analítico", d: "pede dados e compara" }, cauteloso: { r: "Cauteloso", d: "teme errar, pede garantias" },
  emocional: { r: "Emocional", d: "família, sonho, sensações" }, explorador: { r: "Explorador", d: "ainda descobrindo o que quer" }, indefinido: { r: "Indefinido", d: "a conversa ainda não sustenta" } };
const ENG: Record<string, "good" | "warn" | "bad"> = { alto: "good", medio: "warn", baixo: "bad" };

/** Card "Análise da conversa": sentimento, engajamento, perfil de comunicação/decisão e recomendações. */
export function AnaliseLeadCard({ analise, analisadoEm, onAtualizar, atualizando, semMoldura }: { analise?: T | null; analisadoEm?: string | null; onAtualizar: () => void; atualizando?: boolean; semMoldura?: boolean }) {
  const botao = <Button tamanho="sm" variante="fantasma" onClick={onAtualizar} disabled={atualizando} icone={<Ic.refresh size={13} />}>{atualizando ? "Gerando…" : analise ? "Atualizar" : "Gerar análise"}</Button>;
  if (!analise) {
    if (semMoldura) return (
      <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
        <span className="rounded-full bg-surface-2 p-2.5 text-ink-muted"><Ic.spark size={20} /></span>
        <p className="text-sm font-medium text-ink">Sem análise ainda</p>
        <p className="max-w-xs text-xs text-ink-muted">A Mora lê a conversa e indica sentimento, engajamento, perfil de decisão e como abordar este lead.</p>
        <div className="mt-1">{botao}</div>
      </div>
    );
    return (
      <section className="rounded-xl border border-line bg-surface shadow-card">
        <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-3"><h2 className="text-sm font-semibold">Análise da conversa</h2>{botao}</header>
        <p className="p-4 text-sm text-ink-muted">Gerada automaticamente pela Mora quando o lead fica qualificado, agenda visita ou é encaminhado. Você também pode pedir agora.</p>
      </section>
    );
  }
  const sent = SENT[analise.sentimento] ?? { r: analise.sentimento, tom: "neutro" as const };
  const perfil = PERFIL[analise.perfil_decisao] ?? { r: analise.perfil_decisao, d: "" };
  const conf = Math.round(analise.confianca * 100);
  const Moldura = semMoldura
    ? ({ children }: { children: React.ReactNode }) => <div>{children}</div>
    : ({ children }: { children: React.ReactNode }) => <section className="rounded-xl border border-line bg-surface shadow-card">{children}</section>;
  return (
    <Moldura>
      <header className={cx("flex items-center justify-between gap-2", semMoldura ? "mb-3" : "border-b border-line px-4 py-3")}>
        <h2 className={cx("font-semibold", semMoldura ? "text-xs text-ink-muted" : "text-sm")}>Análise da conversa</h2>
        <span className="flex items-center gap-2 text-[11px] text-ink-muted">{analisadoEm && <span title={analisadoEm}>há {relativo(analisadoEm)}</span>}{botao}</span>
      </header>
      <div className={cx("space-y-4 text-sm", !semMoldura && "p-4")}>
        <p className="text-ink">{analise.resumo_perfil}</p>
        <div className="grid grid-cols-3 gap-2">
          <Tile label="Sentimento"><Badge tom={sent.tom}>{sent.r}</Badge><span className="mt-1 block text-[11px] text-ink-muted">{TEND[analise.sentimento_tendencia] ?? analise.sentimento_tendencia}</span></Tile>
          <Tile label="Engajamento"><Badge tom={ENG[analise.engajamento] ?? "neutro"}>{analise.engajamento}</Badge></Tile>
          <Tile label="Perfil de decisão"><span className="font-medium">{perfil.r}</span><span className="mt-0.5 block text-[11px] text-ink-muted">{perfil.d}</span></Tile>
        </div>
        <div>
          <div className="mb-1 flex items-center justify-between text-[11px] text-ink-muted"><span>Confiança da leitura</span><span>{conf}%</span></div>
          <div className="h-1.5 rounded-full bg-surface-2"><div className={cx("h-1.5 rounded-full", conf >= 70 ? "bg-[var(--status-good)]" : conf >= 40 ? "bg-[var(--status-warn)]" : "bg-ink-faint")} style={{ width: `${conf}%` }} /></div>
        </div>
        {analise.estilo_comunicacao && <Linha titulo="Como se comunica">{analise.estilo_comunicacao}</Linha>}
        {analise.motivadores.length > 0 && <Lista titulo="O que move a decisão" itens={analise.motivadores} />}
        {analise.objecoes.length > 0 && <Lista titulo="Objeções e dúvidas" itens={analise.objecoes} />}
        {analise.sinais_alerta.length > 0 && <Lista titulo="Sinais de alerta" itens={analise.sinais_alerta} tom="alerta" />}
        {analise.como_abordar.length > 0 && (
          <div className="rounded-lg bg-info-soft p-3">
            <p className="mb-1.5 text-xs font-semibold text-brand-accent">Como abordar</p>
            <ol className="list-decimal space-y-1 pl-4 text-ink">{analise.como_abordar.map((x, i) => <li key={i}>{x}</li>)}</ol>
          </div>
        )}
        <p className="text-[11px] text-ink-muted">Leitura inferida do texto da conversa pela Mora, para calibrar a abordagem. Não é avaliação psicológica clínica.</p>
      </div>
    </Moldura>
  );
}

function Tile({ label, children }: { label: string; children: React.ReactNode }) { return <div className="rounded-lg bg-canvas p-2.5"><p className="mb-1 text-[11px] text-ink-muted">{label}</p>{children}</div>; }
function Linha({ titulo, children }: { titulo: string; children: React.ReactNode }) { return <div><p className="text-xs font-medium text-ink-muted">{titulo}</p><p className="text-ink">{children}</p></div>; }
function Lista({ titulo, itens, tom }: { titulo: string; itens: string[]; tom?: "alerta" }) {
  return <div><p className={cx("text-xs font-medium", tom === "alerta" ? "text-warn-strong" : "text-ink-muted")}>{titulo}</p><ul className="mt-0.5 space-y-0.5">{itens.map((x, i) => <li key={i} className="flex gap-1.5"><span className={cx("mt-2 h-1 w-1 shrink-0 rounded-full", tom === "alerta" ? "bg-warn" : "bg-ink-faint")} />{x}</li>)}</ul></div>;
}
