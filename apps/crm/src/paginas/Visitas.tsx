import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Botao, Card, Carregando, Erro, Etiqueta, Vazio, cx, entradaCls } from "../componentes/ui";
import { ErroApi, api, type Visita } from "../lib/api";
import { PROXIMAS_VISITA, STATUS_VISITA, dataHora } from "../lib/formato";

/** Agenda de visitas.
 *
 *  A tela existe por causa de uma distinção que o sistema inteiro carrega: **solicitar não
 *  agenda**. O agente pede; quem confirma é uma pessoa. Por isso as solicitadas vêm primeiro — são
 *  as que dependem de alguém aqui.
 */
export function Visitas() {
  const qc = useQueryClient();
  const [filtro, setFiltro] = useState("requested");
  const [falha, setFalha] = useState<unknown>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["visitas", filtro], queryFn: () => api.visitas({ status: filtro || undefined, limit: "100" }),
  });

  const mover = useMutation({
    mutationFn: ({ v, alvo, motivo }: { v: Visita; alvo: string; motivo: string | null }) =>
      api.moverVisita(v.id, alvo, motivo, v.version),
    onSuccess: () => {
      setFalha(null);
      qc.invalidateQueries({ queryKey: ["visitas"] });
      qc.invalidateQueries({ queryKey: ["painel"] });
    },
    onError: (e) => setFalha(e),
  });

  const disputa = falha instanceof ErroApi && falha.code === "SLOT_UNAVAILABLE";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold text-ink">Visitas</h1>
        <label className="text-sm">
          <span className="sr-only">Filtrar por situação</span>
          <select className={cx(entradaCls, "w-auto")} value={filtro} onChange={(e) => setFiltro(e.target.value)}>
            <option value="requested">Solicitadas</option>
            <option value="confirmed">Confirmadas</option>
            <option value="completed">Concluídas</option>
            <option value="cancelled">Canceladas</option>
            <option value="">Todas</option>
          </select>
        </label>
      </div>

      {falha ? <Erro erro={falha} /> : null}
      {disputa && (
        <p className="text-xs text-inkMuted">
          Outra visita foi confirmada nesse horário antes desta. O horário é de quem confirmou
          primeiro — escolha outro com o cliente.
        </p>
      )}

      {isLoading ? <Carregando linhas={5} />
        : error ? <Erro erro={error} aoTentar={() => refetch()} />
        : data!.items.length === 0 ? (
          <Vazio titulo="Nenhuma visita nesta situação"
                 descricao="A Mora solicita visitas quando o cliente pede; a confirmação é sempre de uma pessoa." />
        ) : (
          <Card semPadding>
            <ul className="divide-y divide-line">
              {data!.items.map((v) => (
                <Linha key={v.id} v={v} ocupado={mover.isPending}
                       aoMover={(alvo, motivo) => mover.mutate({ v, alvo, motivo })} />
              ))}
            </ul>
          </Card>
        )}
    </div>
  );
}

function Linha({ v, aoMover, ocupado }: {
  v: Visita; aoMover: (alvo: string, motivo: string | null) => void; ocupado: boolean;
}) {
  const [cancelando, setCancelando] = useState(false);
  const [motivo, setMotivo] = useState("");
  const proximas = PROXIMAS_VISITA[v.status] ?? [];

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 text-sm">
      <span className="font-medium tabular-nums text-ink">{dataHora(v.starts_at)}</span>
      <Etiqueta tom={STATUS_VISITA[v.status].tom}>{STATUS_VISITA[v.status].r}</Etiqueta>
      <Link to={`/oportunidades/${v.opportunity_id}`} className="text-inkMuted hover:text-acento hover:underline">
        oportunidade {v.opportunity_id.slice(0, 8)}
      </Link>
      {v.cancellation_reason && <span className="text-[11px] text-inkFaint">motivo: {v.cancellation_reason}</span>}

      <div className="ml-auto flex flex-wrap items-center gap-2">
        {cancelando ? (
          <>
            <input className={cx(entradaCls, "w-48 text-xs")} autoFocus placeholder="Motivo do cancelamento"
                   aria-label="Motivo do cancelamento" value={motivo}
                   onChange={(e) => setMotivo(e.target.value)} />
            <Botao variante="perigo" ocupado={ocupado} disabled={!motivo.trim()}
                   onClick={() => aoMover("cancelled", motivo.trim())}>Confirmar cancelamento</Botao>
            <Botao onClick={() => { setCancelando(false); setMotivo(""); }}>Voltar</Botao>
          </>
        ) : (
          proximas.map((p) => (
            <Botao key={p.alvo} ocupado={ocupado}
                   variante={p.alvo === "confirmed" ? "primario" : p.alvo === "cancelled" ? "perigo" : "normal"}
                   onClick={() => (p.pedeMotivo ? setCancelando(true) : aoMover(p.alvo, null))}>
              {p.r}
            </Botao>
          ))
        )}
        {proximas.length === 0 && !cancelando && (
          <span className="text-[11px] text-inkFaint">encerrada — reagendar cria uma nova solicitação</span>
        )}
      </div>
    </li>
  );
}
