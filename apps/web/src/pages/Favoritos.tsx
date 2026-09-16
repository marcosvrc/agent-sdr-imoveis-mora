import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { listarImoveis } from "../lib/api";
import { useSeo } from "../lib/seo";
import { BotaoLink, EstadoVazio } from "../lib/ui";
import { ImovelCard } from "../components/ImovelCard";
import { SkeletonCard } from "../components/SkeletonCard";
import { Migalha } from "../components/Migalha";
import { Ic } from "../components/Icones";
import { useFavoritos } from "../store/favoritos";

export function Favoritos() {
  const ids = useFavoritos((s) => s.ids);
  const { data, isLoading } = useQuery({
    queryKey: ["imoveis", "todos"],
    queryFn: () => listarImoveis({}, 200),
    enabled: ids.length > 0,          // sem favorito não há o que buscar
    staleTime: 5 * 60_000,
  });
  const salvos = useMemo(() => (data ?? []).filter((im) => ids.includes(im.id)), [data, ids]);

  // Lista pessoal guardada no navegador: não há o que um buscador indexe aqui.
  useSeo({ titulo: "Meus favoritos | Vértice Imóveis",
           descricao: "Os imóveis que você salvou neste navegador.", caminho: "/favoritos", naoIndexar: true });

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      <Migalha itens={[{ rotulo: "Início", para: "/" }, { rotulo: "Favoritos" }]} />
      <h1 className="mt-3 font-display text-2xl font-semibold text-brand sm:text-3xl">Meus favoritos</h1>
      <p className="mt-1 text-sm text-ink-muted">
        Ficam salvos neste navegador — não pedimos cadastro para você guardar um imóvel.
        {ids.length > 0 && ` ${ids.length} ${ids.length === 1 ? "imóvel salvo" : "imóveis salvos"}.`}
      </p>

      {ids.length > 0 && isLoading && (
        <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: Math.min(ids.length, 3) }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      )}

      {ids.length === 0 && (
        <div className="mt-6">
          <EstadoVazio icone={<Ic.coracao size={22} />}
                       titulo="Você ainda não salvou nenhum imóvel"
                       descricao="Toque no coração de qualquer imóvel para guardá-lo aqui e comparar depois."
                       acao={<BotaoLink para="/imoveis">Explorar catálogo</BotaoLink>} />
        </div>
      )}

      {salvos.length > 0 && (
        <ul className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {salvos.map((im, i) => <li key={im.id}><ImovelCard im={im} prioridade={i < 3} /></li>)}
        </ul>
      )}
    </div>
  );
}
