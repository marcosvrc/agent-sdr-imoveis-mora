// Trilha de auditoria: quem fez o quê, quando e com que resultado. Leitura, filtro e exportação.
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type RegistroAuditoria } from "../lib/api";
import { dataHora } from "../lib/format";
import { Badge, Button, Card, EmptyState, Input, Modal, PageHeader, Paginacao, Select, Skeleton, StatTile, Table, cx, usePaginacao } from "../components/ui";
import { Ic } from "../components/Icons";

const PERIODOS = [7, 30, 90];

/** Nomes técnicos viram frases que um gestor entende sem manual. */
const ROTULO_ACAO: Record<string, string> = {
  "lead.handoff_assumido": "Corretor assumiu o lead",
  "lead.corretor_respondeu": "Corretor respondeu ao cliente",
  "lead.devolvido_ao_agente": "Lead devolvido à Mora",
  "lead.corretor_atribuido": "Corretor atribuído",
  "lead.analise_solicitada": "Análise de perfil solicitada",
  "lead.exportado_crm": "Leads exportados para o CRM",
  "lead.listado": "Carteira de leads consultada",
  "lead.consultado": "Ficha de lead consultada",
  "lead.contato_alterado": "Contato do lead alterado",
  "lead.encaminhado_corretor": "Mora encaminhou ao corretor",
  "lead.estagio_alterado": "Estágio do lead alterado",
  "lead.followup_enviado": "Follow-up enviado",
  "lead.contato_capturado": "Contato do cliente capturado",
  "visita.agendada": "Visita agendada",
  "corretor.criado": "Corretor cadastrado",
  "corretor.alterado": "Cadastro de corretor alterado",
  "corretor.removido": "Corretor removido",
  "imovel.foto_enviada": "Foto de imóvel enviada",
  "imovel.foto_removida": "Foto de imóvel removida",
  "imovel.fotos_reordenadas": "Fotos de imóvel reordenadas",
  "configuracao.alterada": "Configuração alterada",
  "configuracao.restaurada": "Configuração restaurada",
  "governanca.limites_alterados": "Limites de IA alterados",
  "governanca.preco_alterado": "Preço de modelo alterado",
  "governanca.preco_restaurado": "Preço de modelo restaurado",
  "agente.turno_falhou": "Falha ao responder o cliente",
  "agente.bloqueado_por_orcamento": "Agente bloqueado por orçamento",
  "auditoria.exportada": "Trilha de auditoria exportada",
};
const rotulo = (a: string) => ROTULO_ACAO[a] ?? a;

const ICONE_ATOR = { corretor: Ic.badge, agente: Ic.spark, sistema: Ic.gauge } as const;

export function Auditoria() {
  const [dias, setDias] = useState(30);
  const [acao, setAcao] = useState("");
  const [entidade, setEntidade] = useState("");
  const [ator, setAtor] = useState("");
  const [soSensiveis, setSoSensiveis] = useState(false);
  const [busca, setBusca] = useState("");
  const [aberto, setAberto] = useState<RegistroAuditoria | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["auditoria", dias, acao, entidade, ator, soSensiveis, busca],
    queryFn: () => api.auditoria({ dias, acao, entidade, ator, so_sensiveis: soSensiveis, busca }),
    refetchInterval: 60_000,
  });
  const registros = useMemo(() => data?.registros ?? [], [data]);
  const pg = usePaginacao(registros, 10, "auditoria");
  const sensiveis = new Set(data?.acoes_sensiveis ?? []);

  return (
    <div className="space-y-4">
      <PageHeader titulo="Auditoria" descricao="Trilha de tudo que muda o sistema e dos acessos a dados de clientes"
        acoes={
          <div className="flex items-center gap-2">
            <div className="inline-flex rounded-lg border border-line bg-surface p-0.5 text-xs">
              {PERIODOS.map((d) => (
                <button key={d} onClick={() => setDias(d)}
                  className={cx("rounded-md px-2.5 py-1.5 font-medium", dias === d ? "bg-brand text-brand-ink" : "text-ink-muted hover:text-ink")}>{d} dias</button>
              ))}
            </div>
            <Button icone={<Ic.external size={15} />} onClick={() => api.exportarAuditoria({ dias, acao, entidade })}>Exportar CSV</Button>
          </div>
        } />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label={`Registros · ${dias} dias`} valor={data ? String(data.resumo.total) : "—"} icone="overview" destaque
          ajuda={<>Tudo que mudou o sistema no período, mais os acessos a dados de cliente. Conta o período inteiro com os filtros aplicados — a tabela abaixo mostra no máximo os 300 mais recentes, então este número pode ser maior que a lista.</>} />
        <StatTile label="Ações sensíveis" valor={data ? String(data.resumo.sensiveis) : "—"} icone="eye"
          ajuda={<>Ações que tocam dado pessoal ou removem cadastro: exportar leads para o CRM, consultar a carteira inteira, exportar esta trilha, remover corretor. São as que um pedido de prestação de contas pede primeiro.</>} />
        <StatTile label="Ações com erro" valor={data ? String(data.resumo.erros) : "—"} subirEBom={false} icone="info"
          ajuda={<>Ações que não completaram — permissão negada, registro inexistente, falha do agente. Vale olhar quando sobe: costuma indicar integração quebrada, não tentativa de invasão.</>} />
        <StatTile label="Ações distintas" valor={data ? String(data.resumo.por_acao.length) : "—"} icone="bolt"
          ajuda={<>Quantos <b>tipos</b> diferentes de ação apareceram no período, não quantas vezes. Serve para ver a variedade do que está acontecendo: um número baixo com muitos registros significa muita repetição do mesmo evento.</>} />
      </div>

      <Card semPadding>
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
          <div className="relative"><Ic.search size={15} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint" />
            <Input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar por ator, id ou conteúdo" className="w-64 pl-8" /></div>
          <Select aria-label="Filtrar por ação" value={acao} onChange={(e) => setAcao(e.target.value)} className="w-56">
            <option value="">Todas as ações</option>
            {(data?.resumo.acoes_conhecidas ?? []).map((a) => <option key={a} value={a}>{rotulo(a)}</option>)}
          </Select>
          <Select aria-label="Filtrar por entidade" value={entidade} onChange={(e) => setEntidade(e.target.value)} className="w-44">
            <option value="">Todas as entidades</option>
            {(data?.resumo.entidades_conhecidas ?? []).map((e) => <option key={e} value={e}>{e}</option>)}
          </Select>
          <Select aria-label="Filtrar por tipo de ator" value={ator} onChange={(e) => setAtor(e.target.value)} className="w-44">
            <option value="">Todos os atores</option>
            <option value="corretor">Corretores</option>
            <option value="agente">Mora</option>
            <option value="sistema">Sistema</option>
          </Select>
          <button onClick={() => setSoSensiveis(!soSensiveis)}
            className={cx("inline-flex h-9 items-center gap-1.5 rounded-lg border px-3 text-xs font-medium",
              soSensiveis ? "border-warn-line bg-warn-soft text-warn-strong" : "border-line bg-surface text-ink-muted hover:text-ink")}>
            <Ic.eye size={14} />Só sensíveis
          </button>
          {(acao || entidade || ator || busca || soSensiveis) &&
            <Button variante="fantasma" tamanho="sm" onClick={() => { setAcao(""); setEntidade(""); setAtor(""); setBusca(""); setSoSensiveis(false); }}>Limpar</Button>}
          <span className="ml-auto text-xs text-ink-muted">{registros.length} registro{registros.length === 1 ? "" : "s"}</span>
        </div>

        {isLoading ? <div className="p-4"><Skeleton className="h-96" /></div>
          : registros.length === 0 ? <div className="p-6"><EmptyState titulo="Nenhum registro no período" descricao="Ajuste os filtros ou amplie o período." icone="search" /></div>
          : <>
            <Table colunas={[{ h: "Quando", cls: "w-40" }, { h: "Quem", cls: "w-52" }, "Ação", { h: "Alvo", cls: "w-48" }, { h: "Resultado", cls: "w-28 text-center" }, { h: "", cls: "w-12 text-center" }]}>
              {pg.fatia.map((r) => {
                const IconeAtor = ICONE_ATOR[r.ator_tipo as keyof typeof ICONE_ATOR] ?? Ic.dot;
                return (
                  <tr key={r.id} className="border-t border-line hover:bg-surface-2">
                    <td className="px-3 py-2 text-xs tabular-nums text-ink-muted">{dataHora(r.em)}</td>
                    <td className="px-3 py-2 text-sm">
                      <span className="inline-flex items-center gap-1.5"><IconeAtor size={14} className="text-ink-muted" />
                        <span className="truncate">{r.ator_nome ?? r.ator_id ?? r.ator_tipo}</span></span>
                    </td>
                    <td className="px-3 py-2 text-sm">
                      <span className="inline-flex items-center gap-2">{rotulo(r.acao)}
                        {sensiveis.has(r.acao) && <Badge tom="warn" icone={<Ic.eye size={11} />}>sensível</Badge>}</span>
                    </td>
                    <td className="px-3 py-2 text-xs text-ink-muted">
                      {r.entidade === "lead" && r.entidade_id
                        ? <Link to={`/leads/${r.entidade_id}`} className="text-brand-accent hover:underline">{r.entidade_id}</Link>
                        : <span className="truncate">{r.entidade}{r.entidade_id ? ` · ${r.entidade_id}` : ""}</span>}
                    </td>
                    <td className="px-3 py-2 text-center">
                      <Badge tom={r.resultado === "ok" ? "good" : "bad"}>{r.resultado === "ok" ? "ok" : "erro"}</Badge>
                    </td>
                    <td className="px-3 py-2 text-center">
                      <button onClick={() => setAberto(r)} className="rounded-md p-1.5 text-ink-muted hover:bg-surface-2 hover:text-ink" title="Ver detalhes"><Ic.eye size={15} /></button>
                    </td>
                  </tr>
                );
              })}
            </Table>
            <Paginacao {...pg} />
          </>}
      </Card>

      <Detalhe registro={aberto} onFechar={() => setAberto(null)} sensivel={aberto ? sensiveis.has(aberto.acao) : false} />
    </div>
  );
}

function Detalhe({ registro, onFechar, sensivel }: { registro: RegistroAuditoria | null; onFechar: () => void; sensivel: boolean }) {
  if (!registro) return null;
  const linhas: [string, string][] = [
    ["Quando", dataHora(registro.em)],
    ["Ator", `${registro.ator_nome ?? registro.ator_id ?? "—"} (${registro.ator_tipo})`],
    ["Ação", `${rotulo(registro.acao)} · ${registro.acao}`],
    ["Entidade", `${registro.entidade}${registro.entidade_id ? ` · ${registro.entidade_id}` : ""}`],
    ["Resultado", registro.resultado],
    ["Origem", registro.origem ?? "—"],
  ];
  return (
    <Modal aberto onFechar={onFechar} titulo={rotulo(registro.acao)}>
      <div className="space-y-4">
        {sensivel && (
          <div className="flex items-start gap-2 rounded-lg border border-warn-line bg-warn-soft px-3 py-2 text-xs text-warn-strong">
            <Ic.eye size={14} className="mt-0.5 shrink-0" />
            <span>Ação sensível: toca dados de clientes ou remove cadastro. A trilha registra que o acesso ocorreu — o conteúdo em si permanece apenas no cadastro.</span>
          </div>
        )}
        <dl className="grid grid-cols-[7rem_1fr] gap-x-3 gap-y-2 text-sm">
          {linhas.map(([k, v]) => (<div key={k} className="contents"><dt className="text-ink-muted">{k}</dt><dd className="break-words">{v}</dd></div>))}
        </dl>
        {registro.detalhe && <div className="rounded-lg border border-bad-line bg-bad-soft p-3 text-xs text-bad-strong"><pre className="whitespace-pre-wrap font-mono">{registro.detalhe}</pre></div>}
        <div>
          <div className="mb-1.5 text-xs font-medium text-ink-muted">Dados registrados</div>
          <pre className="max-h-72 overflow-auto rounded-lg border border-line bg-surface-2 p-3 text-xs font-mono text-ink">{JSON.stringify(registro.dados, null, 2)}</pre>
        </div>
      </div>
    </Modal>
  );
}
