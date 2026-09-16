import { useFavoritos } from "../store/favoritos";
import { cx } from "../lib/ui";
import { Ic } from "./Icones";

/** O rótulo nomeia o imóvel porque numa lista de 24 cards "Salvar nos favoritos" repetido 24 vezes
 *  não diz a quem usa leitor de tela qual deles está sendo salvo. */
export function FavoritoBotao({ id, nome, className = "" }: { id: string; nome?: string; className?: string }) {
  const ativo = useFavoritos((s) => s.ids.includes(id));
  const alternar = useFavoritos((s) => s.alternar);
  const alvo = nome ? `: ${nome}` : "";

  return (
    <button
      type="button"
      aria-label={ativo ? `Remover dos favoritos${alvo}` : `Salvar nos favoritos${alvo}`}
      aria-pressed={ativo}
      onClick={() => alternar(id)}
      className={cx("alvo-toque grid place-items-center rounded-full bg-surface/95 shadow-sm ring-1 ring-line backdrop-blur transition hover:ring-line-forte",
        ativo ? "text-red-600" : "text-ink-muted", className)}
    >
      <Ic.coracao size={19} cheio={ativo} />
    </button>
  );
}
