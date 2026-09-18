import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { Card, Carregando, Erro, Etiqueta, Vazio } from "../componentes/ui";
import { api } from "../lib/api";
import { ATENDIMENTO, NOME_ESTAGIO, PROPOSITO, STATUS_VISITA, brl, dataHora } from "../lib/formato";

/** Ficha da oportunidade: preferências, imóveis, visitas, tarefas e quem está conduzindo.
 *
 *  O bloco de atendimento fica no topo e destacado de propósito. Saber se quem está falando com o
 *  cliente é a Mora ou um corretor muda tudo que vem depois — e é a informação que alguém procura
 *  antes de pegar o telefone.
 */
export function OportunidadeDetalhe() {
  const { id = "" } = useParams();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["oportunidade", id], queryFn: () => api.oportunidade(id),
  });

  if (isLoading) return <Carregando linhas={5} />;
  if (error) return <Erro erro={error} aoTentar={() => refetch()} />;
  const o = data!.data;
  const p = o.preferences;
  const porMes = p?.budget_basis === "monthly_total";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold text-ink">{PROPOSITO[o.purpose]}</h1>
        <Etiqueta>{NOME_ESTAGIO[o.stage]}</Etiqueta>
        <Etiqueta tom={ATENDIMENTO[o.atendimento].tom}>{ATENDIMENTO[o.atendimento].r}</Etiqueta>
        <Link to={`/clientes/${o.lead_id}`} className="text-sm text-acento hover:underline">ver o cliente</Link>
      </div>

      {o.atendimento !== "agent" && (
        <div className="rounded-lg border border-info/30 bg-infoSoft px-4 py-2 text-sm text-info">
          {o.atendimento === "human_pending"
            ? "Encaminhado: a Mora parou de movimentar esta oportunidade e está só registrando o que o cliente escreve."
            : "Um corretor assumiu. A Mora continua ouvindo, mas não age até alguém devolver o atendimento."}
        </div>
      )}
      {o.lost_reason && (
        <div className="rounded-lg border border-line bg-surface2 px-4 py-2 text-sm text-inkSoft">
          Perdida — motivo: {o.lost_reason}
        </div>
      )}

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <Card titulo="O que o cliente procura">
          {!p || (!p.city && !p.budget_max_cents) ? (
            <Vazio titulo="Preferências ainda incompletas"
                   descricao="A qualificação exige cidade, finalidade e teto de orçamento. Enquanto faltar, a oportunidade não avança." />
          ) : (
            <dl className="space-y-2 text-sm">
              <Linha rotulo="Cidade" valor={p.city ?? "—"} />
              <Linha rotulo="Bairros" valor={p.neighborhoods.join(", ") || "—"} />
              <Linha rotulo="Tipos" valor={p.property_types.join(", ") || "—"} />
              <Linha rotulo={porMes ? "Orçamento (custo mensal)" : "Orçamento"}
                     valor={`${p.budget_min_cents ? brl(p.budget_min_cents) + " a " : "até "}${brl(p.budget_max_cents)}`} />
              <Linha rotulo="Quartos (mínimo)" valor={p.bedrooms_min?.toString() ?? "—"} />
              <Linha rotulo="Vagas (mínimo)" valor={p.parking_min?.toString() ?? "—"} />
              {p.requirements.length > 0 && <Linha rotulo="Exigências" valor={p.requirements.join(" · ")} />}
            </dl>
          )}
        </Card>

        <Card titulo="Imóveis apresentados">
          {o.interests.length === 0 ? <Vazio titulo="Nenhum imóvel associado ainda" /> : (
            <ul className="space-y-2 text-sm">
              {o.interests.map((i) => (
                <li key={i.property_id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line px-3 py-2">
                  <span className="font-medium text-ink">{i.title}</span>
                  <span className="text-[11px] text-inkFaint">{i.code}</span>
                  <Etiqueta tom={i.status === "interested" ? "bom" : i.status === "rejected" ? "ruim" : "neutro"}>
                    {{ presented: "apresentado", interested: "interessou", rejected: "descartado" }[i.status] ?? i.status}
                  </Etiqueta>
                  {i.notes && <span className="w-full text-[11px] text-inkMuted">{i.notes}</span>}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card titulo="Visitas">
          {o.visits.length === 0 ? <Vazio titulo="Nenhuma visita" /> : (
            <ul className="space-y-1.5 text-sm">
              {o.visits.map((v) => (
                <li key={v.id} className="flex items-center gap-2">
                  <span className="tabular-nums text-inkSoft">{dataHora(v.starts_at)}</span>
                  <Etiqueta tom={STATUS_VISITA[v.status].tom}>{STATUS_VISITA[v.status].r}</Etiqueta>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-[11px] text-inkFaint">
            Confirmar, concluir e marcar falta são ações de uma pessoa — na tela de Visitas.
          </p>
        </Card>

        <Card titulo="Tarefas">
          {o.tasks.length === 0 ? <Vazio titulo="Nenhuma tarefa" /> : (
            <ul className="space-y-1.5 text-sm">
              {o.tasks.map((t) => (
                <li key={t.id} className="flex flex-wrap items-center gap-2">
                  <span className={t.status === "done" ? "text-inkFaint line-through" : "text-inkSoft"}>{t.title}</span>
                  <Etiqueta tom={t.kind === "follow_up" ? "info" : "neutro"}>
                    {t.kind === "follow_up" ? "contato" : "interno"}
                  </Etiqueta>
                  {t.due_at && <span className="ml-auto text-[11px] text-inkFaint">{dataHora(t.due_at)}</span>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

function Linha({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-inkMuted">{rotulo}</dt>
      <dd className="text-right text-ink">{valor}</dd>
    </div>
  );
}
