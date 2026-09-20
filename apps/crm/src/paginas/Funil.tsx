import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Botao, CabecalhoPagina, Card, Carregando, Erro, Etiqueta, cx, entradaCls, foco } from "../componentes/ui";
import { ErroApi, api, type Oportunidade } from "../lib/api";
import { ATENDIMENTO, ESTAGIOS, NOME_ESTAGIO, PROPOSITO } from "../lib/formato";

/** Busca TODAS as oportunidades, seguindo o cursor.
 *
 *  Uma página só (o máximo da API é 100) fazia o quadro mostrar 100 de 120 e contradizer as
 *  contagens da Visão geral na tela anterior — um funil que mente por omissão é pior que um funil
 *  que avisa estar truncado. O teto de 20 páginas existe para o quadro não virar um carregamento
 *  infinito no dia em que a base crescer; quando ele é atingido, a tela diz.
 */
const PAGINAS_MAX = 20;

async function todasAsOportunidades() {
  const itens: Oportunidade[] = [];
  let cursor: string | undefined;
  for (let i = 0; i < PAGINAS_MAX; i++) {
    const p = await api.oportunidades({ limit: "100", cursor });
    itens.push(...p.items);
    if (!p.next_cursor) return { itens, truncado: false };
    cursor = p.next_cursor;
  }
  return { itens, truncado: true };
}

/** Quadro do funil.
 *
 *  A mudança de estágio é por MENU, não por arrastar. Arrastar é bonito e é a pior forma de mover
 *  algo que precisa de motivo, de confirmação e de leitor de tela: a especificação pede "menu
 *  acessível ou arraste", e entre os dois o menu é o que funciona para todo mundo.
 *
 *  Quando o servidor recusa, a coluna volta ao que era e o erro aparece com o motivo. Nada de
 *  otimismo aqui — o painel não pode mostrar "negociação" e o banco dizer outra coisa.
 */
export function Funil() {
  const qc = useQueryClient();
  const [falha, setFalha] = useState<unknown>(null);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["oportunidades"], queryFn: todasAsOportunidades,
  });

  const mover = useMutation({
    mutationFn: ({ op, destino, motivo }: { op: Oportunidade; destino: string; motivo: string | null }) =>
      api.mover(op.id, destino, motivo, op.version),
    onSuccess: () => { setFalha(null); qc.invalidateQueries({ queryKey: ["oportunidades"] }); },
    onError: (e) => setFalha(e),
  });

  if (isLoading) return <Carregando linhas={5} />;
  if (error) return <Erro erro={error} aoTentar={() => refetch()} />;

  const porEstagio = Object.fromEntries(
    ESTAGIOS.map((e) => [e.k, data!.itens.filter((o) => o.stage === e.k)]),
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-2">
        <CabecalhoPagina titulo="Funil" descricao="Arraste ou use os botões para mover a oportunidade de estágio." />
        <span className="text-xs text-inkFaint">{data!.itens.length} oportunidades</span>
      </div>
      {data!.truncado && (
        <p className="rounded-lg border border-line bg-alertaSoft px-3 py-2 text-xs text-alerta">
          Mostrando as {data!.itens.length} mais recentes — há mais no banco do que cabe neste quadro.
        </p>
      )}
      {falha ? <Erro erro={falha} /> : null}
      {falha instanceof ErroApi && falha.code === "VERSION_CONFLICT" && (
        <p className="text-xs text-inkMuted">
          Alguém alterou esta oportunidade enquanto a tela estava aberta. Recarregue para ver o
          estado atual antes de mover de novo.
        </p>
      )}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {ESTAGIOS.map((e) => (
          <Card key={e.k} titulo={
            <span className="flex items-center gap-2">
              {e.r}
              <span className="rounded bg-surface2 px-1.5 text-[11px] tabular-nums text-inkMuted">
                {porEstagio[e.k].length}
              </span>
            </span>
          } semPadding>
            <p className="px-4 pt-2 text-[11px] text-inkFaint">{e.ajuda}</p>
            <ul className="max-h-[420px] space-y-2 overflow-y-auto p-3">
              {porEstagio[e.k].length === 0 && (
                <li className="px-1 py-2 text-xs text-inkFaint">Vazio.</li>
              )}
              {porEstagio[e.k].map((op) => (
                <Ficha key={op.id} op={op} ocupado={mover.isPending}
                       aoMover={(destino, motivo) => mover.mutate({ op, destino, motivo })} />
              ))}
            </ul>
          </Card>
        ))}
      </div>
    </div>
  );
}

function Ficha({ op, aoMover, ocupado }: {
  op: Oportunidade; aoMover: (destino: string, motivo: string | null) => void; ocupado: boolean;
}) {
  const [destino, setDestino] = useState("");
  const [motivo, setMotivo] = useState("");
  const humano = op.atendimento !== "agent";
  // Perder e reabrir exigem motivo — a API recusa sem ele, e pedir aqui evita um erro que a
  // pessoa só descobriria depois de clicar.
  const pedeMotivo = destino === "lost" || (destino === "in_service" && ["won", "lost"].includes(op.stage));

  return (
    <li className="rounded-lg border border-line bg-surface p-2.5">
      <div className="flex items-start justify-between gap-2">
        <Link to={`/oportunidades/${op.id}`}
              className={cx("text-sm font-medium text-ink hover:text-acento hover:underline", foco)}>
          {PROPOSITO[op.purpose]}
        </Link>
        {humano && <Etiqueta tom={ATENDIMENTO[op.atendimento].tom}>{ATENDIMENTO[op.atendimento].r}</Etiqueta>}
      </div>
      <Link to={`/clientes/${op.lead_id}`} className="mt-0.5 block truncate text-[11px] text-inkMuted hover:underline">
        {op.lead_name ?? `cliente ${op.lead_id.slice(0, 8)}`}
      </Link>
      {op.lost_reason && <p className="mt-1 text-[11px] text-inkFaint">Motivo: {op.lost_reason}</p>}

      <div className="mt-2 space-y-1.5">
        <label className="sr-only" htmlFor={`mover-${op.id}`}>
          Mover a oportunidade de {PROPOSITO[op.purpose]} do estágio {NOME_ESTAGIO[op.stage]}
        </label>
        <select id={`mover-${op.id}`} className={cx(entradaCls, "text-xs")} value={destino}
                onChange={(e) => setDestino(e.target.value)}>
          <option value="">Mover para…</option>
          {ESTAGIOS.filter((x) => x.k !== op.stage).map((x) => (
            <option key={x.k} value={x.k}>{x.r}</option>
          ))}
        </select>
        {pedeMotivo && (
          <input className={cx(entradaCls, "text-xs")} placeholder="Motivo (obrigatório)"
                 aria-label="Motivo" value={motivo} onChange={(e) => setMotivo(e.target.value)} />
        )}
        {destino && (
          <Botao className="w-full justify-center text-xs" ocupado={ocupado}
                 disabled={pedeMotivo && !motivo.trim()}
                 onClick={() => aoMover(destino, motivo.trim() || null)}>
            Confirmar
          </Botao>
        )}
      </div>
    </li>
  );
}
