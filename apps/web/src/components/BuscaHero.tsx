import { useId, useState } from "react";
import { useNavigate } from "react-router-dom";
import { TIPOS } from "../lib/api";
import { Botao, Campo, Entrada, Escolha, cx } from "../lib/ui";
import { Ic } from "./Icones";

/** Busca da home. Quatro campos, um objetivo: chegar ao catálogo já filtrado.
 *  O refinamento fino (suíte, vaga, área) fica na página de resultados — pedir onze decisões antes
 *  do primeiro resultado é a forma mais confiável de perder a visita. */
export function BuscaHero() {
  const nav = useNavigate();
  const id = useId();
  const [operacao, setOperacao] = useState("venda");
  const [texto, setTexto] = useState("");
  const [tipo, setTipo] = useState("");
  const [quartos, setQuartos] = useState("");

  const buscar = (e: React.FormEvent) => {
    e.preventDefault();
    const qs = new URLSearchParams({ operacao, ...(texto ? { texto } : {}), ...(tipo ? { tipo } : {}), ...(quartos ? { quartos } : {}) });
    nav(`/imoveis?${qs}`);
  };

  return (
    <form onSubmit={buscar} aria-label="Buscar imóveis"
          className="rounded-xl bg-surface p-3 shadow-soft ring-1 ring-line sm:p-4">
      <div role="group" aria-label="Comprar ou alugar" className="mb-3 flex gap-1 rounded-md bg-surface-2 p-1 text-sm font-medium">
        {[{ v: "venda", r: "Comprar" }, { v: "aluguel", r: "Alugar" }].map((o) => (
          <button type="button" key={o.v} onClick={() => setOperacao(o.v)} aria-pressed={operacao === o.v}
                  className={cx("alvo-toque flex-1 rounded-sm transition",
                                operacao === o.v ? "bg-surface text-brand shadow-sm" : "text-ink-muted hover:text-ink")}>
            {o.r}
          </button>
        ))}
      </div>

      <div className="grid gap-3">
        <Campo rotulo="Onde você quer morar?" id={`${id}-texto`}>
          <div className="relative">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft"><Ic.local size={17} /></span>
            <Entrada id={`${id}-texto`} className="pl-9" type="search" placeholder="Bairro, região ou palavra-chave"
                     value={texto} onChange={(e) => setTexto(e.target.value)} />
          </div>
        </Campo>

        <div className="grid gap-3 sm:grid-cols-2">
          <Campo rotulo="Tipo" id={`${id}-tipo`}>
            <Escolha id={`${id}-tipo`} value={tipo} onChange={(e) => setTipo(e.target.value)}>
              <option value="">Qualquer tipo</option>
              {Object.entries(TIPOS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </Escolha>
          </Campo>
          <Campo rotulo="Quartos" id={`${id}-q`}>
            <Escolha id={`${id}-q`} value={quartos} onChange={(e) => setQuartos(e.target.value)}>
              <option value="">Qualquer</option>
              {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}+ quartos</option>)}
            </Escolha>
          </Campo>
        </div>

        <Botao type="submit" largo tamanho="lg" icone={<Ic.busca size={18} />}>Ver imóveis</Botao>
      </div>
    </form>
  );
}
