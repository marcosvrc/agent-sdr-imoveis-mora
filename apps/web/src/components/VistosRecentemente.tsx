import { useQuery } from "@tanstack/react-query";
import { listarImoveis } from "../lib/api";
import { idsVistos, limparVistos } from "../lib/vistos";
import { ImovelCard } from "./ImovelCard";

/** "Vistos recentemente".
 *
 *  O histórico já era coletado pelo `POST /eventos` para o agente qualificar o lead; o visitante
 *  nunca via nada em troca. Aqui ele vê — a partir da lista guardada no próprio navegador — e tem
 *  um botão para apagá-la, que é a contrapartida honesta de manter histórico de navegação.
 */
export function VistosRecentemente({ excluir, titulo = "Vistos recentemente" }: { excluir?: string; titulo?: string }) {
  const ids = idsVistos(excluir);
  const { data } = useQuery({
    queryKey: ["imoveis", "todos"],
    queryFn: () => listarImoveis({}, 200),
    enabled: ids.length > 0,
    staleTime: 5 * 60_000,
  });

  if (!ids.length || !data) return null;
  const ordem = new Map(ids.map((id, i) => [id, i]));
  const itens = data.filter((im) => ordem.has(im.id)).sort((a, b) => ordem.get(a.id)! - ordem.get(b.id)!).slice(0, 4);
  if (!itens.length) return null;

  return (
    <section aria-labelledby="vistos" className="mt-14">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 id="vistos" className="font-display text-xl font-semibold text-brand sm:text-2xl">{titulo}</h2>
        <button onClick={() => { limparVistos(); location.reload(); }}
                className="text-xs font-semibold text-ink-muted underline-offset-2 hover:text-ink hover:underline">
          Limpar histórico
        </button>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {itens.map((im) => <ImovelCard key={im.id} im={im} />)}
      </div>
    </section>
  );
}
