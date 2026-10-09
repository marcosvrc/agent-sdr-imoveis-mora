import { Link } from "react-router-dom";
import { brl } from "../lib/api";
import type { ImovelCard } from "../lib/ws";

/** Card de imóvel dentro do chat.
 *
 *  `numero` é a posição na tela — o mesmo número dos botões "Qual deles?" e o que a Mora entende
 *  em "o segundo". `onVisitar` leva direto aos horários deste imóvel (`imovel:<id>`), sem passar
 *  por "Agendar visita" → "Qual deles?": antes eram dois passos, e o segundo tinha botões com o
 *  mesmo rótulo para imóveis diferentes.
 *
 *  O botão fica FORA do link: interativo dentro de interativo quebra leitor de tela e teclado. */
export function CardImovelChat({ card, numero, onVisitar }:
  { card: ImovelCard; numero?: number; onVisitar?: (card: ImovelCard) => void }) {
  return (
    <div className="max-w-[85%] overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
      <Link to={`/imoveis/${card.id}`} className="flex gap-3 hover:bg-slate-50">
        <span className="relative shrink-0">
          {card.foto ? <img src={card.foto} alt="" className="h-24 w-24 object-cover" /> : <span className="block h-24 w-24 bg-slate-100" />}
          {numero ? (
            <span className="absolute left-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-white/95 text-xs font-bold text-ink shadow"
                  aria-label={`Opção ${numero}`}>{numero}</span>
          ) : null}
        </span>
        <span className="block py-2 pr-3 text-sm">
          <span className="block font-medium">{card.titulo}</span>
          <span className="block font-semibold text-brand-accent">{brl(card.preco)}</span>
          <span className="line-clamp-2 block text-xs text-slate-600">{card.motivo}</span>
        </span>
      </Link>
      {onVisitar ? (
        <div className="flex border-t border-slate-100">
          <button type="button" onClick={() => onVisitar(card)}
                  aria-label={`Quero visitar ${numero ? `a opção ${numero}, ` : ""}${card.titulo}`}
                  className="min-h-9 flex-1 px-3 py-2 text-sm font-medium text-brand-accent hover:bg-blue-50 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand-accent">
            Quero visitar
          </button>
        </div>
      ) : null}
    </div>
  );
}
