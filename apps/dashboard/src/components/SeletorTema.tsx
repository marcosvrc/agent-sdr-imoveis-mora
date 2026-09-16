import { useEffect, useRef, useState } from "react";
import { TEMAS, type Tema, aplicar, efetivo, observarSistema, salvar, temaSalvo } from "../lib/tema";
import { Ic } from "./Icons";
import { cx } from "./ui";

const ICONE: Record<Tema, keyof typeof Ic> = { claro: "sol", escuro: "lua", sistema: "monitor" };

/** Troca de tema do painel (ADR-0014).
 *
 *  Três opções e não um interruptor de dois estados: "sistema" é o padrão de quem nunca escolheu, e
 *  precisa continuar visível DEPOIS de escolher — senão a pessoa que trocou uma vez para escuro não
 *  tem como voltar a "deixa o computador decidir".
 *
 *  O ícone do botão mostra o tema EM VIGOR (sol/lua), mas o item marcado na lista é a ESCOLHA. Com
 *  "sistema" selecionado às 20h, o botão mostra lua e a marca fica em Sistema — as duas informações
 *  são diferentes e as duas importam.
 */
export function SeletorTema() {
  const [tema, setTema] = useState<Tema>(temaSalvo);
  const [aberto, setAberto] = useState(false);
  const [, redesenhar] = useState(0);
  const caixa = useRef<HTMLDivElement>(null);

  useEffect(() => { aplicar(tema); }, [tema]);
  // Escolha "sistema" acompanha o anoitecer com a aba aberta.
  useEffect(() => observarSistema(() => redesenhar((n) => n + 1)), []);
  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => { if (!caixa.current?.contains(e.target as Node)) setAberto(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setAberto(false); };
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", fora); document.removeEventListener("keydown", esc); };
  }, [aberto]);

  const emVigor = efetivo(tema);
  const IconeBotao = Ic[emVigor === "escuro" ? "lua" : "sol"];

  return (
    <div className="relative" ref={caixa}>
      <button type="button" onClick={() => setAberto((a) => !a)} aria-expanded={aberto} aria-haspopup="menu"
        title={`Tema: ${TEMAS.find((t) => t.k === tema)?.r}`}
        aria-label={`Tema do painel: ${TEMAS.find((t) => t.k === tema)?.r}. Trocar`}
        className="rounded-md p-1.5 text-ink-muted hover:bg-surface-2 hover:text-ink">
        <IconeBotao size={16} />
      </button>
      {aberto && (
        <div role="menu" className="absolute right-0 top-full z-40 mt-1.5 w-56 overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-xl">
          {TEMAS.map((t) => {
            const Icone = Ic[ICONE[t.k]];
            const marcado = t.k === tema;
            return (
              <button key={t.k} role="menuitemradio" aria-checked={marcado}
                onClick={() => { setTema(t.k); salvar(t.k); setAberto(false); }}
                className={cx("flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm hover:bg-surface-2",
                  marcado ? "text-ink" : "text-ink-muted")}>
                <Icone size={15} className="shrink-0" />
                <span className="flex-1">
                  {t.r}
                  <span className="block text-[11px] text-ink-faint">{t.dica}</span>
                </span>
                {marcado && <Ic.check size={15} className="shrink-0 text-brand-accent" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
