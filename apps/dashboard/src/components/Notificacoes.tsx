// Sino do painel. O agente promete ao cliente que um corretor continua o atendimento — este é o
// canal por onde o corretor fica sabendo. Os avisos são persistidos, então quem estava fora
// encontra o que aconteceu na ausência, em vez de depender de estar com a tela aberta na hora.
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, type Notificacao } from "../lib/api";
import { relativo } from "../lib/format";
import { Button, cx } from "./ui";
import { Ic, type IconName } from "./Icons";

const ICONE: Record<string, IconName> = {
  "lead.encaminhado": "handoff",
  "lead.respondeu": "chat",
  "visita.agendada": "calendar",
  "briefing.pronto": "spark",
};

export function Notificacoes() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [aberto, setAberto] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);

  const { data } = useQuery({ queryKey: ["notificacoes"], queryFn: () => api.notificacoes(), refetchInterval: 20_000 });
  const lista = data?.notificacoes ?? [];
  const naoLidas = data?.nao_lidas ?? 0;

  const marcarTodas = useMutation({ mutationFn: api.marcarNotificacoesLidas, onSuccess: () => qc.invalidateQueries({ queryKey: ["notificacoes"] }) });
  const marcarUma = useMutation({ mutationFn: api.marcarNotificacaoLida, onSuccess: () => qc.invalidateQueries({ queryKey: ["notificacoes"] }) });

  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => { if (!caixa.current?.contains(e.target as Node)) setAberto(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setAberto(false); };
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", fora); document.removeEventListener("keydown", esc); };
  }, [aberto]);

  const abrir = (n: Notificacao) => {
    if (!n.lida_em) marcarUma.mutate(n.id);
    setAberto(false);
    if (n.lead_id) nav(`/leads/${n.lead_id}`);
  };

  return (
    <div className="relative" ref={caixa}>
      <button onClick={() => setAberto((a) => !a)} aria-label={`Avisos${naoLidas ? ` (${naoLidas} não lidos)` : ""}`}
        aria-expanded={aberto}
        className={cx("relative rounded-md p-1.5 hover:bg-surface-2", naoLidas ? "text-ink" : "text-ink-muted")}>
        <Ic.sino size={17} />
        {naoLidas > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-bad px-1 text-[10px] font-semibold leading-none text-canvas">
            {naoLidas > 9 ? "9+" : naoLidas}
          </span>
        )}
      </button>

      {aberto && (
        <div className="absolute right-0 top-11 z-50 w-[22rem] overflow-hidden rounded-xl border border-line bg-surface shadow-xl">
          <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
            <span className="text-sm font-semibold">Avisos</span>
            {naoLidas > 0 && <span className="text-xs text-ink-muted">{naoLidas} não {naoLidas === 1 ? "lido" : "lidos"}</span>}
            {naoLidas > 0 && (
              <Button variante="fantasma" tamanho="sm" className="ml-auto" onClick={() => marcarTodas.mutate()}>
                Marcar todos como lidos
              </Button>
            )}
          </div>

          {lista.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-ink-muted">
              Nada por aqui.<br />Você é avisado quando um lead for encaminhado, responder ou marcar visita.
            </p>
          ) : (
            <ul className="max-h-[26rem] divide-y divide-line overflow-y-auto">
              {lista.map((n) => {
                const Icone = Ic[ICONE[n.tipo] ?? "info"];
                return (
                  <li key={n.id}>
                    <button onClick={() => abrir(n)}
                      className={cx("flex w-full items-start gap-2.5 px-3 py-2.5 text-left hover:bg-surface-2", !n.lida_em && "bg-info-soft")}>
                      <span className={cx("mt-0.5 rounded-md p-1.5", n.lida_em ? "bg-surface-2 text-ink-muted" : "bg-brand text-brand-ink")}>
                        <Icone size={14} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-baseline gap-2">
                          <span className={cx("line-clamp-2 text-sm", !n.lida_em && "font-medium")}>{n.titulo}</span>
                          <span className="ml-auto shrink-0 text-[11px] text-ink-muted">{relativo(n.criada_em)}</span>
                        </span>
                        {n.detalhe && <span className="mt-0.5 line-clamp-2 block text-xs text-ink-muted">{n.detalhe}</span>}
                      </span>
                      {!n.lida_em && <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-accent" />}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
