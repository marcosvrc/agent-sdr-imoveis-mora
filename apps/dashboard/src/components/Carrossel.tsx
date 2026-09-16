import { useCallback, useEffect, useState } from "react";
import { Ic } from "./Icons";
import { cx } from "./ui";

/** Carrossel de fotos: setas, teclado (← →), pontos e miniaturas. Sem foto → placeholder. */
export function Carrossel({ fotos, altura = "h-64", aoRemover, capa }: { fotos: string[]; altura?: string; aoRemover?: (url: string) => void; capa?: (url: string) => void }) {
  const [i, setI] = useState(0);
  const n = fotos.length;
  useEffect(() => { if (i >= n) setI(Math.max(0, n - 1)); }, [n, i]);
  const ir = useCallback((d: number) => setI((x) => (n ? (x + d + n) % n : 0)), [n]);
  useEffect(() => { const h = (e: KeyboardEvent) => { if (e.key === "ArrowLeft") ir(-1); if (e.key === "ArrowRight") ir(1); }; window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h); }, [ir]);
  if (!n) return <div className={cx("grid place-items-center rounded-lg bg-canvas text-xs text-ink-muted", altura)}><span className="flex flex-col items-center gap-1"><Ic.building size={22} />sem fotos</span></div>;
  return (
    <div className="space-y-2">
      <div className={cx("group relative overflow-hidden rounded-lg bg-black", altura)}>
        <img src={fotos[i]} alt={`Foto ${i + 1} de ${n}`} className="h-full w-full object-contain" />
        {n > 1 && <>
          <button type="button" onClick={() => ir(-1)} aria-label="Foto anterior" className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-surface p-1.5 text-ink shadow opacity-0 transition group-hover:opacity-100 focus:opacity-100"><Ic.chevronLeft size={18} /></button>
          <button type="button" onClick={() => ir(1)} aria-label="Próxima foto" className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-surface p-1.5 text-ink shadow opacity-0 transition group-hover:opacity-100 focus:opacity-100"><Ic.chevronRight size={18} /></button>
          <div className="absolute bottom-2 left-1/2 flex -translate-x-1/2 gap-1">{fotos.map((_, k) => <button type="button" key={k} onClick={() => setI(k)} aria-label={`Ir para a foto ${k + 1}`} className={cx("h-1.5 rounded-full transition", k === i ? "w-4 bg-surface" : "w-1.5 bg-white/60")} />)}</div>
        </>}
        <span className="absolute right-2 top-2 rounded-md bg-black/50 px-1.5 py-0.5 text-[11px] text-white">{i + 1}/{n}</span>
        {i === 0 && <span className="absolute left-2 top-2 rounded-md bg-surface px-1.5 py-0.5 text-[11px] font-medium text-ink">capa</span>}
      </div>
      {(n > 1 || aoRemover) && (
        <div className="flex gap-1.5 overflow-x-auto pb-1">
          {fotos.map((f, k) => (
            <div key={f} className="group/th relative shrink-0">
              <button type="button" onClick={() => setI(k)} className={cx("h-14 w-20 overflow-hidden rounded-md ring-2 transition", k === i ? "ring-brand-accent" : "ring-transparent hover:ring-line")}><img src={f} alt="" className="h-full w-full object-cover" /></button>
              {(aoRemover || capa) && (
                <span className="absolute -right-1 -top-1 hidden gap-0.5 group-hover/th:flex">
                  {capa && k !== 0 && <button type="button" onClick={() => capa(f)} title="Usar como capa" className="rounded-full bg-surface p-0.5 text-ink shadow ring-1 ring-line"><Ic.spark size={11} /></button>}
                  {aoRemover && <button type="button" onClick={() => aoRemover(f)} title="Remover foto" className="rounded-full bg-surface p-0.5 text-bad-strong shadow ring-1 ring-line"><Ic.x size={11} /></button>}
                </span>
              )}
            </div>))}
        </div>
      )}
    </div>
  );
}
