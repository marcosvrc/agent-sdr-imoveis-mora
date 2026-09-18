import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Card, Carregando, Erro, Etiqueta, Vazio, cx, entradaCls } from "../componentes/ui";
import { api } from "../lib/api";
import { POLITICA_CONTATO, relativo } from "../lib/formato";

/** Lista de clientes.
 *
 *  A busca por nome é separada dos filtros por identificador de propósito: nome PROCURA, e-mail e
 *  telefone IDENTIFICAM. Misturar os dois numa caixa só levaria alguém a concluir que "João Silva"
 *  é uma pessoa — e há mais de um em qualquer base real.
 */
export function Clientes() {
  const [nome, setNome] = useState("");
  const [identificador, setIdentificador] = useState("");
  const [arquivados, setArquivados] = useState(false);

  const filtros = {
    name: nome.trim() || undefined,
    email: identificador.includes("@") ? identificador.trim() : undefined,
    phone: identificador && !identificador.includes("@") ? identificador.trim() : undefined,
    include_archived: arquivados ? "true" : undefined,
    limit: "50",
  };
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["leads", filtros], queryFn: () => api.leads(filtros),
  });

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-ink">Clientes</h1>

      <Card titulo="Filtros">
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm">
            <span className="mb-1 block font-medium text-inkSoft">Procurar por nome</span>
            <input className={entradaCls} value={nome} onChange={(e) => setNome(e.target.value)}
                   placeholder="parte do nome" />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-inkSoft">E-mail ou telefone</span>
            <input className={entradaCls} value={identificador} onChange={(e) => setIdentificador(e.target.value)}
                   placeholder="correspondência exata" />
          </label>
          <label className="flex items-end gap-2 text-sm">
            <input type="checkbox" checked={arquivados} onChange={(e) => setArquivados(e.target.checked)}
                   className="mb-2 h-4 w-4 rounded border-line" />
            <span className="mb-1.5 text-inkSoft">Mostrar arquivados</span>
          </label>
        </div>
      </Card>

      {isLoading ? <Carregando linhas={6} />
        : error ? <Erro erro={error} aoTentar={() => refetch()} />
        : data!.items.length === 0 ? (
          <Vazio titulo="Nenhum cliente encontrado"
                 descricao="Ajuste os filtros. Clientes arquivados ficam fora da lista por padrão e continuam acessíveis pelo link direto." />
        ) : (
          <Card semPadding>
            <ul className="divide-y divide-line">
              {data!.items.map((l) => (
                <li key={l.id}>
                  <Link to={`/clientes/${l.id}`}
                        className={cx("flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-sm hover:bg-surface2")}>
                    <span className="font-medium text-ink">{l.name}</span>
                    {l.archived_at && <Etiqueta>arquivado</Etiqueta>}
                    {l.contact_policy !== "unknown" && (
                      <Etiqueta tom={POLITICA_CONTATO[l.contact_policy].tom}>
                        {POLITICA_CONTATO[l.contact_policy].r}
                      </Etiqueta>
                    )}
                    <span className="text-inkMuted">{l.email ?? l.phone_e164 ?? l.external_contact_id}</span>
                    <span className="ml-auto text-[11px] text-inkFaint">
                      {l.source} · criado {relativo(l.created_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        )}
    </div>
  );
}
