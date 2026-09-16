/** URLs legíveis (etapa 2 do redesenho).
 *
 *  Antes: /imoveis/SP-0001 — não diz nada a quem vê o link no WhatsApp nem ao buscador.
 *  Agora: /imovel/apartamento-2-quartos-brooklin-sp-0001
 *
 *  O id continua no fim: é ele que a rota lê. Assim o slug pode mudar (o corretor corrige o bairro)
 *  sem quebrar link antigo, e não precisamos guardar slug no banco.
 */
import type { Imovel } from "./api";

export const paraSlug = (s: string) =>
  s.normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

export function slugImovel(im: Pick<Imovel, "id" | "tipo" | "quartos" | "bairro">): string {
  const quartos = im.quartos > 0 ? `-${im.quartos}-quartos` : "";
  return paraSlug(`${im.tipo}${quartos}-${im.bairro}-${im.id}`);
}

export const caminhoImovel = (im: Pick<Imovel, "id" | "tipo" | "quartos" | "bairro">) => `/imovel/${slugImovel(im)}`;

/** Extrai o id do fim do slug: "...-brooklin-sp-0001" → "SP-0001".
 *  Aceita também o id puro, para que /imovel/SP-0001 continue funcionando. */
export function idDoSlug(slug: string): string | null {
  const m = slug.match(/([a-z]{2}-\d{3,})$/i);
  return m ? m[1].toUpperCase() : null;
}
