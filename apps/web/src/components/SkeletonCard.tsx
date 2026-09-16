import { Esqueleto } from "../lib/ui";

/** Espelha a altura real do ImovelCard: esqueleto de tamanho diferente do conteúdo final
 *  produz um salto de layout (CLS) exatamente no momento em que a página termina de carregar. */
export function SkeletonCard() {
  return (
    <div className="overflow-hidden rounded-lg bg-surface shadow-card ring-1 ring-line" aria-hidden>
      <Esqueleto className="aspect-[4/3] w-full rounded-none" />
      <div className="space-y-2 p-4">
        <Esqueleto className="h-3 w-1/3" />
        <Esqueleto className="h-4 w-3/4" />
        <Esqueleto className="h-3 w-2/3" />
        <Esqueleto className="mt-2 h-6 w-1/3" />
      </div>
    </div>
  );
}
