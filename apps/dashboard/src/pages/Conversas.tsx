import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { relativo, CANAL } from "../lib/format";
import { Transcricao } from "../components/Transcricao";
import { Card, PageHeader, Estagio, Temperatura, EmptyState, Avatar, Input, Skeleton, cx } from "../components/ui";
import { Ic } from "../components/Icons";
import { Link } from "react-router-dom";

/** Caixa de entrada: leads ordenados pela última mensagem, transcrição ao vivo à direita. */
export function Conversas() {
  const { data: leads, isLoading } = useQuery({ queryKey: ["leads", "todos"], queryFn: () => api.leads() });
  const [sel, setSel] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const lista = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return [...(leads ?? [])].filter((l) => l.ultima_mensagem_em && (!q || (l.nome ?? l.id).toLowerCase().includes(q))).sort((a, b) => (b.ultima_mensagem_em ?? "").localeCompare(a.ultima_mensagem_em ?? ""));
  }, [leads, busca]);
  const atual = sel ?? lista[0]?.id ?? null;
  const lead = lista.find((l) => l.id === atual);
  const { data: msgs } = useQuery({ queryKey: ["mensagens", atual], queryFn: () => api.mensagens(atual!), enabled: !!atual, refetchInterval: 5000 });

  return (
    <div>
      <PageHeader titulo="Conversas" descricao="Acompanhe em tempo real o que a Mora e os corretores estão dizendo aos leads" />
      <Card semPadding className="overflow-hidden">
        <div className="grid lg:h-[calc(100vh-11.5rem)] lg:grid-cols-[320px_1fr]">
          <aside className="flex min-h-0 flex-col border-b border-line lg:border-b-0 lg:border-r">
            <div className="relative p-3"><Ic.search size={15} className="pointer-events-none absolute left-5 top-5 text-ink-faint" /><Input className="pl-8" placeholder="Buscar conversa…" value={busca} onChange={(e) => setBusca(e.target.value)} /></div>
            <ul className="max-h-[50vh] min-h-0 flex-1 divide-y divide-line overflow-y-auto lg:max-h-none">
              {isLoading && Array.from({ length: 5 }).map((_, i) => <li key={i} className="p-3"><Skeleton className="h-10" /></li>)}
              {lista.map((l) => (
                <li key={l.id}><button onClick={() => setSel(l.id)} className={cx("flex w-full items-center gap-2.5 px-3 py-2.5 text-left hover:bg-surface-2", atual === l.id && "bg-info-soft")}>
                  <Avatar nome={l.nome ?? l.id} />
                  <span className="min-w-0 flex-1"><span className="flex items-center justify-between gap-2"><span className="truncate text-sm font-medium">{l.nome ?? l.id}</span><span className="shrink-0 text-[11px] text-ink-faint">{relativo(l.ultima_mensagem_em)}</span></span>
                    <span className="mt-0.5 flex items-center gap-1.5"><Estagio e={l.estagio} /><Temperatura t={l.temperatura} /><span className="text-[11px] text-ink-muted">{l.canais?.map((c) => CANAL[c.canal] ?? c.canal).join(", ")}</span></span></span>
                </button></li>))}
              {!isLoading && lista.length === 0 && <li><EmptyState icone="chat" titulo="Nenhuma conversa" descricao="Assim que um lead escrever no site ou no Telegram, ele aparece aqui." /></li>}
            </ul>
          </aside>
          <section className="flex min-h-0 min-w-0 flex-col">
            {lead ? (<>
              <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-3"><div className="flex items-center gap-2.5"><Avatar nome={lead.nome ?? lead.id} /><div><p className="text-sm font-medium">{lead.nome ?? lead.id}</p><p className="text-[11px] text-ink-muted">score {lead.score} · {lead.estagio === "handoff" ? "com corretor" : "com a Mora"}</p></div></div><Link to={`/leads/${lead.id}`} className="inline-flex items-center gap-1 text-xs font-medium text-brand-accent hover:underline">abrir lead <Ic.arrowRight size={12} /></Link></header>
              {/* No desktop a altura vem do grid (`h-full` dentro de um flex que pode encolher). No celular
                  não há grid de altura fixa: sem um teto, a transcrição cresce com as 40 mensagens, a página
                  inteira vira um rolo só e a lista de conversas fica longe do alcance do polegar. */}
              <div className="min-h-0 flex-1 p-3"><Transcricao msgs={msgs ?? []} altura="h-full min-h-[50vh] max-h-[70vh] lg:max-h-none lg:min-h-0" /></div>
            </>) : <EmptyState icone="chat" titulo="Selecione uma conversa" />}
          </section>
        </div>
      </Card>
    </div>
  );
}
