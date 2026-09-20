import { useMemo, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { api, ESTAGIOS, ROTULO } from "../lib/api";
import { CANAL, INTENCAO, REGIAO, brl, canalDoLead, nomeDoLead, relativo, rotulo } from "../lib/format";
import { Avatar, Button, Card, EmptyState, Estagio, Input, NomeLead, PageHeader, Paginacao, Select, Table, Temperatura, cx, usePaginacao } from "../components/ui";
import { Ic } from "../components/Icons";

type Ord = "score" | "recente" | "nome";

export function Leads() {
  const [sp, setSp] = useSearchParams();
  const estagio = sp.get("estagio") ?? "", temperatura = sp.get("temperatura") ?? "", corretor = sp.get("corretor") ?? "";
  const [busca, setBusca] = useState("");
  const [ord, setOrd] = useState<Ord>("score");
  const { data, isLoading } = useQuery({ queryKey: ["leads", { estagio, temperatura, corretor }], queryFn: () => api.leads({ estagio: estagio || undefined, temperatura: temperatura || undefined, corretor_id: corretor || undefined }) });
  const { data: corretores } = useQuery({ queryKey: ["corretores"], queryFn: api.corretores });
  const sync = useMutation({ mutationFn: api.crmSync });
  const setF = (k: string, v: string) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }); };

  const lista = useMemo(() => {
    const q = busca.trim().toLowerCase();
    const l = (data ?? []).filter((x) => !q || [x.nome, x.id, x.telefone, x.cartao.regiao, x.cartao.intencao].some((v) => v?.toLowerCase().includes(q)));
    return [...l].sort((a, b) => ord === "score" ? b.score - a.score : ord === "nome" ? (a.nome ?? a.id).localeCompare(b.nome ?? b.id) : (b.ultima_mensagem_em ?? "").localeCompare(a.ultima_mensagem_em ?? ""));
  }, [data, busca, ord]);
  const pag = usePaginacao(lista, 10, "leads");

  return (
    <div>
      <PageHeader titulo="Leads" descricao={data ? `${lista.length} de ${data.length} leads` : undefined}
        acoes={<Button onClick={() => sync.mutate()} disabled={sync.isPending} icone={<Ic.refresh size={14} />}>{sync.data ? `CRM: ${sync.data.exportados} exportados` : "Sincronizar CRM"}</Button>} />
      <Card semPadding>
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
          <div className="relative min-w-[220px] flex-1"><Ic.search size={15} className="pointer-events-none absolute left-2.5 top-2.5 text-ink-faint" /><Input className="pl-8" placeholder="Buscar por nome, telefone, região…" value={busca} onChange={(e) => setBusca(e.target.value)} /></div>
          <Select aria-label="Filtrar por estágio" className="w-48" value={estagio} onChange={(e) => setF("estagio", e.target.value)}><option value="">Todos os estágios</option>{ESTAGIOS.map((e) => <option key={e} value={e}>{ROTULO[e]}</option>)}</Select>
          <Select aria-label="Filtrar por temperatura" className="w-44" value={temperatura} onChange={(e) => setF("temperatura", e.target.value)}><option value="">Toda temperatura</option>{["quente", "morno", "frio"].map((t) => <option key={t} value={t}>{t}</option>)}</Select>
          <Select aria-label="Filtrar por corretor" className="w-48" value={corretor} onChange={(e) => setF("corretor", e.target.value)}><option value="">Todos os corretores</option>{corretores?.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}</Select>
          <Select aria-label="Ordenar a lista" className="w-40" value={ord} onChange={(e) => setOrd(e.target.value as Ord)}><option value="score">Maior score</option><option value="recente">Mais recente</option><option value="nome">Nome</option></Select>
          {(estagio || temperatura || corretor || busca) && <Button variante="fantasma" tamanho="sm" onClick={() => { setBusca(""); setSp({}, { replace: true }); }}>Limpar</Button>}
        </div>
        <Table colunas={["Lead", "Intenção", "Região", "Orçamento", "Estágio", "Temp.", { h: "Score", cls: "text-right" }, "Corretor", "Canal", "Último contato"]}
          vazio={!isLoading && lista.length === 0 ? <EmptyState icone="leads" titulo="Nenhum lead encontrado" descricao="Ajuste os filtros ou aguarde novas conversas nos canais." /> : undefined}>
          {pag.fatia.map((l) => (
            <tr key={l.id} className="hover:bg-surface-2">
              <td className="px-4 py-2.5"><Link to={`/leads/${l.id}`} className="flex items-center gap-2.5"><Avatar nome={nomeDoLead(l).avatar} /><span className="min-w-0"><NomeLead lead={l} className="block font-medium hover:underline" />{/* A segunda linha é o CONTATO, e só aparece quando acrescenta alguma coisa: sem nome, o
                     telefone JÁ É o título, e repeti-lo embaixo é a mesma informação duas vezes. */}
                {l.telefone && l.nome && <span className="block text-xs text-ink-muted">{l.telefone}</span>}</span></Link></td>
              <td className="px-4 py-2.5">{INTENCAO[l.cartao.intencao] ?? l.cartao.intencao}</td>
              <td className="px-4 py-2.5">{l.cartao.regiao ? REGIAO[l.cartao.regiao] ?? l.cartao.regiao : <span className="text-ink-faint">—</span>}</td>
              <td className="px-4 py-2.5 tabular-nums">{l.cartao.preco_max || l.cartao.ticket ? brl(l.cartao.preco_max ?? l.cartao.ticket, true) : <span className="text-ink-faint">—</span>}</td>
              <td className="px-4 py-2.5"><Estagio e={l.estagio} /></td>
              <td className="px-4 py-2.5"><Temperatura t={l.temperatura} /></td>
              <td className="px-4 py-2.5 text-right"><span className={cx("inline-block min-w-[2.2rem] rounded-md px-1.5 py-0.5 text-center text-xs font-semibold tabular-nums", l.score >= 70 ? "bg-bad-soft text-bad-strong" : l.score >= 40 ? "bg-warn-soft text-warn-strong" : "bg-surface-2 text-ink-muted")}>{l.score}</span></td>
              <td className="px-4 py-2.5 text-xs">{l.corretor_nome ? <span className="inline-flex items-center gap-1.5"><Avatar nome={l.corretor_nome} tamanho={20} />{l.corretor_nome}</span> : l.estagio === "handoff" ? <span className="text-warn-strong">sem corretor</span> : <span className="text-ink-faint">—</span>}</td>
              <td className="px-4 py-2.5 text-xs text-ink-muted">{l.canais?.length ? l.canais.map((c) => CANAL[c.canal] ?? c.canal).join(", ") : rotulo(CANAL, canalDoLead(l))}</td>
              <td className="px-4 py-2.5 text-xs text-ink-muted" title={l.ultima_mensagem_em ?? ""}>{relativo(l.ultima_mensagem_em)}</td>
            </tr>
          ))}
        </Table>
        <Paginacao {...pag} />
      </Card>
    </div>
  );
}
