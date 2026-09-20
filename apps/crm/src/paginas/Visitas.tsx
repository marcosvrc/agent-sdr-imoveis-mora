import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AvisoOrdemParcial, Botao, CabecalhoPagina, Card, Carregando, Erro, Etiqueta, Paginacao,
         Vazio, cx, entradaCls, usePaginaCursor } from "../componentes/ui";
import { ErroApi, api, type Visita } from "../lib/api";
import { ordenar, useFiltrosNaUrl, type Ordem } from "../lib/filtros";
import { PROXIMAS_VISITA, STATUS_VISITA, dataHora } from "../lib/formato";

const POR_PAGINA = "50";
type Campo = "quando" | "situacao";
const ORDENS = [
  { k: "", r: "Ordem do servidor (mais recentes)" },
  { k: "quando", r: "Mais próxima primeiro" },
  { k: "quando:desc", r: "Mais distante primeiro" },
  { k: "situacao", r: "Situação" },
];

/** Agenda de visitas.
 *
 *  A tela existe por causa de uma distinção que o sistema inteiro carrega: **solicitar não
 *  agenda**. O agente pede; quem confirma é uma pessoa. Por isso as solicitadas vêm primeiro — são
 *  as que dependem de alguém aqui.
 */
export function Visitas() {
  const qc = useQueryClient();
  const { valores, definir } = useFiltrosNaUrl({ situacao: "requested", ordem: "" });
  const filtro = valores.situacao;
  const [falha, setFalha] = useState<unknown>(null);
  const pag = usePaginaCursor();

  useEffect(() => { pag.reiniciar(); }, [filtro]);   // eslint-disable-line react-hooks/exhaustive-deps

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["visitas", filtro, pag.cursor],
    queryFn: () => api.visitas({ status: filtro || undefined, limit: POR_PAGINA, cursor: pag.cursor }),
  });

  const [campo, dir] = valores.ordem.split(":");
  const ordem: Ordem<Campo> | null = campo ? { campo: campo as Campo, desc: dir === "desc" } : null;
  const itens = ordenar(data?.items ?? [], ordem, (v, c) => (c === "quando" ? v.starts_at : STATUS_VISITA[v.status].r));

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
      <CabecalhoPagina titulo="Visitas"
        descricao="Solicitar não agenda: o agente pede, quem confirma é uma pessoa."
        acoes={
          <>
            <label className="text-sm">
              <span className="sr-only">Filtrar por situação</span>
              <select className={cx(entradaCls, "w-auto")} value={filtro} onChange={(e) => definir({ situacao: e.target.value })}>
                <option value="requested">Solicitadas</option>
                <option value="confirmed">Confirmadas</option>
                <option value="completed">Concluídas</option>
                <option value="cancelled">Canceladas</option>
                <option value="">Todas</option>
              </select>
            </label>
            <label className="text-sm">
              <span className="sr-only">Ordenar</span>
              <select className={cx(entradaCls, "w-auto")} value={valores.ordem} onChange={(e) => definir({ ordem: e.target.value })}>
                {ORDENS.map((o) => <option key={o.k} value={o.k}>{o.r}</option>)}
              </select>
            </label>
          </>
        } />

      {falha ? <Erro erro={falha} /> : null}
      {disputa && (
        <p className="text-xs text-inkMuted">
          Outra visita foi confirmada nesse horário antes desta. O horário é de quem confirmou
          primeiro — escolha outro com o cliente.
        </p>
      )}

      {isLoading ? <Carregando linhas={5} />
        : error ? <Erro erro={error} aoTentar={() => refetch()} />
        : itens.length === 0 ? (
          <Vazio titulo="Nenhuma visita nesta situação"
                 descricao="A Mora solicita visitas quando o cliente pede; a confirmação é sempre de uma pessoa." />
        ) : (
          <Card semPadding>
            <ul className="divide-y divide-line">
              {itens.map((v) => (
                <Linha key={v.id} v={v} ocupado={mover.isPending}
                       aoMover={(alvo, motivo) => mover.mutate({ v, alvo, motivo })} />
              ))}
            </ul>
            <AvisoOrdemParcial mostrar={!!ordem && !!data!.next_cursor} />
            <Paginacao rotulo="visitas" mostrando={itens.length} pagina={pag.pagina} primeira={pag.primeira}
                       temProxima={!!data!.next_cursor} aoVoltar={pag.voltar}
                       aoAvancar={() => data!.next_cursor && pag.avancar(data!.next_cursor)} />
          </Card>
        )}
    </div>
  );
}

function Linha({ v, aoMover, ocupado }: {
  v: Visita; aoMover: (alvo: string, motivo: string | null) => void; ocupado: boolean;
}) {
  const [cancelando, setCancelando] = useState(false);
  const [remarcando, setRemarcando] = useState(false);
  const [motivo, setMotivo] = useState("");
  const proximas = PROXIMAS_VISITA[v.status] ?? [];
  const podeRemarcar = v.status === "requested" || v.status === "confirmed";

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3 text-sm">
      <span className="font-medium tabular-nums text-ink">{dataHora(v.starts_at)}</span>
      <Etiqueta tom={STATUS_VISITA[v.status].tom}>{STATUS_VISITA[v.status].r}</Etiqueta>
      <Link to={`/oportunidades/${v.opportunity_id}`} className="text-inkMuted hover:text-acento hover:underline">
        oportunidade {v.opportunity_id.slice(0, 8)}
      </Link>
      {v.cancellation_reason && (
        /* Cancelada POR REMARCAÇÃO não é cliente perdido, e a lista precisa dizer qual das duas
           foi — era exatamente o que se perdia quando remarcar era cancelar e pedir de novo. */
        <span className="text-[11px] text-inkFaint">
          {v.rescheduled_to ? "remarcada — " : "motivo: "}{v.cancellation_reason}
        </span>
      )}

      <div className="ml-auto flex flex-wrap items-center gap-2">
        {remarcando ? (
          <Remarcar v={v} aoSair={() => setRemarcando(false)} />
        ) : cancelando ? (
          <>
            <input className={cx(entradaCls, "w-48 text-xs")} autoFocus placeholder="Motivo do cancelamento"
                   aria-label="Motivo do cancelamento" value={motivo}
                   onChange={(e) => setMotivo(e.target.value)} />
            <Botao variante="perigo" ocupado={ocupado} disabled={!motivo.trim()}
                   onClick={() => aoMover("cancelled", motivo.trim())}>Confirmar cancelamento</Botao>
            <Botao onClick={() => { setCancelando(false); setMotivo(""); }}>Voltar</Botao>
          </>
        ) : (
          <>
            {proximas.map((p) => (
              <Botao key={p.alvo} ocupado={ocupado}
                     variante={p.alvo === "confirmed" ? "primario" : p.alvo === "cancelled" ? "perigo" : "normal"}
                     onClick={() => (p.pedeMotivo ? setCancelando(true) : aoMover(p.alvo, null))}>
                {p.r}
              </Botao>
            ))}
            {podeRemarcar && <Botao onClick={() => setRemarcando(true)}>Remarcar</Botao>}
          </>
        )}
        {proximas.length === 0 && !cancelando && !remarcando && (
          /* O texto anterior dizia "reagendar cria uma nova solicitação". Deixou de ser verdade
             quando a remarcação virou operação própria — e uma visita remarcada tem para onde
             apontar, que é mais útil do que dizer o que não dá para fazer. */
          <span className="text-[11px] text-inkFaint">
            {v.rescheduled_to ? "remarcada — a visita seguinte está na lista" : "encerrada"}
          </span>
        )}
      </div>
    </li>
  );
}


/** Remarcar: escolher outro horário do MESMO imóvel, numa operação só.
 *
 *  Oferece apenas horários livres — `only_free` é o padrão da rota. Horário livre ainda pode ter
 *  solicitação pendente de outra pessoa; quem chega primeiro na confirmação leva, e o índice único
 *  do banco decide. Se perder, o servidor recusa e a visita atual continua de pé.
 */
function Remarcar({ v, aoSair }: { v: Visita; aoSair: () => void }) {
  const qc = useQueryClient();
  const [slot, setSlot] = useState("");
  const [motivo, setMotivo] = useState("");

  const livres = useQuery({
    queryKey: ["horarios", v.property_id],
    queryFn: () => api.horarios({ property_id: v.property_id, limit: "50" }),
  });
  const remarcar = useMutation({
    mutationFn: () => api.remarcarVisita(v.id, slot, motivo.trim()),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["visitas"] }); aoSair(); },
  });

  const opcoes = (livres.data?.items ?? []).filter((s) => s.id !== v.slot_id);

  return (
    <div className="flex w-full flex-wrap items-center gap-2">
      {remarcar.error ? <div className="w-full"><Erro erro={remarcar.error} /></div> : null}
      {livres.isLoading ? <span className="text-xs text-inkMuted">buscando horários…</span>
        : opcoes.length === 0 ? (
          <span className="text-xs text-alerta">
            Não há outro horário livre para este imóvel — abra um na agenda antes de remarcar.
          </span>
        ) : (
          <>
            <select className={cx(entradaCls, "w-auto text-xs")} value={slot} aria-label="Novo horário"
                    onChange={(e) => setSlot(e.target.value)}>
              <option value="">Novo horário…</option>
              {opcoes.map((s) => (
                <option key={s.id} value={s.id}>{dataHora(s.starts_at)} · {s.broker_name}</option>
              ))}
            </select>
            <input className={cx(entradaCls, "w-48 text-xs")} placeholder="Motivo (obrigatório)"
                   aria-label="Motivo da remarcação" value={motivo}
                   onChange={(e) => setMotivo(e.target.value)} />
            <Botao variante="primario" ocupado={remarcar.isPending}
                   disabled={!slot || !motivo.trim()} onClick={() => remarcar.mutate()}>
              Confirmar remarcação
            </Botao>
          </>
        )}
      <Botao onClick={aoSair}>Voltar</Botao>
    </div>
  );
}
