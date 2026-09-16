import { useCallback, useEffect, useRef, useState } from "react";
import { BotaoIcone, cx } from "../lib/ui";
import { Ic } from "./Icones";

/** Galeria da ficha.
 *
 *  Correções de acessibilidade sobre a versão anterior:
 *   • as setas eram <span onClick> DENTRO do <button> que abre a tela cheia — invisíveis para o
 *     teclado e HTML inválido. Agora são <button> irmãos, fora do botão principal;
 *   • a tela cheia não prendia o foco nem o devolvia ao fechar — quem navega por teclado ficava
 *     tabulando na página atrás do fundo preto;
 *   • a troca de foto não era anunciada. Agora existe uma região viva com "foto 2 de 5".
 *
 *  Funciona com uma foto só (o caso comum na base hoje) e escala quando o corretor cadastra mais.
 */
export function GaleriaFotos({ fotos, alt }: { fotos: string[]; alt: string }) {
  const [indice, setIndice] = useState(0);
  const [tela, setTela] = useState(false);
  const varias = fotos.length > 1;
  const abriu = useRef<HTMLElement | null>(null);
  const dialogo = useRef<HTMLDivElement>(null);

  const anterior = useCallback(() => setIndice((i) => (i - 1 + fotos.length) % fotos.length), [fotos.length]);
  const proxima = useCallback(() => setIndice((i) => (i + 1) % fotos.length), [fotos.length]);

  useEffect(() => { setIndice(0); }, [fotos]);

  // Tela cheia: prende o foco, fecha no Escape e devolve o foco a quem abriu.
  useEffect(() => {
    if (!tela) return;
    abriu.current = document.activeElement as HTMLElement;
    dialogo.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") return setTela(false);
      if (e.key === "ArrowRight" && varias) return proxima();
      if (e.key === "ArrowLeft" && varias) return anterior();
      if (e.key !== "Tab") return;
      const focaveis = dialogo.current?.querySelectorAll<HTMLElement>("button");
      if (!focaveis?.length) return;
      const primeiro = focaveis[0], ultimo = focaveis[focaveis.length - 1];
      if (e.shiftKey && document.activeElement === primeiro) { e.preventDefault(); ultimo.focus(); }
      else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primeiro.focus(); }
    };
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      abriu.current?.focus();
    };
  }, [tela, varias, proxima, anterior]);

  if (!fotos.length) {
    return (
      <div className="grid aspect-[4/3] place-items-center rounded-xl bg-surface-2 text-sm text-ink-muted">
        Este imóvel ainda não tem foto cadastrada
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="relative overflow-hidden rounded-xl bg-surface-2">
        <button type="button" onClick={() => setTela(true)} className="group block w-full">
          <img src={fotos[indice]} alt={`${alt} — foto ${indice + 1} de ${fotos.length}`}
               width={800} height={600} fetchPriority="high" decoding="async"
               className="aspect-[4/3] w-full object-cover transition group-hover:scale-[1.02]" />
          <span className="absolute bottom-3 right-3 rounded-full bg-black/70 px-3 py-1.5 text-xs font-medium text-white">
            Ampliar
          </span>
        </button>

        {varias && (
          <>
            <BotaoIcone rotulo="Foto anterior" onClick={anterior}
                        className="absolute left-2 top-1/2 -translate-y-1/2 bg-surface/95 text-ink shadow-sm hover:bg-surface">
              <Ic.esquerda size={20} />
            </BotaoIcone>
            <BotaoIcone rotulo="Próxima foto" onClick={proxima}
                        className="absolute right-2 top-1/2 -translate-y-1/2 bg-surface/95 text-ink shadow-sm hover:bg-surface">
              <Ic.direita size={20} />
            </BotaoIcone>
            <p aria-live="polite" className="absolute bottom-3 left-3 rounded-full bg-black/70 px-2.5 py-1 text-[11px] font-medium text-white">
              Foto {indice + 1} de {fotos.length}
            </p>
          </>
        )}
      </div>

      {varias && (
        <ul className="flex gap-2 overflow-x-auto pb-1">
          {fotos.map((f, i) => (
            <li key={f}>
              <button type="button" onClick={() => setIndice(i)} aria-label={`Ver foto ${i + 1}`}
                      aria-current={i === indice}
                      className={cx("h-16 w-20 shrink-0 overflow-hidden rounded-sm ring-2 transition",
                                    i === indice ? "ring-brand-accent" : "ring-transparent opacity-70 hover:opacity-100")}>
                <img src={f} alt="" width={160} height={120} loading="lazy" className="h-full w-full object-cover" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {tela && (
        <div ref={dialogo} role="dialog" aria-modal="true" aria-label={`${alt} — foto ${indice + 1} de ${fotos.length}`}
             tabIndex={-1} className="fixed inset-0 z-50 grid place-items-center bg-black/90 p-4 outline-none">
          <img src={fotos[indice]} alt={`${alt} — foto ${indice + 1} de ${fotos.length}`}
               className="max-h-[85vh] max-w-full rounded-md object-contain" />
          {varias && (
            <>
              <BotaoIcone rotulo="Foto anterior" onClick={anterior} className="absolute left-4 top-1/2 -translate-y-1/2 bg-white/10 text-white hover:bg-white/25">
                <Ic.esquerda size={24} />
              </BotaoIcone>
              <BotaoIcone rotulo="Próxima foto" onClick={proxima} className="absolute right-4 top-1/2 -translate-y-1/2 bg-white/10 text-white hover:bg-white/25">
                <Ic.direita size={24} />
              </BotaoIcone>
            </>
          )}
          <BotaoIcone rotulo="Fechar galeria" onClick={() => setTela(false)}
                      className="absolute right-4 top-4 bg-white/10 text-white hover:bg-white/25">
            <Ic.fechar size={22} />
          </BotaoIcone>
        </div>
      )}
    </div>
  );
}
