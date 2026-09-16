import { useEffect, useRef } from "react";
import type { Mensagem } from "../lib/api";
import { CANAL } from "../lib/format";
import { cx } from "./ui";

export function Transcricao({ msgs, altura = "h-[56vh]" }: { msgs: Mensagem[]; altura?: string }) {
  const fim = useRef<HTMLDivElement>(null);
  useEffect(() => { fim.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);
  return (
    <div tabIndex={0} role="log" aria-label="Histórico da conversa"
         className={cx("space-y-2 overflow-y-auto rounded-lg bg-canvas p-3 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-accent/40", altura)}>
      {msgs.length === 0 && <p className="py-8 text-center text-xs text-ink-muted">Sem mensagens ainda.</p>}
      {msgs.map((m) => {
        const lead = m.direcao === "in";
        const cor = lead ? "bg-surface text-ink ring-1 ring-line" : m.direcao === "corretor" ? "bg-violeta text-canvas" : "bg-brand text-brand-ink";
        return (
          <div key={m.id} className={cx("flex", lead ? "justify-start" : "justify-end")}>
            <div className={cx("max-w-[80%] rounded-2xl px-3 py-2 text-sm", cor, lead ? "rounded-bl-sm" : "rounded-br-sm")}>
              <div className="mb-0.5 text-[10px] opacity-60">{lead ? "lead" : m.direcao === "corretor" ? "corretor" : "Mora"} · {CANAL[m.canal] ?? m.canal} · {new Date(m.em).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</div>
              <div className="whitespace-pre-wrap">{m.conteudo}</div>
            </div>
          </div>
        );
      })}
      <div ref={fim} />
    </div>
  );
}
