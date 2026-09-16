import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { REGIOES, brl, nomeImovel, type Imovel } from "../lib/api";
import { caminhoImovel } from "../lib/slug";
import { Selo } from "../lib/ui";
import { Ic } from "./Icones";
import { FavoritoBotao } from "./FavoritoBotao";

/** Card do imóvel.
 *
 *  A estrutura importa: o card é um <article> e o link cobre a área toda via ::after
 *  (`.link-cobre`), em vez de o card inteiro ser um <a>. Antes, o botão de favorito ficava DENTRO
 *  do link — HTML inválido, um alvo só para o teclado e ambiguidade no leitor de tela. Agora são
 *  dois controles irmãos: "abrir a ficha" e "favoritar".
 */
export function ImovelCard({ im, prioridade }: { im: Imovel; prioridade?: boolean }) {
  const aluguel = im.operacao === "aluguel";
  const atributos = [
    { i: <Ic.cama size={15} />, t: `${im.quartos} quarto${im.quartos === 1 ? "" : "s"}` },
    im.suites > 0 ? { i: <Ic.banho size={15} />, t: `${im.suites} suíte${im.suites === 1 ? "" : "s"}` } : null,
    { i: <Ic.regua size={15} />, t: `${im.area_m2} m²` },
    im.vagas > 0 ? { i: <Ic.carro size={15} />, t: `${im.vagas} vaga${im.vagas === 1 ? "" : "s"}` } : null,
  ].filter(Boolean) as { i: ReactNode; t: string }[];

  return (
    <article className="group relative flex flex-col overflow-hidden rounded-lg bg-surface shadow-card ring-1 ring-line transition hover:-translate-y-0.5 hover:shadow-soft focus-within:ring-2 focus-within:ring-brand-accent">
      <div className="relative aspect-[4/3] overflow-hidden bg-surface-2">
        {im.fotos[0] ? (
          <img src={im.fotos[0]} alt={`Foto — ${nomeImovel(im).toLowerCase()}`}
               width={800} height={600}
               loading={prioridade ? "eager" : "lazy"} decoding="async"
               className="h-full w-full object-cover transition duration-300 group-hover:scale-105" />
        ) : (
          <div className="grid h-full place-items-center text-sm text-ink-soft">Sem foto cadastrada</div>
        )}

        <div className="absolute left-2 top-2 flex flex-col items-start gap-1.5">
          <Selo tom={aluguel ? "info" : "marca"}>{aluguel ? "Aluguel" : "Venda"}</Selo>
          {/* Rótulo antigo era "Boa renda" — não dizia o quê. Este diz para quem o imóvel serve. */}
          {im.destaque_investimento && <Selo tom="alerta">Indicado para investir</Selo>}
        </div>

        {/* z-10: acima do ::after do link, então continua clicável sem estar aninhado nele */}
        <FavoritoBotao id={im.id} nome={nomeImovel(im)} className="absolute right-2 top-2 z-10" />
      </div>

      <div className="flex flex-1 flex-col gap-1.5 p-4">
        {/* Antes: "APARTAMENTO · BROOKLIN", repetindo o tipo que o título logo abaixo já diz.
            Trocado pela localização completa, que é informação nova. */}
        <p className="text-xs font-medium uppercase tracking-wide text-ink-muted">
          {im.bairro} · {REGIOES[im.regiao] ?? im.regiao}
        </p>
        <h3 className="text-base font-semibold leading-snug text-ink">
          <Link to={caminhoImovel(im)} className="link-cobre outline-none">{nomeImovel(im)}</Link>
        </h3>
        <ul className="mt-0.5 flex flex-wrap gap-x-3 gap-y-1 text-sm text-ink-muted">
          {atributos.map((a) => <li key={a.t} className="inline-flex items-center gap-1">{a.i}{a.t}</li>)}
        </ul>
        <p className="mt-auto pt-2 font-display text-xl font-semibold text-brand">
          {brl(im.preco)}
          {aluguel && <span className="font-sans text-sm font-normal text-ink-muted">/mês</span>}
        </p>
      </div>
    </article>
  );
}
