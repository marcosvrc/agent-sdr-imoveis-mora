import { useSeo } from "../lib/seo";
import { BotaoLink, EstadoVazio } from "../lib/ui";
import { Ic } from "../components/Icones";

/** 404 com saída. Antes, qualquer rota desconhecida caía num redirect silencioso para a home —
 *  o visitante perdia o contexto e o buscador recebia 200 numa página que não existe. */
export function NaoEncontrada() {
  useSeo({ titulo: "Página não encontrada | Vértice Imóveis",
           descricao: "A página que você procurou não existe ou saiu do ar.", naoIndexar: true });
  return (
    <div className="mx-auto max-w-2xl px-4 py-20 sm:px-6">
      <EstadoVazio icone={<Ic.busca size={22} />}
                   titulo="Não encontramos esta página"
                   descricao="O endereço pode estar errado, ou o imóvel saiu do catálogo."
                   acao={<div className="flex flex-wrap justify-center gap-2">
                     <BotaoLink para="/imoveis">Ver imóveis</BotaoLink>
                     <BotaoLink para="/" variante="secundario">Voltar ao início</BotaoLink>
                   </div>} />
    </div>
  );
}
