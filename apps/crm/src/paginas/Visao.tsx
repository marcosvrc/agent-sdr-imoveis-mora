import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Card, Carregando, Erro, Etiqueta } from "../componentes/ui";
import { api } from "../lib/api";
import { ESTAGIOS, dataHora, relativo } from "../lib/formato";

/** Visão geral: o que exige ação hoje, e o funil inteiro.
 *
 *  A ordem dos blocos é a ordem da urgência, não a da beleza: encaminhamento pendente e tarefa
 *  vencida vêm primeiro porque são pessoas esperando. O funil vem depois porque é diagnóstico,
 *  não fila.
 */
export function Visao() {
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["painel"], queryFn: api.painel });

  if (isLoading) return <Carregando linhas={4} />;
  if (error) return <Erro erro={error} aoTentar={() => refetch()} />;
  const p = data!.data;

  const total = Object.values(p.por_estagio).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-semibold text-ink">Visão geral</h1>
        {/* Carimbo de hora: um painel sem ele é a forma mais fácil de alguém decidir com dado de ontem. */}
        <p className="text-xs text-inkFaint">Atualizado {relativo(p.generated_at)} · {dataHora(p.generated_at)}</p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Numero rotulo="Esperando um corretor" valor={p.handoffs_pendentes} para="/encaminhamentos"
                tom={p.handoffs_pendentes > 0 ? "alerta" : "neutro"} nota="encaminhamentos pendentes" />
        <Numero rotulo="Tarefas vencidas" valor={p.tarefas_vencidas}
                tom={p.tarefas_vencidas > 0 ? "ruim" : "neutro"} nota="prazo já passou" />
        <Numero rotulo="Visitas a confirmar" valor={p.visitas_solicitadas} para="/visitas"
                tom={p.visitas_solicitadas > 0 ? "alerta" : "neutro"} nota="solicitadas pelo agente" />
        <Numero rotulo="Visitas futuras" valor={p.visitas_futuras} para="/visitas" nota="já confirmadas" />
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-[2fr_1fr]">
        <Card titulo="Funil" acoes={<Link to="/funil" className="text-xs text-acento hover:underline">abrir o quadro</Link>}>
          {total === 0 ? (
            <p className="text-sm text-inkMuted">Nenhuma oportunidade ainda.</p>
          ) : (
            <ul className="space-y-2">
              {ESTAGIOS.map((e) => {
                const n = p.por_estagio[e.k] ?? 0;
                return (
                  <li key={e.k} className="flex items-center gap-3">
                    <span className="w-32 shrink-0 text-sm text-inkSoft" title={e.ajuda}>{e.r}</span>
                    <div className="h-2.5 min-w-0 flex-1 overflow-hidden rounded-full bg-surface2">
                      <div className="h-full rounded-full bg-acento"
                           style={{ width: `${total ? (n / total) * 100 : 0}%` }} />
                    </div>
                    <span className="w-10 shrink-0 text-right text-sm tabular-nums text-ink">{n}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        <Card titulo="Base">
          <dl className="space-y-3 text-sm">
            <Linha rotulo="Clientes ativos" valor={p.leads_ativos} />
            <Linha rotulo="Oportunidades" valor={total} />
            <Linha rotulo="Imóveis disponíveis" valor={p.imoveis_disponiveis} />
          </dl>
        </Card>
      </div>
    </div>
  );
}

function Numero({ rotulo, valor, nota, tom = "neutro", para }: {
  rotulo: string; valor: number; nota?: string; tom?: "neutro" | "alerta" | "ruim"; para?: string;
}) {
  const corpo = (
    <div className="h-full rounded-xl border border-line bg-surface p-3 shadow-card">
      <p className="text-[11px] uppercase tracking-wide text-inkMuted">{rotulo}</p>
      <p className="mt-0.5 text-2xl font-semibold tabular-nums text-ink">{valor}</p>
      <div className="mt-1 flex items-center gap-1.5">
        {nota && <span className="text-[11px] text-inkFaint">{nota}</span>}
        {tom !== "neutro" && valor > 0 && <Etiqueta tom={tom}>ação</Etiqueta>}
      </div>
    </div>
  );
  return para ? <Link to={para} className="block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--anel-foco)]">{corpo}</Link> : corpo;
}

function Linha({ rotulo, valor }: { rotulo: string; valor: number }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-inkMuted">{rotulo}</dt>
      <dd className="font-medium tabular-nums text-ink">{valor}</dd>
    </div>
  );
}
