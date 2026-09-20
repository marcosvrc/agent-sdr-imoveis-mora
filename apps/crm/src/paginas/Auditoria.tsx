import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { CabecalhoPagina, Card, Carregando, Erro, Etiqueta, Vazio, cx, entradaCls } from "../componentes/ui";
import { api } from "../lib/api";
import { dataHora, relativo } from "../lib/formato";

/** Auditoria — só administrador.
 *
 *  Somente append: nada nesta tela edita ou apaga um evento. Auditoria que se corrige depois não
 *  responde "quem mudou isto", que é a única pergunta que ela existe para responder.
 */
export function Auditoria() {
  const [entidade, setEntidade] = useState("");
  const filtros = { entity_type: entidade || undefined, limit: "100" };
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["auditoria", filtros], queryFn: () => api.auditoria(filtros),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <CabecalhoPagina titulo="Auditoria" descricao="Quem fez o quê, quando, e o que mudou." />
        <label className="text-sm">
          <span className="sr-only">Filtrar por entidade</span>
          <select className={cx(entradaCls, "w-auto")} value={entidade} onChange={(e) => setEntidade(e.target.value)}>
            <option value="">Todas as entidades</option>
            <option value="lead">Clientes</option>
            <option value="opportunity">Oportunidades</option>
            <option value="visit">Visitas</option>
            <option value="handoff">Encaminhamentos</option>
            <option value="task">Tarefas</option>
            <option value="property">Imóveis</option>
          </select>
        </label>
      </div>

      {isLoading ? <Carregando linhas={8} />
        : error ? <Erro erro={error} aoTentar={() => refetch()} />
        : data!.items.length === 0 ? <Vazio titulo="Nenhum evento" />
        : (
          <Card semPadding>
            <ul className="divide-y divide-line">
              {data!.items.map((e) => (
                <li key={e.id} className="px-4 py-2.5 text-sm">
                  <div className="flex flex-wrap items-center gap-2">
                    <Etiqueta tom={e.actor_type === "service" ? "info" : "neutro"}>
                      {e.actor_type === "service" ? "agente" : e.actor_type === "user" ? "pessoa" : "sistema"}
                    </Etiqueta>
                    <span className="text-inkSoft">{e.actor_name ?? "—"}</span>
                    <code className="rounded bg-surface2 px-1.5 py-0.5 font-mono text-[11px] text-inkSoft">{e.action}</code>
                    <span className="text-[11px] text-inkFaint">{e.entity_type}</span>
                    <span className="ml-auto text-[11px] text-inkFaint" title={dataHora(e.occurred_at)}>
                      {relativo(e.occurred_at)}
                    </span>
                  </div>
                  {Object.keys(e.changes_json ?? {}).length > 0 && (
                    <pre className="mt-1 overflow-x-auto rounded bg-surface2 p-2 text-[11px] text-inkMuted">
                      {JSON.stringify(e.changes_json, null, 1)}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          </Card>
        )}
    </div>
  );
}
