import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ChamadaLLM, type EstadoOrcamento, type Limites, type Uso } from "../lib/api";
import { brlCusto, dataHora, num, pct, tokens as fmtTokens, usd } from "../lib/format";
import { Badge, Button, Card, Field, Input, PageHeader, Paginacao, Select, Skeleton, StatTile, Table, Tabs, cx, usePaginacao } from "../components/ui";
import { CustoChart, RankingUso, TokensChart } from "../components/chartsUso";
import { Ic } from "../components/Icons";

type Aba = "consumo" | "limites" | "precos";
const PERIODOS = [7, 30, 90];

export function Governanca() {
  const [aba, setAba] = useState<Aba>("consumo");
  const [dias, setDias] = useState(30);
  const { data: uso, isLoading } = useQuery({ queryKey: ["uso", dias], queryFn: () => api.uso(dias), refetchInterval: 30_000 });
  const cotacao = uso?.orcamento.limites.cotacao_brl ?? 5.12;

  return (
    <div className="space-y-4">
      <PageHeader titulo="Governança de IA" descricao="Quanto a Mora consome de modelos e tokens, quanto isso custa e os limites da operação"
        acoes={aba === "consumo" ? <div className="inline-flex rounded-lg border border-line bg-surface p-0.5 text-xs">{PERIODOS.map((d) => <button key={d} onClick={() => setDias(d)} className={cx("rounded-md px-2.5 py-1.5 font-medium", dias === d ? "bg-brand text-brand-ink" : "text-ink-muted hover:text-ink")}>{d} dias</button>)}</div> : undefined} />

      {uso && <EstadoAgente estado={uso.orcamento} configuracao={uso.configuracao_atual} />}

      <Card semPadding>
        <Tabs<Aba> atual={aba} onMudar={setAba} abas={[
          { k: "consumo", r: "Consumo" },
          { k: "limites", r: "Limites", badge: uso?.orcamento.em_alerta || uso?.orcamento.estourado ? <span className="h-1.5 w-1.5 rounded-full bg-[var(--status-warn)]" /> : undefined },
          { k: "precos", r: "Preços" }]} />
        <div className="p-4">
          {aba === "consumo" && (isLoading || !uso ? <Skeleton className="h-96" /> : <Consumo uso={uso} dias={dias} cotacao={cotacao} />)}
          {aba === "limites" && <AbaLimites />}
          {aba === "precos" && <AbaPrecos cotacao={cotacao} />}
        </div>
      </Card>
    </div>
  );
}

/** Faixa de estado: o corretor precisa saber, sem procurar, se o agente está degradado ou bloqueado. */
function EstadoAgente({ estado, configuracao }: { estado: EstadoOrcamento; configuracao: Uso["configuracao_atual"] }) {
  const modo = estado.modo;
  const cor = modo === "bloqueado" ? "border-bad-line bg-bad-soft text-bad-strong"
    : modo === "degradado" ? "border-warn-line bg-warn-soft text-warn-strong"
    : estado.em_alerta ? "border-warn-line bg-warn-soft text-warn-strong" : "border-line bg-surface text-ink";
  const texto = modo === "bloqueado"
    ? "Orçamento esgotado: a Mora não está chamando o modelo — novas conversas vão direto para um corretor."
    : modo === "degradado"
      ? "Orçamento estourado: a Mora está respondendo com o modelo econômico (Haiku) até o próximo ciclo."
      : estado.em_alerta ? `Consumo em ${pct(estado.pct)} do limite — perto do teto configurado.`
      : "Operando normalmente dentro do orçamento.";
  const Icone = modo === "normal" && !estado.em_alerta ? Ic.check : Ic.info;
  return (
    <div className={cx("flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border px-4 py-3 text-sm shadow-card", cor)}>
      <span className="flex items-center gap-2 font-medium"><Icone size={16} />{texto}</span>
      <span className="ml-auto flex flex-wrap items-center gap-2 text-xs">
        <Badge tom={modo === "normal" ? "good" : modo === "degradado" ? "warn" : "bad"}>modo {modo}</Badge>
        <span className="text-ink-muted">{configuracao.provider} · {configuracao.modelo_conversa.replace(/^anthropic\./, "")} / {configuracao.modelo_roteamento.replace(/^anthropic\./, "")}</span>
      </span>
    </div>
  );
}

function Consumo({ uso, dias, cotacao }: { uso: Uso; dias: number; cotacao: number }) {
  const k = uso.kpis;
  const variacao = (a: number, b: number) => b === 0 ? (a === 0 ? 0 : null) : (a - b) / b;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label={`Tokens · ${dias} dias`} valor={fmtTokens(k.tokens.atual)} delta={variacao(k.tokens.atual, k.tokens.anterior)} subirEBom={false} icone="bolt"
          ajuda={<>Tudo que passou pelos modelos no período: entrada, saída e também os tokens de cache. Por isso é maior que a soma dos dois indicadores de entrada e saída abaixo.</>} />
        <StatTile label="Custo do período" valor={usd(k.custo.atual)} sufixo={`≈ ${brlCusto(k.custo.atual, cotacao)}`} delta={variacao(k.custo.atual, k.custo.anterior)} subirEBom={false} icone="coins" destaque
          ajuda={<>Custo real das chamadas do período, calculado chamada a chamada com a tabela da aba <b>Preços</b>. O valor em real usa a cotação definida em Limites — atualize-a para o número fazer sentido no fechamento.</>} />
        <StatTile label="Custo por lead atendido" valor={usd(k.custo_por_lead.atual)} sufixo={`≈ ${brlCusto(k.custo_por_lead.atual, cotacao)}`} delta={variacao(k.custo_por_lead.atual, k.custo_por_lead.anterior)} subirEBom={false} icone="leads"
          ajuda={<>Custo do período dividido pelos leads que efetivamente conversaram com a Mora nele. É o número para comparar com o que a imobiliária gasta hoje para atender um lead — e o que sobe quando as conversas ficam longas demais.</>} />
        <StatTile label="Latência média" valor={`${Math.round(k.latencia.atual)} ms`} delta={variacao(k.latencia.atual, k.latencia.anterior)} subirEBom={false} icone="clock"
          ajuda={<>Tempo médio de cada chamada a modelo, incluindo as que falharam. Não é o tempo total que o cliente espera: um turno pode somar duas ou três chamadas (roteamento, extração e resposta).</>} />
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Chamadas ao modelo" valor={num(k.chamadas.atual)} delta={variacao(k.chamadas.atual, k.chamadas.anterior)} subirEBom={false}
          ajuda={<>Quantas vezes um modelo foi chamado no período. Cada mensagem do cliente costuma gerar mais de uma: roteamento e extração no modelo econômico, resposta no modelo de conversa.</>} />
        <StatTile label="Tokens de entrada" valor={fmtTokens(k.entrada.atual)}
          ajuda={<>O que foi enviado aos modelos: instruções, histórico da conversa e os imóveis encontrados. Cresce naturalmente conforme a conversa avança, porque o histórico vai junto a cada turno.</>} />
        <StatTile label="Tokens de saída" valor={fmtTokens(k.saida.atual)}
          ajuda={<>O que os modelos escreveram. Custa bem mais caro por token que a entrada — é por isso que a persona limita as respostas a três frases.</>} />
        <StatTile label="Chamadas com erro" valor={num(k.erros.atual)} subirEBom={false}
          ajuda={<>Chamadas que falharam (timeout, indisponibilidade, limite do provedor). Não significa cliente sem resposta: quando o turno falha, a Mora avisa e encaminha a conversa a um corretor.</>} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card titulo="Tokens por dia" acoes={<span className="text-xs text-ink-muted">entrada + saída</span>}><TokensChart serie={uso.serie} /></Card>
        <Card titulo="Custo por dia" acoes={<span className="text-xs text-ink-muted">US$ · cotação R$ {cotacao.toFixed(2).replace(".", ",")}</span>}><CustoChart serie={uso.serie} /></Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card titulo="Por modelo"><RankingUso linhas={uso.por_modelo} cotacao={cotacao} rotulo={(m) => m.replace(/^anthropic\./, "")} /></Card>
        <Card titulo="Por etapa do agente"><RankingUso linhas={uso.por_no} cotacao={cotacao} /></Card>
        <Card titulo="Por papel"><RankingUso linhas={uso.por_papel} cotacao={cotacao} /></Card>
      </div>

      <ChamadasRecentes chamadas={uso.recentes} />
    </div>
  );
}

/** Últimas chamadas ao modelo. Paginada: a lista costuma ser lida procurando uma chamada específica
 *  (a que deu erro, a mais cara), e rolar dentro de um quadro curto atrapalha essa leitura. */
function ChamadasRecentes({ chamadas }: { chamadas: ChamadaLLM[] }) {
  const pg = usePaginacao(chamadas, 10, "chamadas-llm");
  return (
    <Card titulo="Chamadas recentes" acoes={<span className="text-xs text-ink-muted">últimas {chamadas.length}</span>} semPadding>
      <Table colunas={["Quando", "Etapa", "Modelo", { h: "Entrada", cls: "text-right" }, { h: "Saída", cls: "text-right" }, { h: "Custo", cls: "text-right" }, { h: "Latência", cls: "text-right" }, "Lead"]}>
        {pg.fatia.map((c) => (
          <tr key={c.id} className={cx("hover:bg-surface-2", c.erro && "bg-bad-soft")}>
            <td className="px-4 py-2 text-xs text-ink-muted">{dataHora(c.em)}</td>
            <td className="px-4 py-2">{c.no ?? "—"}{c.papel && <span className="ml-1 text-[11px] text-ink-muted">({c.papel})</span>}</td>
            <td className="px-4 py-2 text-xs">{c.modelo.replace(/^anthropic\./, "")}</td>
            <td className="px-4 py-2 text-right tabular-nums">{num(c.tokens_entrada)}{c.tokens_cache_leitura > 0 && <span className="ml-1 text-[11px] text-good-strong" title="tokens lidos do cache (mais baratos)">+{num(c.tokens_cache_leitura)} cache</span>}</td>
            <td className="px-4 py-2 text-right tabular-nums">{num(c.tokens_saida)}</td>
            <td className="px-4 py-2 text-right tabular-nums">{usd(c.custo_usd)}</td>
            <td className="px-4 py-2 text-right tabular-nums text-ink-muted">{c.latencia_ms ?? "—"} ms</td>
            <td className="px-4 py-2 text-xs">{c.erro ? <Badge tom="bad">erro</Badge> : c.lead_id ?? "—"}</td>
          </tr>))}
      </Table>
      <Paginacao {...pg} />
    </Card>
  );
}

function AbaLimites() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["limites"], queryFn: api.limites });
  const [form, setForm] = useState<Limites | null>(null);
  const [salvo, setSalvo] = useState(false);
  useEffect(() => { if (data) setForm(data.limites); }, [data]);
  const salvar = useMutation({ mutationFn: () => api.salvarLimites(form!), onSuccess: () => { qc.invalidateQueries({ queryKey: ["limites"] }); qc.invalidateQueries({ queryKey: ["uso"] }); setSalvo(true); setTimeout(() => setSalvo(false), 2500); } });
  if (!data || !form) return <Skeleton className="h-64" />;
  const e = data.estado;
  const alterado = JSON.stringify(form) !== JSON.stringify(data.limites);
  const set = <K extends keyof Limites>(k: K, v: Limites[K]) => setForm({ ...form, [k]: v });

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-4">
        <h3 className="text-sm font-semibold">Consumo do ciclo atual</h3>
        <Medidor titulo="Orçamento do mês" atual={usd(e.gasto_mes_usd)} limite={form.orcamento_mensal_usd ? usd(form.orcamento_mensal_usd) : "sem teto"}
          sufixo={`≈ ${brlCusto(e.gasto_mes_usd, form.cotacao_brl)} de ${brlCusto(form.orcamento_mensal_usd, form.cotacao_brl)}`} pct={e.pct_orcamento} alerta={form.alerta_pct / 100} />
        <Medidor titulo="Tokens de hoje" atual={fmtTokens(e.tokens_hoje)} limite={form.teto_tokens_dia ? fmtTokens(form.teto_tokens_dia) : "sem teto"} pct={e.pct_tokens} alerta={form.alerta_pct / 100} />
        <div className="rounded-lg bg-canvas p-3 text-xs text-ink-muted">
          <p className="mb-1 font-medium text-ink">O que acontece ao estourar</p>
          <p><b>Degradar</b>: a Mora troca o modelo de conversa pelo econômico; passando de 150% do limite, entrega a conversa a um corretor.
             <br /><b>Alertar</b>: nada muda no atendimento, só o aviso aqui. <b>Bloquear</b>: a Mora para de chamar o modelo e encaminha ao corretor.</p>
        </div>
      </div>
      <form className="space-y-4" onSubmit={(ev) => { ev.preventDefault(); salvar.mutate(); }}>
        <div className="flex items-center justify-between"><h3 className="text-sm font-semibold">Limites</h3>{salvo && <Badge tom="good" icone={<Ic.check size={10} />}>salvo</Badge>}</div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Orçamento mensal (US$)" dica="0 = sem teto"><Input type="number" min={0} step="1" value={form.orcamento_mensal_usd} onChange={(ev) => set("orcamento_mensal_usd", Number(ev.target.value))} /></Field>
          <Field label="Teto de tokens por dia" dica="0 = sem teto"><Input type="number" min={0} step="10000" value={form.teto_tokens_dia} onChange={(ev) => set("teto_tokens_dia", Number(ev.target.value))} /></Field>
          <Field label="Alertar a partir de (%)"><Input type="number" min={1} max={100} value={form.alerta_pct} onChange={(ev) => set("alerta_pct", Number(ev.target.value))} /></Field>
          <Field label="Cotação do dólar (R$)" dica="usada só para exibir custos em real"><Input type="number" min={0.1} step="0.01" value={form.cotacao_brl} onChange={(ev) => set("cotacao_brl", Number(ev.target.value))} /></Field>
        </div>
        <Field label="Ao estourar o limite">
          <Select value={form.acao_ao_estourar} onChange={(ev) => set("acao_ao_estourar", ev.target.value as Limites["acao_ao_estourar"])}>
            <option value="degradar">Degradar para o modelo econômico</option>
            <option value="alertar">Apenas alertar (não muda o atendimento)</option>
            <option value="bloquear">Bloquear e encaminhar ao corretor</option>
          </Select>
        </Field>
        <div className="flex justify-end gap-2 border-t border-line pt-4">
          <Button type="button" onClick={() => setForm(data.limites)} disabled={!alterado}>Descartar</Button>
          <Button type="submit" variante="primario" disabled={!alterado || salvar.isPending}>Salvar limites</Button>
        </div>
        {salvar.isError && <p className="rounded-lg bg-bad-soft px-3 py-2 text-xs text-bad-strong">{(salvar.error as Error).message}</p>}
      </form>
    </div>
  );
}

function Medidor({ titulo, atual, limite, pct: p, alerta, sufixo }: { titulo: string; atual: string; limite: string; pct: number; alerta: number; sufixo?: string }) {
  const larg = Math.min(p, 1) * 100;
  const cor = p >= 1 ? "var(--status-bad)" : p >= alerta ? "var(--status-warn)" : "var(--status-good)";
  return (
    <div className="rounded-lg border border-line p-3">
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <span className="text-xs text-ink-muted">{titulo}</span>
        <span className="text-sm"><b className="tabular-nums text-ink">{atual}</b> <span className="text-ink-muted">de {limite}</span></span>
      </div>
      <div className="relative h-2 rounded-full bg-surface-2">
        <div className="h-2 rounded-full transition-[width] duration-500" style={{ width: `${larg}%`, background: cor }} />
        {alerta < 1 && <span className="absolute top-[-2px] h-3 w-px bg-ink-faint" style={{ left: `${alerta * 100}%` }} title={`alerta em ${Math.round(alerta * 100)}%`} />}
      </div>
      <p className="mt-1 flex justify-between text-[11px] text-ink-muted"><span>{sufixo}</span><span className="tabular-nums">{pct(p)}</span></p>
    </div>
  );
}

function AbaPrecos({ cotacao }: { cotacao: number }) {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["precos"], queryFn: api.precos });
  const [edit, setEdit] = useState<{ modelo: string; entrada: number; saida: number } | null>(null);
  const salvar = useMutation({ mutationFn: () => api.salvarPreco(edit!.modelo, { entrada: edit!.entrada, saida: edit!.saida, cache_escrita: 0, cache_leitura: 0 }), onSuccess: () => { qc.invalidateQueries({ queryKey: ["precos"] }); qc.invalidateQueries({ queryKey: ["uso"] }); setEdit(null); } });
  const restaurar = useMutation({ mutationFn: (m: string) => api.restaurarPreco(m), onSuccess: () => qc.invalidateQueries({ queryKey: ["precos"] }) });
  const linhas = useMemo(() => Object.entries(data?.precos ?? {}).sort((a, b) => b[1][0] - a[1][0]), [data]);
  const pgPrecos = usePaginacao(linhas, 10, "precos");
  if (!data) return <Skeleton className="h-64" />;
  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-muted">Preços por 1 milhão de tokens, em dólares, usados para calcular o custo de cada chamada. Os valores padrão seguem a tabela pública da Anthropic; ajuste se você tem preço negociado ou usa outro provedor.</p>
      <Table colunas={["Modelo", { h: "Entrada / 1M", cls: "text-right" }, { h: "Saída / 1M", cls: "text-right" }, { h: "Leitura de cache", cls: "text-right" }, { h: "", cls: "w-16" }, { h: " ", cls: "w-16" }]}>
        {pgPrecos.fatia.map(([m, p]) => {
          const custom = data.personalizados.includes(m);
          const editando = edit?.modelo === m;
          return (
            <tr key={m} className="hover:bg-surface-2">
              <td className="px-4 py-2 font-medium">{m}{custom && <Badge tom="info">ajustado</Badge>}</td>
              <td className="px-4 py-2 text-right tabular-nums">{editando ? <Input className="w-24 text-right" type="number" step="0.01" min={0} value={edit.entrada} onChange={(e) => setEdit({ ...edit, entrada: Number(e.target.value) })} /> : <>US$ {p[0]} <span className="text-[11px] text-ink-muted">· R$ {(p[0] * cotacao).toFixed(2).replace(".", ",")}</span></>}</td>
              <td className="px-4 py-2 text-right tabular-nums">{editando ? <Input className="w-24 text-right" type="number" step="0.01" min={0} value={edit.saida} onChange={(e) => setEdit({ ...edit, saida: Number(e.target.value) })} /> : <>US$ {p[1]} <span className="text-[11px] text-ink-muted">· R$ {(p[1] * cotacao).toFixed(2).replace(".", ",")}</span></>}</td>
              <td className="px-4 py-2 text-right tabular-nums text-ink-muted">US$ {p[3] ?? 0}</td>
              <td className="px-4 py-2 text-right">
                {editando
                  ? <span className="flex justify-end gap-1"><Button tamanho="sm" onClick={() => setEdit(null)}>Cancelar</Button><Button tamanho="sm" variante="primario" onClick={() => salvar.mutate()} disabled={salvar.isPending}>Salvar</Button></span>
                  : <Button tamanho="sm" variante="fantasma" onClick={() => setEdit({ modelo: m, entrada: p[0], saida: p[1] })} aria-label={`Editar preço de ${m}`}><Ic.edit size={14} /></Button>}
              </td>
              <td className="px-4 py-2 text-right">{custom && !editando && <Button tamanho="sm" variante="fantasma" onClick={() => restaurar.mutate(m)} title="Voltar ao preço padrão"><Ic.refresh size={14} /></Button>}</td>
            </tr>);
        })}
      </Table>
      <Paginacao {...pgPrecos} />
    </div>
  );
}
