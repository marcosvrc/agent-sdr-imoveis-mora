import { useEffect } from "react";
import { brl, type Imovel } from "../lib/api";
import { Botao, cx } from "../lib/ui";
import { Ic } from "./Icones";

/** Barra fixa de conversão no celular.
 *
 *  Na versão anterior o botão "conversar sobre este imóvel" vivia num <aside> que, no mobile,
 *  empilha DEPOIS da descrição e dos pontos de referência: o principal ponto de conversão da ficha
 *  ficava a duas telas de rolagem do preço. Aqui ele acompanha a página, junto do valor — que é o
 *  contexto que a pessoa precisa ter na cabeça na hora de decidir falar com alguém.
 */
export function BarraCtaMobile({ im, aoConversar }: { im: Imovel; aoConversar: () => void }) {
  // Enquanto a barra existe, o lançador do chat sobe (regra `.com-barra-cta` em index.css). Sem
  // isso ele ficava por cima do botão e cortava o texto ao meio — visto na captura de 390px.
  useEffect(() => {
    document.body.classList.add("com-barra-cta");
    return () => document.body.classList.remove("com-barra-cta");
  }, []);

  return (
    <div className={cx("fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface px-4 py-3 shadow-soft",
                       "pb-[max(0.75rem,env(safe-area-inset-bottom))] md:hidden")}>
      <div className="flex items-center gap-3">
        <div className="min-w-0">
          <p className="truncate font-display text-lg font-semibold leading-tight text-brand">
            {brl(im.preco)}{im.operacao === "aluguel" && <span className="font-sans text-xs font-normal text-ink-muted">/mês</span>}
          </p>
          <p className="truncate text-xs text-ink-muted">{im.bairro} · {im.area_m2} m²</p>
        </div>
        <Botao className="ml-auto shrink-0" icone={<Ic.chat size={16} />} onClick={aoConversar}>
          Falar sobre o imóvel
        </Botao>
      </div>
    </div>
  );
}
