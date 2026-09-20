import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AvisoOrdemParcial, Botao, CabecalhoPagina, Card, Carregando, ColunaOrdenavel, Erro, Etiqueta,
         Paginacao, Vazio, cx, entradaCls, foco, usePaginaCursor } from "../componentes/ui";
import { Ic } from "../componentes/Icones";
import { api } from "../lib/api";
import { ordenar, useAtraso, useFiltrosNaUrl, type Ordem } from "../lib/filtros";
import { POLITICA_CONTATO, dataHora, relativo } from "../lib/formato";

const POR_PAGINA = "25";
type Campo = "name" | "source" | "created_at";

/** Lista de clientes.
 *
 *  A busca por nome é separada dos filtros por identificador de propósito: nome PROCURA, e-mail e
 *  telefone IDENTIFICAM. Misturar os dois numa caixa só levaria alguém a concluir que "João Silva"
 *  é uma pessoa — e há mais de um em qualquer base real.
 */
export function Clientes() {
  const { valores, definir, limpar, algumFiltro } = useFiltrosNaUrl({ nome: "", id: "", arquivados: "" });
  // O campo responde na hora; a consulta espera a digitação parar. Ligar a consulta direto no
  // valor da URL faria a lista recarregar a cada tecla.
  const [nome, setNome] = useState(valores.nome);
  const nomeAtrasado = useAtraso(nome);
  const [ordem, setOrdem] = useState<Ordem<Campo> | null>(null);
  const pag = usePaginaCursor();

  useEffect(() => { definir({ nome: nomeAtrasado }); }, [nomeAtrasado]);   // eslint-disable-line react-hooks/exhaustive-deps
  // O caminho de volta: o botão voltar do navegador muda a URL, e quem mora só no estado do React
  // não fica sabendo. Sem isto, voltar limpava o endereço e deixava o texto no campo — a tela
  // mostrando um filtro que a URL diz que não existe mais.
  useEffect(() => { if (valores.nome !== nomeAtrasado) setNome(valores.nome); }, [valores.nome]);   // eslint-disable-line react-hooks/exhaustive-deps
  // Mexeu no filtro, volta para a primeira página: manter o cursor mostraria a segunda página de
  // uma busca que não existe mais.
  useEffect(() => { pag.reiniciar(); }, [nomeAtrasado, valores.id, valores.arquivados]);   // eslint-disable-line react-hooks/exhaustive-deps

  const filtros = {
    name: nomeAtrasado.trim() || undefined,
    email: valores.id.includes("@") ? valores.id.trim() : undefined,
    phone: valores.id && !valores.id.includes("@") ? valores.id.trim() : undefined,
    include_archived: valores.arquivados === "1" ? "true" : undefined,
    limit: POR_PAGINA,
    cursor: pag.cursor,
  };
  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["leads", filtros], queryFn: () => api.leads(filtros),
  });

  // Três estados no mesmo cabeçalho: crescente → decrescente → sem ordenação. O terceiro existe
  // para dar como voltar à ordem que o servidor entregou, que é a única completa.
  const alternar = (campo: Campo) =>
    setOrdem((o) => (o?.campo === campo ? (o.desc ? null : { campo, desc: true }) : { campo, desc: false }));

  const itens = ordenar(data?.items ?? [], ordem, (l, c) =>
    c === "name" ? l.name : c === "source" ? l.source : l.created_at);

  return (
    <div>
      <CabecalhoPagina titulo="Clientes"
        descricao="Nome procura; e-mail e telefone identificam. Arquivados ficam fora por padrão."
        acoes={algumFiltro && <Botao onClick={() => { limpar(); setNome(""); }}><Ic.limpar size={14} /> Limpar filtros</Botao>} />

      <Card titulo="Filtros" acoes={isFetching ? <span className="text-[11px] text-inkFaint">buscando…</span> : undefined}>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm">
            <span className="mb-1 block font-medium text-inkSoft">Procurar por nome</span>
            <span className="relative block">
              <Ic.procurar size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-inkFaint" />
              <input className={cx(entradaCls, "pl-8")} value={nome} onChange={(e) => setNome(e.target.value)}
                     placeholder="parte do nome" type="search" />
            </span>
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-inkSoft">E-mail ou telefone</span>
            <input className={entradaCls} value={valores.id} onChange={(e) => definir({ id: e.target.value })}
                   placeholder="correspondência exata" />
          </label>
          <label className="flex items-end gap-2 pb-1.5 text-sm">
            <input type="checkbox" checked={valores.arquivados === "1"}
                   onChange={(e) => definir({ arquivados: e.target.checked ? "1" : "" })}
                   className={cx("h-4 w-4 rounded border-lineForte accent-[var(--acento)]", foco)} />
            <span className="text-inkSoft">Mostrar arquivados</span>
          </label>
        </div>
      </Card>

      <div className="mt-4">
        {isLoading ? <Carregando linhas={6} />
          : error ? <Erro erro={error} aoTentar={() => refetch()} />
          : itens.length === 0 ? (
            <Vazio titulo="Nenhum cliente encontrado"
                   descricao="Ajuste os filtros. Clientes arquivados ficam fora da lista por padrão e continuam acessíveis pelo link direto." />
          ) : (
            <Card semPadding>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="border-b border-line bg-surface2">
                    <tr>
                      <ColunaOrdenavel campo="name" atual={ordem} aoOrdenar={alternar}>Nome</ColunaOrdenavel>
                      <th scope="col" className="px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wide text-inkMuted">Contato</th>
                      <ColunaOrdenavel campo="source" atual={ordem} aoOrdenar={alternar}>Origem</ColunaOrdenavel>
                      <ColunaOrdenavel campo="created_at" atual={ordem} aoOrdenar={alternar} alinhar="direita">Criado</ColunaOrdenavel>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {itens.map((l) => (
                      <tr key={l.id} className="hover:bg-surface2">
                        <td className="px-3 py-2">
                          {/* O link é só no nome, e não na linha inteira: linha clicável impede
                              copiar o telefone sem navegar sem querer, e não aparece na navegação
                              por tabulação como um destino com nome. */}
                          <Link to={`/clientes/${l.id}`} className={cx("rounded font-medium text-ink hover:text-acento hover:underline", foco)}>
                            {l.name}
                          </Link>
                          <span className="ml-2 inline-flex gap-1 align-middle">
                            {l.archived_at && <Etiqueta>arquivado</Etiqueta>}
                            {l.contact_policy !== "unknown" && (
                              <Etiqueta tom={POLITICA_CONTATO[l.contact_policy].tom}>
                                {POLITICA_CONTATO[l.contact_policy].r}
                              </Etiqueta>
                            )}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-inkMuted">{l.email ?? l.phone_e164 ?? l.external_contact_id}</td>
                        <td className="px-3 py-2 text-inkMuted">{l.source}</td>
                        <td className="px-3 py-2 text-right text-inkFaint" title={dataHora(l.created_at)}>
                          {relativo(l.created_at)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <AvisoOrdemParcial mostrar={!!ordem && !!data!.next_cursor} />
              <Paginacao rotulo="clientes" mostrando={itens.length} pagina={pag.pagina} primeira={pag.primeira}
                         temProxima={!!data!.next_cursor} aoVoltar={pag.voltar}
                         aoAvancar={() => data!.next_cursor && pag.avancar(data!.next_cursor)} />
            </Card>
          )}
      </div>
    </div>
  );
}
