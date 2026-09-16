// Componentes base do painel: um vocabulário visual único para todas as telas.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Ic } from "./Icons";
import { ROTULO } from "../lib/api";
import { pct } from "../lib/format";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

export function PageHeader({ titulo, descricao, acoes }: { titulo: string; descricao?: string; acoes?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-xl font-semibold tracking-tight text-ink">{titulo}</h1>{descricao && <p className="mt-0.5 text-sm text-ink-muted">{descricao}</p>}</div>
      {acoes && <div className="flex flex-wrap items-center gap-2">{acoes}</div>}
    </div>
  );
}

export function Card({ children, className, titulo, acoes, semPadding }: { children: ReactNode; className?: string; titulo?: ReactNode; acoes?: ReactNode; semPadding?: boolean }) {
  return (
    <section className={cx("min-w-0 rounded-xl border border-line bg-surface shadow-card", className)}>
      {(titulo || acoes) && (
        <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-3">
          <h2 className="text-sm font-semibold text-ink">{titulo}</h2>{acoes}
        </header>
      )}
      <div className={semPadding ? "" : "p-4"}>{children}</div>
    </section>
  );
}

/** Stat tile: label · valor · delta vs período anterior (cor = direção × se subir é bom).
 *  Com `ajuda`, o tile explica de onde o número sai quando clicado — indicador sem definição
 *  vira chute, e a definição é o que muda a decisão de quem olha. */
export function StatTile({ label, valor, delta, subirEBom = true, sufixo, icone, destaque, ajuda }: {
  label: string; valor: string; delta?: number | null; subirEBom?: boolean; sufixo?: string;
  icone?: keyof typeof Ic; destaque?: boolean; ajuda?: ReactNode }) {
  const Icon = icone ? Ic[icone] : null;
  const bom = delta != null && (delta === 0 || (delta > 0) === subirEBom);
  const [aberto, setAberto] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => { if (!caixa.current?.contains(e.target as Node)) setAberto(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setAberto(false); };
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", fora); document.removeEventListener("keydown", esc); };
  }, [aberto]);

  const corpo = (
    <>
      <div className="flex items-start justify-between gap-2">
        <p className="text-left text-xs font-medium text-ink-muted">{label}</p>
        {ajuda
          ? <span className={cx("rounded-md p-1.5 transition", aberto ? "bg-brand text-brand-ink" : "bg-surface-2 text-ink-muted group-hover:text-ink")}>
              {Icon ? <Icon size={14} /> : <Ic.info size={14} />}
            </span>
          : Icon && <span className="rounded-md bg-surface-2 p-1.5 text-ink-muted"><Icon size={14} /></span>}
      </div>
      <p className={cx("mt-1 truncate text-left font-semibold tracking-tight text-ink", destaque ? "text-2xl sm:text-3xl" : "text-xl sm:text-2xl")}>{valor}{sufixo && <span className="ml-1 text-sm font-normal text-ink-muted">{sufixo}</span>}</p>
      {delta !== undefined && (
        <p className={cx("mt-1 flex items-center gap-1 text-xs", delta == null ? "text-ink-muted" : bom ? "text-status-good" : "text-status-bad")}>
          {delta == null ? <span>sem base de comparação</span> : <>{delta > 0 ? <Ic.arrowUp size={12} /> : delta < 0 ? <Ic.arrowDown size={12} /> : null}<span>{delta === 0 ? "estável" : pct(Math.abs(delta))}</span><span className="text-ink-muted">vs. período anterior</span></>}
        </p>
      )}
    </>
  );

  // `h-full` nas duas formas: o tile sem ajuda é o próprio item do grid (estica sozinho), mas o
  // tile com ajuda é um <button> DENTRO de um wrapper posicionado — o wrapper estica e o botão não.
  // Sem isto, um tile com uma linha a mais (a variação vs. período anterior) fica visivelmente maior
  // que os vizinhos da mesma linha, que é o que acontecia em "Encaminhados ao corretor".
  const caixaCls = cx("flex h-full min-w-0 flex-col rounded-xl border border-line bg-surface p-4 shadow-card",
                      destaque && "ring-1 ring-[var(--anel-foco)]");
  if (!ajuda) return <div className={caixaCls}>{corpo}</div>;

  return (
    <div className="relative min-w-0" ref={caixa}>
      <button type="button" onClick={() => setAberto((a) => !a)} aria-expanded={aberto}
        aria-label={`${label}: ${valor}. Ver como este número é calculado`}
        className={cx(caixaCls, "group w-full cursor-help text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--anel-foco)]",
          aberto && "ring-1 ring-[var(--anel-foco)]")}>
        {corpo}
      </button>
      {aberto && (
        <div role="tooltip"
          className="absolute left-0 right-0 top-full z-40 mt-1.5 rounded-xl border border-line bg-surface p-3 text-xs leading-relaxed text-ink-soft shadow-xl">
          <span className="mb-1 flex items-center gap-1.5 font-medium text-ink"><Ic.info size={13} />Como este número é calculado</span>
          {ajuda}
        </div>
      )}
    </div>
  );
}

/** Ponto de interrogação com explicação — para números que não são StatTile (seções, cabeçalhos). */
export function Ajuda({ children, titulo = "Como este número é calculado", alinhar = "direita" }:
  { children: ReactNode; titulo?: string; alinhar?: "direita" | "esquerda" }) {
  const [aberto, setAberto] = useState(false);
  const caixa = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => { if (!caixa.current?.contains(e.target as Node)) setAberto(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setAberto(false); };
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", fora); document.removeEventListener("keydown", esc); };
  }, [aberto]);
  return (
    <span className="relative inline-flex" ref={caixa}>
      <button type="button" onClick={() => setAberto((a) => !a)} aria-expanded={aberto} aria-label={titulo}
        className={cx("grid h-5 w-5 place-items-center rounded-full border text-[10px] font-semibold transition",
          aberto ? "border-brand bg-brand text-brand-ink" : "border-line text-ink-muted hover:border-ink-faint hover:text-ink")}>?</button>
      {aberto && (
        <span role="tooltip"
          className={cx("absolute top-7 z-40 w-72 rounded-xl border border-line bg-surface p-3 text-left text-xs font-normal leading-relaxed text-ink-soft shadow-xl",
            alinhar === "direita" ? "right-0" : "left-0")}>
          <span className="mb-1 flex items-center gap-1.5 font-medium text-ink"><Ic.info size={13} />{titulo}</span>
          {children}
        </span>
      )}
    </span>
  );
}

export function Badge({ children, tom = "neutro", icone }: { children: ReactNode; tom?: "neutro" | "info" | "good" | "warn" | "bad" | "violet"; icone?: ReactNode }) {
  const cls = { neutro: "bg-surface-2 text-ink", info: "bg-info-soft text-info-strong", good: "bg-good-soft text-good-strong", warn: "bg-warn-soft text-warn-strong", bad: "bg-bad-soft text-bad-strong", violet: "bg-violeta-soft text-violeta-strong" }[tom];
  return <span className={cx("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium", cls)}>{icone}{children}</span>;
}

/** Ícone por temperatura, usado no badge e nos cards da visão geral. */
export const ICONE_TEMPERATURA = { quente: Ic.flame, morno: Ic.thermometer, frio: Ic.snowflake } as const;

export function Temperatura({ t }: { t: string }) {
  const Icone = ICONE_TEMPERATURA[t as keyof typeof ICONE_TEMPERATURA];
  const tom = ({ quente: "bad", morno: "warn", frio: "info" } as const)[t as "quente"] ?? "neutro";
  return <Badge tom={tom} icone={Icone ? <Icone size={11} /> : null}>{t}</Badge>;
}

export function Estagio({ e }: { e: string }) {
  const tom = ({ novo: "neutro", qualificando: "info", qualificado: "info", agendado: "good", handoff: "violet", inativo: "warn", frio: "neutro" } as const)[e as "novo"] ?? "neutro";
  return <Badge tom={tom}>{ROTULO[e] ?? e}</Badge>;
}

export function Button({ children, variante = "secundario", tamanho = "md", icone, className, ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variante?: "primario" | "secundario" | "fantasma" | "perigo"; tamanho?: "sm" | "md"; icone?: ReactNode }) {
  const base = "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--anel-foco)] disabled:cursor-not-allowed disabled:opacity-50";
  const v = { primario: "bg-brand text-brand-ink hover:opacity-90", secundario: "border border-line bg-surface text-ink hover:bg-surface-2", fantasma: "text-ink-muted hover:bg-surface-2 hover:text-ink", perigo: "bg-bad text-canvas hover:opacity-90" }[variante];
  const t = tamanho === "sm" ? "h-8 px-2.5 text-xs" : "h-9 px-3.5 text-sm";
  return <button className={cx(base, v, t, className)} {...p}>{icone}{children}</button>;
}

export const inputCls = "h-9 rounded-lg border border-line bg-surface px-3 text-sm text-ink placeholder:text-ink-faint focus:border-brand-accent focus:outline-none focus:ring-2 focus:ring-[var(--anel-foco)]";
const larg = (c?: string) => (c && /\bw-/.test(c) ? "" : "w-full");
export function Input(p: React.InputHTMLAttributes<HTMLInputElement>) { return <input {...p} className={cx(inputCls, larg(p.className), p.className)} />; }
export function Select({ children, ...p }: React.SelectHTMLAttributes<HTMLSelectElement>) { return <select {...p} className={cx(inputCls, "pr-8", larg(p.className), p.className)}>{children}</select>; }
export function Field({ label, children, dica }: { label: string; children: ReactNode; dica?: string }) {
  return <label className="block text-sm"><span className="mb-1 block text-xs font-medium text-ink-muted">{label}</span>{children}{dica && <span className="mt-1 block text-[11px] text-ink-faint">{dica}</span>}</label>;
}
export function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <button type="button" role="switch" aria-checked={on} onClick={() => onChange(!on)} className="inline-flex items-center gap-2 text-left text-sm text-ink">
      <span className={cx("relative h-5 w-9 rounded-full transition", on ? "bg-brand-accent" : "bg-ink-faint")}><span className={cx("absolute top-0.5 h-4 w-4 rounded-full bg-surface shadow transition", on ? "left-[18px]" : "left-0.5")} /></span>{label}
    </button>
  );
}

export function EmptyState({ titulo, descricao, acao, icone = "info" }: { titulo: string; descricao?: string; acao?: ReactNode; icone?: keyof typeof Ic }) {
  const Icon = Ic[icone];
  return (
    <div className="flex flex-col items-center justify-center px-4 py-10 text-center">
      <span className="mb-2 rounded-full bg-surface-2 p-2.5 text-ink-muted"><Icon size={20} /></span>
      <p className="text-sm font-medium text-ink">{titulo}</p>{descricao && <p className="mt-0.5 max-w-sm text-xs text-ink-muted">{descricao}</p>}{acao && <div className="mt-3">{acao}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) { return <div className={cx("animate-pulse rounded-md bg-surface-2", className)} />; }

/** Painel lateral (detalhe/edição) — fecha com Esc ou clique fora. */
export function Drawer({ aberto, onFechar, titulo, children, rodape, largura = "max-w-lg" }: { aberto: boolean; onFechar: () => void; titulo: ReactNode; children: ReactNode; rodape?: ReactNode; largura?: string }) {
  useEffect(() => { if (!aberto) return; const h = (e: KeyboardEvent) => e.key === "Escape" && onFechar(); window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h); }, [aberto, onFechar]);
  if (!aberto) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal>
      <div className="absolute inset-0 bg-black/50 backdrop-blur-[1px]" onClick={onFechar} />
      <aside className={cx("relative flex h-full w-full flex-col bg-surface shadow-2xl", largura)}>
        <header className="flex items-center justify-between border-b border-line px-5 py-3"><h2 className="text-base font-semibold text-ink">{titulo}</h2><Button variante="fantasma" tamanho="sm" onClick={onFechar} aria-label="Fechar"><Ic.x size={16} /></Button></header>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {rodape && <footer className="flex items-center justify-end gap-2 border-t border-line px-5 py-3">{rodape}</footer>}
      </aside>
    </div>
  );
}

/** Abas: evita empilhar painéis concorrentes numa coluna longa. */
export function Tabs<T extends string>({ abas, atual, onMudar }: { abas: { k: T; r: string; badge?: ReactNode }[]; atual: T; onMudar: (k: T) => void }) {
  return (
    <div role="tablist" className="flex gap-1 border-b border-line px-2">
      {abas.map((a) => (
        <button key={a.k} role="tab" aria-selected={atual === a.k} onClick={() => onMudar(a.k)}
          className={cx("-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-medium transition",
            atual === a.k ? "border-brand text-ink" : "border-transparent text-ink-muted hover:text-ink")}>
          {a.r}{a.badge}
        </button>))}
    </div>
  );
}

/** Popup centralizado (modal) — fecha com Esc, clique fora ou no X. */
export function Modal({ aberto, onFechar, titulo, children, rodape, largura = "max-w-2xl" }: { aberto: boolean; onFechar: () => void; titulo: ReactNode; children: ReactNode; rodape?: ReactNode; largura?: string }) {
  useEffect(() => { if (!aberto) return; const h = (e: KeyboardEvent) => e.key === "Escape" && onFechar(); window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h); }, [aberto, onFechar]);
  if (!aberto) return null;
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4" role="dialog" aria-modal>
      <div className="absolute inset-0 bg-black/50 backdrop-blur-[1px]" onClick={onFechar} />
      <div className={cx("relative flex max-h-[90vh] w-full flex-col overflow-hidden rounded-2xl bg-surface shadow-2xl", largura)}>
        <header className="flex items-center justify-between border-b border-line px-5 py-3"><h2 className="text-base font-semibold text-ink">{titulo}</h2><Button variante="fantasma" tamanho="sm" onClick={onFechar} aria-label="Fechar"><Ic.x size={16} /></Button></header>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {rodape && <footer className="flex items-center justify-end gap-2 border-t border-line px-5 py-3">{rodape}</footer>}
      </div>
    </div>
  );
}

/** Diálogo de confirmação (ação destrutiva por padrão). Enter confirma, Esc cancela. */
export function ConfirmDialog({ aberto, titulo, descricao, confirmar = "Confirmar", cancelar = "Cancelar", perigo = true, carregando, onConfirmar, onCancelar, previa }: {
  aberto: boolean; titulo: string; descricao?: ReactNode; confirmar?: string; cancelar?: string; perigo?: boolean; carregando?: boolean; onConfirmar: () => void; onCancelar: () => void; previa?: ReactNode }) {
  useEffect(() => {
    if (!aberto) return;
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onCancelar(); if (e.key === "Enter" && !carregando) onConfirmar(); };
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  }, [aberto, carregando, onConfirmar, onCancelar]);
  if (!aberto) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="alertdialog" aria-modal aria-labelledby="confirm-titulo">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-[1px]" onClick={onCancelar} />
      <div className="relative w-full max-w-sm rounded-2xl bg-surface p-5 shadow-2xl">
        <div className="flex items-start gap-3">
          <span className={cx("mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-full", perigo ? "bg-bad-soft text-bad-strong" : "bg-info-soft text-brand-accent")}>{perigo ? <Ic.trash size={17} /> : <Ic.info size={17} />}</span>
          <div className="min-w-0 flex-1">
            <h2 id="confirm-titulo" className="text-base font-semibold text-ink">{titulo}</h2>
            {descricao && <p className="mt-1 text-sm text-ink-muted">{descricao}</p>}
            {previa && <div className="mt-3">{previa}</div>}
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button onClick={onCancelar} disabled={carregando}>{cancelar}</Button>
          <Button variante={perigo ? "perigo" : "primario"} onClick={onConfirmar} disabled={carregando} autoFocus>{carregando ? "Aguarde…" : confirmar}</Button>
        </div>
      </div>
    </div>
  );
}

/** Tabela com cabeçalho fixo e linhas clicáveis. */
export function Table({ colunas, children, vazio }: { colunas: (string | { h: string; cls?: string })[]; children: ReactNode; vazio?: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-surface-2/90 text-left text-[11px] uppercase tracking-wide text-ink-muted backdrop-blur">
          <tr>{colunas.map((c) => { const o = typeof c === "string" ? { h: c } : c; return <th key={o.h} className={cx("px-4 py-2.5 font-medium", o.cls)}>{o.h}</th>; })}</tr>
        </thead>
        <tbody className="divide-y divide-line">{children}</tbody>
      </table>
      {vazio}
    </div>
  );
}

export function Avatar({ nome, tamanho = 28, foto }: { nome?: string; tamanho?: number; foto?: string | null }) {
  const ini = (nome ?? "?").split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
  let h = 0; for (const ch of nome ?? "") h = (h * 31 + ch.charCodeAt(0)) % 360;
  if (foto) return <img src={foto} alt={nome ?? ""} className="shrink-0 rounded-full object-cover ring-1 ring-line" style={{ width: tamanho, height: tamanho }} />;
  return <span className="inline-flex shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white" style={{ width: tamanho, height: tamanho, background: `hsl(${h} 45% 32%)`, fontSize: Math.max(10, tamanho * 0.38) }}>{ini}</span>;
}

export const TAMANHOS_PAGINA = [10, 20, 50, 100] as const;

/** Paginação client-side. `chave` lembra o tamanho escolhido por tabela — quem trabalha com 100
 *  linhas por dia não deveria reescolher a cada visita. */
export function usePaginacao<T>(itens: T[], porPaginaInicial = 10, chave?: string) {
  const [pagina, setPagina] = useState(1);
  const [porPagina, setPorPagina] = useState(() => {
    if (!chave) return porPaginaInicial;
    try {
      const salvo = Number(localStorage.getItem(`mora.pag.${chave}`));
      return TAMANHOS_PAGINA.includes(salvo as (typeof TAMANHOS_PAGINA)[number]) ? salvo : porPaginaInicial;
    } catch { return porPaginaInicial; }          // aba anônima ou storage bloqueado
  });

  const total = Math.max(1, Math.ceil(itens.length / porPagina));
  const atual = Math.min(pagina, total);
  useEffect(() => { if (pagina > total) setPagina(total); }, [pagina, total]);

  const mudarTamanho = (n: number) => {
    // Mantém à vista o primeiro item da página atual: trocar o tamanho não pode perder o lugar.
    const primeiro = (atual - 1) * porPagina;
    setPorPagina(n);
    setPagina(Math.floor(primeiro / n) + 1);
    if (chave) { try { localStorage.setItem(`mora.pag.${chave}`, String(n)); } catch { /* ignora */ } }
  };

  return { pagina: atual, total, setPagina, porPagina, mudarTamanho,
           fatia: itens.slice((atual - 1) * porPagina, atual * porPagina),
           inicio: itens.length ? (atual - 1) * porPagina + 1 : 0,
           fim: Math.min(atual * porPagina, itens.length), n: itens.length };
}

/** `compacto`: mesma paginação, sem moldura e sem seletor de tamanho — para caber em coluna
 *  estreita (o modal do imóvel tem ~330 px). Uma página só nunca mostra controle nenhum. */
export function Paginacao({ pagina, total, setPagina, inicio, fim, n, porPagina, mudarTamanho, compacto }: {
  pagina: number; total: number; setPagina: (p: number) => void; inicio: number; fim: number; n: number;
  porPagina?: number; mudarTamanho?: (n: number) => void; compacto?: boolean }) {
  if (n === 0) return null;
  if (compacto && total === 1) return null;
  const paginas = Array.from({ length: total }, (_, i) => i + 1).filter((p) => p === 1 || p === total || Math.abs(p - pagina) <= 1);
  return (
    <div className={cx("flex flex-wrap items-center justify-between gap-2 text-xs text-ink-muted",
                       compacto ? "pt-2" : "border-t border-line px-4 py-2.5")}>
      <span className="flex items-center gap-2">
        <span>Mostrando <b className="text-ink">{inicio}–{fim}</b> de <b className="text-ink">{n}</b></span>
        {!compacto && mudarTamanho && porPagina && n > TAMANHOS_PAGINA[0] && (
          <span className="flex items-center gap-1.5">
            <label htmlFor={`por-pagina-${pagina}-${n}`} className="sr-only">Itens por página</label>
            <select id={`por-pagina-${pagina}-${n}`} value={porPagina} onChange={(e) => mudarTamanho(Number(e.target.value))}
              className="h-7 rounded-md border border-line bg-surface px-1.5 text-xs text-ink focus:border-brand-accent focus:outline-none focus:ring-2 focus:ring-[var(--anel-foco)]"
              title="Itens por página">
              {TAMANHOS_PAGINA.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <span>por página</span>
          </span>
        )}
      </span>
      <div className="flex items-center gap-1">
        <Button tamanho="sm" variante="fantasma" disabled={pagina === 1} onClick={() => setPagina(pagina - 1)} aria-label="Página anterior"><Ic.chevronLeft size={14} /></Button>
        {paginas.map((p, i) => <span key={p} className="flex items-center">{i > 0 && paginas[i - 1] !== p - 1 && <span className="px-1">…</span>}<button onClick={() => setPagina(p)} className={cx("h-8 min-w-[2rem] rounded-lg px-2 font-medium", p === pagina ? "bg-brand text-brand-ink" : "hover:bg-surface-2")} aria-current={p === pagina ? "page" : undefined}>{p}</button></span>)}
        <Button tamanho="sm" variante="fantasma" disabled={pagina === total} onClick={() => setPagina(pagina + 1)} aria-label="Próxima página"><Ic.chevronRight size={14} /></Button>
      </div>
    </div>
  );
}
