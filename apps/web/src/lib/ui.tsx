/** Primitivos da vitrine. Existem porque o botão principal estava reescrito à mão em doze
 *  lugares, cada um com um raio e um padding — inconsistência que o visitante lê como desleixo.
 *
 *  Regra: componente daqui não sabe de imóvel. Quem sabe de imóvel é `components/`. */
import { forwardRef } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { Link } from "react-router-dom";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

type Variante = "primario" | "secundario" | "fantasma" | "contraste";
type Tamanho = "sm" | "md" | "lg";

const VARIANTE: Record<Variante, string> = {
  primario: "bg-brand-accent text-white hover:bg-brand-accentDark shadow-sm",
  secundario: "bg-surface text-ink ring-1 ring-line-forte hover:ring-brand-accent hover:text-brand-accentDark",
  fantasma: "text-ink-muted hover:bg-surface-2 hover:text-ink",
  contraste: "bg-white text-brand hover:bg-brand-suave shadow-soft",   // sobre fundo escuro
};
const TAMANHO: Record<Tamanho, string> = {
  sm: "h-9 px-3 text-sm gap-1.5",
  md: "h-11 px-4 text-sm gap-2",       // 44px: alvo de toque mínimo
  lg: "h-12 px-6 text-base gap-2",
};
const base = "inline-flex items-center justify-center rounded-md font-semibold transition disabled:opacity-50 disabled:pointer-events-none";

export function Botao({ variante = "primario", tamanho = "md", largo, icone, children, className, ...p }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variante?: Variante; tamanho?: Tamanho; largo?: boolean; icone?: ReactNode }) {
  return (
    <button {...p} className={cx(base, VARIANTE[variante], TAMANHO[tamanho], largo && "w-full", className)}>
      {icone}{children}
    </button>
  );
}

/** Mesmo visual do botão, mas navega. Link e botão não são intercambiáveis para quem usa
 *  leitor de tela ou abre em nova aba — então o componente é outro, e não uma prop. */
export function BotaoLink({ para, variante = "primario", tamanho = "md", largo, externo, icone, children, className, ...p }:
  { para: string; variante?: Variante; tamanho?: Tamanho; largo?: boolean; externo?: boolean; icone?: ReactNode; children: ReactNode; className?: string } & Record<string, unknown>) {
  const cls = cx(base, VARIANTE[variante], TAMANHO[tamanho], largo && "w-full", className);
  if (externo) return <a href={para} target="_blank" rel="noreferrer" className={cls} {...p}>{icone}{children}</a>;
  return <Link to={para} className={cls} {...p}>{icone}{children}</Link>;
}

/** forwardRef porque quem abre um menu precisa devolver o foco para o próprio botão ao fechar. */
export const BotaoIcone = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { rotulo: string; children: ReactNode }>(
  function BotaoIcone({ rotulo, children, className, ...p }, ref) {
    return (
      <button ref={ref} type="button" {...p} aria-label={rotulo} title={rotulo}
        className={cx("alvo-toque grid place-items-center rounded-full text-ink-muted transition hover:bg-surface-2 hover:text-ink", className)}>
        {children}
      </button>
    );
  });

export function Cartao({ children, className, comoArtigo }: { children: ReactNode; className?: string; comoArtigo?: boolean }) {
  const Tag = comoArtigo ? "article" : "div";
  return <Tag className={cx("rounded-lg bg-surface shadow-card ring-1 ring-line", className)}>{children}</Tag>;
}

const TOM = {
  neutro: "bg-surface-2 text-ink-muted",
  info: "bg-brand-suave text-brand-accentDark",
  marca: "bg-brand text-white",
  ok: "bg-emerald-50 text-estado-ok",
  alerta: "bg-amber-50 text-estado-alerta",
} as const;

export function Selo({ tom = "neutro", icone, children, className }:
  { tom?: keyof typeof TOM; icone?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold", TOM[tom], className)}>
      {icone}{children}
    </span>
  );
}

/** Filtro ativo. O × é decorativo: quem lê tela ouve "remover filtro bairro: Brooklin". */
export function Chip({ children, aoRemover, rotuloRemover }: { children: ReactNode; aoRemover?: () => void; rotuloRemover?: string }) {
  if (!aoRemover) return <span className="inline-flex items-center rounded-full bg-surface-2 px-3 py-1.5 text-xs font-medium text-ink-muted">{children}</span>;
  return (
    <button onClick={aoRemover} aria-label={rotuloRemover}
      className="inline-flex items-center gap-1.5 rounded-full bg-surface-2 px-3 py-1.5 text-xs font-medium text-ink-muted transition hover:bg-line hover:text-ink">
      {children}<span aria-hidden className="text-base leading-none">×</span>
    </button>
  );
}

const campo = "h-11 w-full rounded-md border border-line-forte bg-surface px-3 text-sm text-ink placeholder:text-ink-soft focus:border-brand-accent focus:outline-none";

export function Campo({ rotulo, dica, id, children }: { rotulo: string; dica?: string; id: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-xs font-medium text-ink-muted">{rotulo}</label>
      {children}
      {dica && <p className="text-[11px] text-ink-soft">{dica}</p>}
    </div>
  );
}

export function Entrada({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...p} className={cx(campo, className)} />;
}

export function Escolha({ className, children, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...p} className={cx(campo, "pr-8", className)}>{children}</select>;
}

export function Esqueleto({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-md bg-line", className)} aria-hidden />;
}

export function EstadoVazio({ titulo, descricao, acao, icone }:
  { titulo: string; descricao?: string; acao?: ReactNode; icone?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-line-forte bg-surface p-10 text-center">
      {icone && <div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-full bg-surface-2 text-ink-muted">{icone}</div>}
      <p className="font-medium text-ink">{titulo}</p>
      {descricao && <p className="mx-auto mt-1 max-w-sm text-sm text-ink-muted">{descricao}</p>}
      {acao && <div className="mt-4 flex justify-center">{acao}</div>}
    </div>
  );
}

/** Erro com saída. Um parágrafo vermelho sem botão deixa o visitante sem o que fazer. */
export function EstadoErro({ titulo = "Não conseguimos carregar agora", descricao, aoTentar }:
  { titulo?: string; descricao?: string; aoTentar?: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
      <p className="font-medium text-estado-erro">{titulo}</p>
      <p className="mx-auto mt-1 max-w-sm text-sm text-red-900/80">{descricao ?? "A conexão pode ter falhado. Tentar de novo costuma resolver."}</p>
      {aoTentar && <div className="mt-4 flex justify-center"><Botao variante="secundario" onClick={aoTentar}>Tentar de novo</Botao></div>}
    </div>
  );
}

export function Secao({ titulo, descricao, acao, children, className, id }:
  { titulo: string; descricao?: string; acao?: ReactNode; children: ReactNode; className?: string; id?: string }) {
  return (
    <section id={id} className={cx("mx-auto max-w-6xl px-4 py-12 sm:px-6 sm:py-14", className)}>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-2xl font-semibold text-brand sm:text-3xl">{titulo}</h2>
          {descricao && <p className="mt-1 max-w-xl text-sm text-ink-muted">{descricao}</p>}
        </div>
        {acao}
      </div>
      {children}
    </section>
  );
}
