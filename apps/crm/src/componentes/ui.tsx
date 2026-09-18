/** Peças da interface.
 *
 *  Três regras que atravessam tudo aqui, e que a seção 10 da especificação cobra:
 *
 *  • **estados loading / vazio / erro em toda consulta** — uma tela em branco enquanto carrega é
 *    indistinguível de uma tela em branco porque não há nada, e as duas pedem reações opostas;
 *  • **foco visível e navegação por teclado** — anel de foco em tudo que é interativo;
 *  • **nada de sucesso antes da resposta** — o botão fica ocupado até o servidor confirmar.
 */
import type { ReactNode } from "react";
import { ErroApi } from "../lib/api";

export function cx(...v: (string | false | null | undefined)[]): string {
  return v.filter(Boolean).join(" ");
}

export const foco = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-acento/60 focus-visible:ring-offset-1";

export function Card({ titulo, acoes, children, semPadding }: {
  titulo?: ReactNode; acoes?: ReactNode; children: ReactNode; semPadding?: boolean;
}) {
  return (
    <section className="flex h-full min-w-0 flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-card">
      {(titulo || acoes) && (
        <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          <h2 className="text-sm font-semibold text-ink">{titulo}</h2>
          {acoes}
        </header>
      )}
      <div className={cx("min-h-0 flex-1", !semPadding && "p-4")}>{children}</div>
    </section>
  );
}

const TONS = {
  neutro: "bg-surface2 text-inkSoft border-line",
  bom: "bg-bomSoft text-bom border-bom/20",
  alerta: "bg-alertaSoft text-alerta border-alerta/20",
  ruim: "bg-ruimSoft text-ruim border-ruim/20",
  info: "bg-infoSoft text-info border-info/20",
} as const;

export function Etiqueta({ tom = "neutro", children }: { tom?: keyof typeof TONS; children: ReactNode }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium", TONS[tom])}>
      {children}
    </span>
  );
}

export function Botao({ children, variante = "normal", ocupado, ...props }: {
  children: ReactNode; variante?: "normal" | "primario" | "perigo"; ocupado?: boolean;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const estilo = {
    normal: "border-line bg-surface text-inkSoft hover:bg-surface2",
    primario: "border-transparent bg-marca text-white hover:opacity-90",
    perigo: "border-transparent bg-ruim text-white hover:opacity-90",
  }[variante];
  return (
    <button
      {...props}
      disabled={props.disabled || ocupado}
      // `aria-busy` e não só o texto: quem usa leitor de tela precisa saber que a ação está em
      // curso sem depender de enxergar o rótulo mudar.
      aria-busy={ocupado || undefined}
      className={cx("inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition",
        "disabled:cursor-not-allowed disabled:opacity-50", estilo, foco, props.className)}
    >
      {ocupado ? "Aguarde…" : children}
    </button>
  );
}

export function Carregando({ linhas = 3 }: { linhas?: number }) {
  return (
    <div className="space-y-2" role="status" aria-live="polite">
      <span className="sr-only">Carregando…</span>
      {Array.from({ length: linhas }).map((_, i) => (
        <div key={i} className="h-9 animate-pulse rounded-md bg-surface2" />
      ))}
    </div>
  );
}

export function Vazio({ titulo, descricao }: { titulo: string; descricao?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-line px-4 py-8 text-center">
      <p className="text-sm font-medium text-ink">{titulo}</p>
      {descricao && <p className="mx-auto mt-1 max-w-md text-xs text-inkMuted">{descricao}</p>}
    </div>
  );
}

/** Erro da API em português, com o código e o request_id à mão.
 *
 *  O `request_id` aparece porque é a única ponte entre o que a pessoa viu e o que está no log do
 *  servidor — sem ele, "deu erro" é tudo o que sobra para investigar. Stack trace nunca aparece
 *  aqui: a API não devolve, e o painel não inventa.
 */
export function Erro({ erro, aoTentar }: { erro: unknown; aoTentar?: () => void }) {
  const e = erro instanceof ErroApi ? erro : null;
  return (
    <div role="alert" className="rounded-lg border border-ruim/30 bg-ruimSoft px-4 py-3">
      <p className="text-sm font-medium text-ruim">{e?.message ?? "Não foi possível carregar."}</p>
      {e && (
        <p className="mt-1 text-[11px] text-inkMuted">
          {e.code}
          {e.requestId && <> · requisição <code className="font-mono">{e.requestId.slice(0, 8)}</code></>}
        </p>
      )}
      {aoTentar && <Botao className="mt-2" onClick={aoTentar}>Tentar de novo</Botao>}
    </div>
  );
}

/** Faixa permanente exigida pela seção 10. Permanente mesmo: não fecha, não some ao rolar.
 *  Um CRM de laboratório confundido com o de verdade é como alguém liga para um "cliente". */
export function FaixaSintetica() {
  return (
    <div className="bg-alertaSoft px-4 py-1.5 text-center text-[11px] font-medium text-alerta">
      Ambiente de testes — dados sintéticos. Nenhum contato aqui é uma pessoa real.
    </div>
  );
}

export function Campo({ rotulo, children, dica }: { rotulo: string; children: ReactNode; dica?: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-inkSoft">{rotulo}</span>
      {children}
      {dica && <span className="mt-1 block text-[11px] text-inkFaint">{dica}</span>}
    </label>
  );
}

export const entradaCls = cx(
  "w-full rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm text-ink placeholder:text-inkFaint", foco);
