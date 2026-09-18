import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Botao, Card, Carregando, Erro, Etiqueta, Vazio, cx, entradaCls } from "../componentes/ui";
import { api, type Handoff } from "../lib/api";
import { NOME_ESTAGIO, relativo } from "../lib/formato";

/** Fila de encaminhamentos.
 *
 *  Resolver exige dizer explicitamente para quem volta o atendimento — agente ou pessoa. A API
 *  recusa sem essa escolha, e com razão: devolver ao agente por omissão faria a Mora voltar a
 *  escrever para um cliente no meio de uma negociação conduzida por gente.
 */
export function Encaminhamentos() {
  const qc = useQueryClient();
  const [filtro, setFiltro] = useState("pending");
  const [falha, setFalha] = useState<unknown>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["handoffs", filtro], queryFn: () => api.handoffs(filtro),
  });

  const mover = useMutation({
    mutationFn: ({ h, corpo }: { h: Handoff; corpo: Record<string, unknown> }) =>
      api.moverHandoff(h.id, corpo, h.version),
    onSuccess: () => {
      setFalha(null);
      qc.invalidateQueries({ queryKey: ["handoffs"] });
      qc.invalidateQueries({ queryKey: ["painel"] });
    },
    onError: (e) => setFalha(e),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold text-ink">Encaminhamentos</h1>
        <label className="text-sm">
          <span className="sr-only">Filtrar por situação</span>
          <select className={cx(entradaCls, "w-auto")} value={filtro} onChange={(e) => setFiltro(e.target.value)}>
            <option value="pending">Na fila</option>
            <option value="accepted">Assumidos</option>
            <option value="resolved">Resolvidos</option>
          </select>
        </label>
      </div>

      {falha ? <Erro erro={falha} /> : null}

      {isLoading ? <Carregando linhas={4} />
        : error ? <Erro erro={error} aoTentar={() => refetch()} />
        : data!.items.length === 0 ? (
          <Vazio titulo="Ninguém esperando"
                 descricao="A Mora encaminha quando o cliente pede uma pessoa ou quando a conversa sai do que ela resolve." />
        ) : (
          <ul className="grid gap-3 lg:grid-cols-2">
            {data!.items.map((h) => (
              <li key={h.id}>
                <Ficha h={h} ocupado={mover.isPending} aoMover={(corpo) => mover.mutate({ h, corpo })} />
              </li>
            ))}
          </ul>
        )}
    </div>
  );
}

function Ficha({ h, aoMover, ocupado }: {
  h: Handoff; aoMover: (corpo: Record<string, unknown>) => void; ocupado: boolean;
}) {
  const [resolvendo, setResolvendo] = useState(false);

  return (
    <Card titulo={
      <span className="flex flex-wrap items-center gap-2">
        {h.lead_name ?? "Cliente"}
        {h.stage && <Etiqueta>{NOME_ESTAGIO[h.stage]}</Etiqueta>}
        <Etiqueta tom={h.status === "pending" ? "alerta" : h.status === "accepted" ? "info" : "neutro"}>
          {h.status === "pending" ? "na fila" : h.status === "accepted" ? "com você" : "resolvido"}
        </Etiqueta>
      </span>
    }>
      <p className="text-xs text-inkMuted">Motivo: {h.reason}</p>
      {/* O resumo é o que economiza a releitura da conversa inteira — por isso ele fica inteiro. */}
      <p className="mt-2 whitespace-pre-wrap text-sm text-inkSoft">{h.summary}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {h.lead_id && (
          <Link to={`/clientes/${h.lead_id}`} className="text-xs text-acento hover:underline">ver o cliente</Link>
        )}
        <Link to={`/oportunidades/${h.opportunity_id}`} className="text-xs text-acento hover:underline">
          ver a oportunidade
        </Link>
        <span className="ml-auto text-[11px] text-inkFaint">{relativo((h as { created_at?: string }).created_at)}</span>
      </div>

      {h.status === "pending" && (
        <Botao className="mt-3" variante="primario" ocupado={ocupado}
               onClick={() => aoMover({ target_status: "accepted" })}>
          Assumir
        </Botao>
      )}

      {h.status === "accepted" && (
        resolvendo ? (
          <div className="mt-3 space-y-2 rounded-lg border border-line p-3">
            <p className="text-xs text-inkSoft">
              Ao resolver, diga quem continua o atendimento. Não há padrão: devolver ao agente por
              omissão o faria escrever de novo sem ninguém ter pedido.
            </p>
            <div className="flex flex-wrap gap-2">
              <Botao ocupado={ocupado}
                     onClick={() => aoMover({ target_status: "resolved", return_to: "agent" })}>
                Devolver para a Mora
              </Botao>
              <Botao variante="primario" ocupado={ocupado}
                     onClick={() => aoMover({ target_status: "resolved", return_to: "human" })}>
                Continuo eu
              </Botao>
              <Botao onClick={() => setResolvendo(false)}>Voltar</Botao>
            </div>
          </div>
        ) : (
          <Botao className="mt-3" ocupado={ocupado} onClick={() => setResolvendo(true)}>Resolver</Botao>
        )
      )}
    </Card>
  );
}
