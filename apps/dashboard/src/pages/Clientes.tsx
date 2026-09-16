// Clientes: a PESSOA por trás das oportunidades. Serve para o corretor ver com quem já falamos antes de ligar.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { dataHora, relativo, INTENCAO } from "../lib/format";
import { Avatar, Badge, Card, Drawer, EmptyState, Estagio, Input, PageHeader, Paginacao, Skeleton, StatTile, Table, Temperatura, usePaginacao } from "../components/ui";
import { Ic } from "../components/Icons";

export function Clientes() {
  const [busca, setBusca] = useState("");
  const [aberto, setAberto] = useState<string | null>(null);
  const { data, isLoading } = useQuery({ queryKey: ["clientes", busca], queryFn: () => api.clientes(busca) });
  const linhas = data ?? [];
  const pg = usePaginacao(linhas, 10, "clientes");
  const comRecorrencia = linhas.filter((c) => c.oportunidades > 1).length;

  return (
    <div className="space-y-4">
      <PageHeader titulo="Clientes" descricao="Uma pessoa por telefone ou e-mail — com todas as oportunidades que ela já abriu, em qualquer canal" />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <StatTile label="Clientes identificados" valor={String(linhas.length)} icone="leads" destaque
          ajuda={<>Pessoas que informaram telefone ou e-mail em algum momento — é o que permite reconhecê-las numa próxima conversa. Quem falou com a Mora e saiu sem deixar contato não aparece aqui, mas continua na lista de leads.</>} />
        <StatTile label="Com mais de uma oportunidade" valor={String(comRecorrencia)} icone="refresh"
          ajuda={<>Clientes que voltaram: compraram e agora querem alugar, ou procuraram de novo depois de um tempo. São os de maior valor para o corretor, porque já conhecem a casa.</>} />
        <StatTile label="Oportunidades abertas" valor={String(linhas.reduce((s, c) => s + c.abertas, 0))} icone="bolt"
          ajuda={<>Negociações em andamento entre estes clientes. Uma pessoa pode ter mais de uma aberta ao mesmo tempo — por exemplo, procurando para morar e para investir.</>} />
      </div>

      <Card semPadding>
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
          <div className="relative"><Ic.search size={15} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint" />
            <Input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Nome, telefone ou e-mail" className="w-72 pl-8" /></div>
          <span className="ml-auto text-xs text-ink-muted">{linhas.length} cliente{linhas.length === 1 ? "" : "s"}</span>
        </div>

        {isLoading ? <div className="p-4"><Skeleton className="h-80" /></div>
          : linhas.length === 0 ? <div className="p-6"><EmptyState titulo="Nenhum cliente identificado ainda"
              descricao="Um lead vira cliente assim que informa telefone ou e-mail — é o que permite reconhecê-lo numa próxima conversa." icone="leads" /></div>
          : <>
            <Table colunas={["Cliente", { h: "Contato", cls: "w-56" }, { h: "Oportunidades", cls: "w-32 text-center" }, { h: "Última atividade", cls: "w-40" }, { h: "", cls: "w-12 text-center" }]}>
              {pg.fatia.map((c) => (
                <tr key={c.id} className="cursor-pointer border-t border-line hover:bg-surface-2" onClick={() => setAberto(c.id)}>
                  <td className="px-3 py-2">
                    <span className="inline-flex items-center gap-2"><Avatar nome={c.nome ?? c.id} tamanho={26} />
                      <span className="truncate text-sm">{c.nome ?? <span className="text-ink-muted">sem nome</span>}</span></span>
                  </td>
                  <td className="px-3 py-2 text-xs text-ink-muted">{[c.telefone, c.email].filter(Boolean).join(" · ") || "—"}</td>
                  <td className="px-3 py-2 text-center text-sm tabular-nums">
                    {c.oportunidades}{c.abertas > 0 && <Badge tom="good">{c.abertas} aberta{c.abertas === 1 ? "" : "s"}</Badge>}
                  </td>
                  <td className="px-3 py-2 text-xs text-ink-muted">{c.ultima_atividade ? `${relativo(c.ultima_atividade)} atrás` : "—"}</td>
                  <td className="px-3 py-2 text-center"><Ic.chevronRight size={15} className="text-ink-muted" /></td>
                </tr>
              ))}
            </Table>
            <Paginacao {...pg} />
          </>}
      </Card>

      <FichaCliente clienteId={aberto} onFechar={() => setAberto(null)} />
    </div>
  );
}

function FichaCliente({ clienteId, onFechar }: { clienteId: string | null; onFechar: () => void }) {
  const { data } = useQuery({ queryKey: ["cliente", clienteId], queryFn: () => api.cliente(clienteId!), enabled: !!clienteId });
  return (
    <Drawer aberto={!!clienteId} onFechar={onFechar} largura="max-w-2xl"
      titulo={<span className="inline-flex items-center gap-2"><Avatar nome={data?.cliente.nome ?? "?"} tamanho={28} />{data?.cliente.nome ?? "Cliente"}</span>}>
      {!data ? <Skeleton className="h-64" /> : (
        <div className="space-y-5">
          <dl className="grid grid-cols-[6rem_1fr] gap-x-3 gap-y-1.5 text-sm">
            <dt className="text-ink-muted">Telefone</dt><dd>{data.cliente.telefone ?? "—"}</dd>
            <dt className="text-ink-muted">E-mail</dt><dd className="break-words">{data.cliente.email ?? "—"}</dd>
            <dt className="text-ink-muted">Conhecemos</dt><dd>desde {dataHora(data.cliente.criado_em)}</dd>
            <dt className="text-ink-muted">Procurou</dt>
            <dd className="flex flex-wrap gap-1">{data.intencoes.map((i) => <Badge key={i} tom="info">{INTENCAO[i] ?? i}</Badge>)}</dd>
          </dl>

          <div>
            <div className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-muted">
              Oportunidades ({data.total_oportunidades})
            </div>
            <ol className="space-y-2">
              {data.oportunidades.map((o) => (
                <li key={o.id} className="rounded-lg border border-line p-3">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <Link to={`/leads/${o.id}`} className="font-medium text-brand-accent hover:underline">
                      {INTENCAO[o.cartao?.intencao ?? ""] ?? o.cartao?.intencao ?? "Indefinida"}
                    </Link>
                    <Estagio e={o.estagio} /><Temperatura t={o.temperatura} />
                    {o.encerrado_em && <Badge tom="neutro">encerrada</Badge>}
                    <span className="ml-auto text-xs text-ink-muted">{dataHora(o.criado_em)}</span>
                  </div>
                  <p className="mt-1 text-xs text-ink-muted">
                    {o.corretor_nome ? `${o.corretor_nome} · ` : ""}{o.mensagens} mensagem{o.mensagens === 1 ? "" : "s"}
                    {o.visitas > 0 && ` · ${o.visitas} visita${o.visitas === 1 ? "" : "s"}`}
                  </p>
                  {o.resumo && <p className="mt-1.5 line-clamp-3 text-xs text-ink">{o.resumo}</p>}
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
    </Drawer>
  );
}
