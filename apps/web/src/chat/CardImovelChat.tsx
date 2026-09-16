import { Link } from "react-router-dom";
import { brl } from "../lib/api";
import type { ImovelCard } from "../lib/ws";

export function CardImovelChat({ card }: { card: ImovelCard }) {
  return (
    <Link to={`/imoveis/${card.id}`} className="flex max-w-[85%] gap-3 overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200">
      {card.foto && <img src={card.foto} alt="" className="h-24 w-24 object-cover" />}
      <div className="py-2 pr-3 text-sm">
        <p className="font-medium">{card.titulo}</p>
        <p className="font-semibold text-brand-accent">{brl(card.preco)}</p>
        <p className="line-clamp-2 text-xs text-slate-600">{card.motivo}</p>
      </div>
    </Link>
  );
}
