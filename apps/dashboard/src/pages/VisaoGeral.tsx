import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { brl, duracao, num, pct, relativo, variacao, REGIAO, INTENCAO, CANAL } from "../lib/format";
import { Ajuda, Card, PageHeader, StatTile, Estagio, Skeleton, EmptyState, Avatar, cx } from "../components/ui";
import { SerieChart, FunilChart, Distribuicao } from "../components/charts";
import { LeadsPorTemperatura } from "../components/Temperaturas";
import { ReativacaoResumo } from "../components/ReativacaoResumo";
import { Ic } from "../components/Icons";

const PERIODOS = [{ d: 7, r: "7 dias" }, { d: 14, r: "14 dias" }, { d: 30, r: "30 dias" }, { d: 90, r: "90 dias" }];

export function VisaoGeral() {
  const [dias, setDias] = useState(7);
  const { data: m, isLoading } = useQuery({ queryKey: ["metricas", dias], queryFn: () => api.metricas(dias) });
  const { data: quentes } = useQuery({ queryKey: ["leads", "quente"], queryFn: () => api.leads({ temperatura: "quente" }) });
  const { data: atividade } = useQuery({ queryKey: ["atividade"], queryFn: api.atividade });
  const k = m?.kpis;
  const taxaQual = k ? { atual: k.qualificados.atual / (k.leads.atual || 1), anterior: k.qualificados.anterior / (k.leads.anterior || 1) } : null;
  const taxaVis = k ? { atual: k.visitas.atual / (k.leads.atual || 1), anterior: k.visitas.anterior / (k.leads.anterior || 1) } : null;

  return (
    <div className="space-y-5">
      <PageHeader titulo="Visão geral" descricao={m ? `${num(m.totais.leads)} leads atendidos pela Mora · ${num(m.totais.imoveis)} imóveis no índice` : "Como o agente está atendendo"}
        acoes={<div className="inline-flex rounded-lg border border-line bg-surface p-0.5 text-xs">{PERIODOS.map((p) => <button key={p.d} onClick={() => setDias(p.d)} className={cx("rounded-md px-2.5 py-1.5 font-medium transition", dias === p.d ? "bg-brand text-brand-ink" : "text-ink-muted hover:text-ink")}>{p.r}</button>)}</div>} />

      {/* KPIs */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {isLoading || !k ? Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-24" />) : <>
          <StatTile label="Leads novos" valor={num(k.leads.atual)} delta={variacao(k.leads.atual, k.leads.anterior)} icone="leads" destaque
            ajuda={<>Pessoas que iniciaram conversa no período selecionado, contadas pela data de entrada. Inclui quem já foi encerrado depois. A comparação é com a janela imediatamente anterior de mesmo tamanho.</>} />
          <StatTile label="Taxa de qualificação" valor={pct(taxaQual!.atual)} delta={variacao(taxaQual!.atual, taxaQual!.anterior)} icone="check"
            ajuda={<>Dos leads que entraram no período, quantos chegaram a <b>qualificado</b>, <b>agendado</b> ou <b>com corretor</b>. Mede o quanto a Mora está conseguindo extrair da conversa. O numerador olha o estágio de hoje, então um lead que entrou ontem e avançou agora já conta.</>} />
          <StatTile label="Visitas reservadas" valor={num(k.visitas.atual)} delta={variacao(k.visitas.atual, k.visitas.anterior)} icone="calendar"
            ajuda={<>Horários que a Mora <b>reservou</b> no período, contados pela data da reserva e não pela data da visita. <b>Reservado não é confirmado</b>: quem confirma a visita é o corretor, no CRM. Este número mede o que o agente conseguiu encaminhar, não compromissos assumidos.</>} />
          <StatTile label="Tempo de 1ª resposta" valor={duracao(k.resposta_seg.atual)} delta={k.resposta_seg.atual != null && k.resposta_seg.anterior ? variacao(k.resposta_seg.atual, k.resposta_seg.anterior) : null} subirEBom={false} icone="bolt"
            ajuda={<>Quanto o cliente espera entre mandar a primeira mensagem e receber a primeira resposta, na média dos leads do período. Quanto menor, melhor — por isso a queda aparece em verde.</>} />
          <StatTile label="Encaminhados ao corretor" valor={num(k.handoffs.atual)} delta={variacao(k.handoffs.atual, k.handoffs.anterior)} icone="handoff"
            ajuda={<>Leads que entraram no período e estão <b>agora</b> com um corretor humano. É um retrato do momento: se o corretor devolveu a conversa à Mora, o lead sai desta conta.</>} />
        </>}
      </div>
      {/* Pipeline, ticket médio e valor em visitas saíram para o CRM: são leitura COMERCIAL da
          carteira, e o corretor decide sobre ela no sistema dele. Repetir aqui criava dois números
          para a mesma pergunta, calculados de fontes diferentes — e quando divergissem ninguém
          saberia qual acreditar. O que sobrou, nesta fileira única, é o que só a Mora sabe. */}

      {/* Leads por temperatura: prioridade de atendimento em três grupos */}
      <section>
        <div className="mb-2 flex items-end justify-between gap-2">
          <h2 className="flex items-center gap-1.5 text-sm font-semibold text-ink">
            Leads por temperatura
            <Ajuda titulo="De onde vem a temperatura" alinhar="esquerda">
              Cada lead recebe um score de 0 a 100 calculado sem IA, a partir do que ele contou: intenção, região,
              orçamento, quartos e urgência somam pontos; pedir visita e abrir imóveis no site somam mais; cada
              follow-up sem resposta desconta. O score vira a faixa mostrada nos cards. Este quadro é a
              <b> base inteira</b>, não o período selecionado acima.
            </Ajuda>
          </h2>
          <span className="text-xs text-ink-muted">{m ? `${num(Object.values(m.temperaturas).reduce((a, b) => a + b, 0))} leads na base` : ""}</span>
        </div>
        {m ? <LeadsPorTemperatura temperaturas={m.temperaturas} /> : <div className="grid gap-3 sm:grid-cols-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-40" />)}</div>}
      </section>

      {/* Série + funil */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2" titulo={`Atividade por dia · últimos ${dias} dias`}>{m ? <SerieChart serie={m.serie} /> : <Skeleton className="h-[240px]" />}</Card>
        <Card titulo="Funil de leads" acoes={m && <span className="text-xs text-ink-muted">taxa de visita {pct(taxaVis!.atual)}</span>}>
          {m ? <FunilChart estagios={Object.fromEntries(Object.entries(m.pipeline.por_estagio).map(([e, v]) => [e, v.n]))} /> : <Skeleton className="h-[200px]" />}
        </Card>
      </div>

      {/* Distribuições. O "pipeline por estágio" em R$ saiu com os outros números comerciais: o
          valor da carteira é leitura do CRM. O FUNIL acima fica, porque conta leads por estágio da
          MORA — é medida de atendimento, não de dinheiro. */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card titulo="Leads por região">{m ? <Distribuicao dados={m.por_regiao} rotulos={REGIAO} /> : <Skeleton className="h-32" />}</Card>
        <div className="grid gap-4">
          <Card titulo="Por intenção">{m ? <Distribuicao dados={m.por_intencao} rotulos={INTENCAO} cor="var(--series-2)" /> : <Skeleton className="h-16" />}</Card>
          <Card titulo="Por canal">{m ? <Distribuicao dados={m.por_canal} rotulos={CANAL} cor="var(--series-3)" /> : <Skeleton className="h-16" />}</Card>
        </div>
      </div>

      {/* Reativação: a única mensagem que a Mora manda sem ninguém pedir — e por isso a que mais
          precisa de acompanhamento. Fora do filtro de período do topo: a janela é de 30 dias porque
          reativação é lenta por natureza (ver ADR-0013). */}
      <ReativacaoResumo />

      {/* Prioridade + atividade */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card titulo="Prioridade agora" acoes={<Link to="/leads?temperatura=quente" className="text-xs font-medium text-brand-accent hover:underline">ver todos</Link>} semPadding>
          {quentes?.length ? (
            <ul className="divide-y divide-line">
              {quentes.slice(0, 6).map((l) => (
                <li key={l.id}><Link to={`/leads/${l.id}`} className="flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-surface-2">
                  <Avatar nome={l.nome ?? l.id} />
                  <div className="min-w-0 flex-1"><p className="truncate font-medium">{l.nome ?? l.id}</p><p className="truncate text-xs text-ink-muted">{INTENCAO[l.cartao.intencao] ?? l.cartao.intencao} · {REGIAO[l.cartao.regiao ?? ""] ?? "região não informada"}{l.cartao.preco_max ? ` · até ${brl(l.cartao.preco_max, true)}` : ""}</p></div>
                  <Estagio e={l.estagio} /><span className="w-9 text-right text-xs tabular-nums text-ink-muted">{l.score}</span><Ic.chevronRight size={14} className="text-ink-faint" />
                </Link></li>))}
            </ul>
          ) : <EmptyState icone="flame" titulo="Nenhum lead quente" descricao="Leads com cartão completo e urgência aparecem aqui." />}
        </Card>
        <Card titulo="Atividade recente" acoes={<Link to="/conversas" className="text-xs font-medium text-brand-accent hover:underline">abrir conversas</Link>} semPadding>
          {atividade?.length ? (
            <ul className="max-h-[360px] divide-y divide-line overflow-y-auto">
              {atividade.slice(0, 12).map((a) => (
                <li key={a.id} className="flex gap-3 px-4 py-2.5 text-sm">
                  <span className={cx("mt-1 h-2 w-2 shrink-0 rounded-full", a.direcao === "in" ? "bg-[var(--series-1)]" : a.direcao === "corretor" ? "bg-[var(--series-6)]" : "bg-ink-faint")} />
                  <div className="min-w-0 flex-1"><p className="truncate"><Link to={`/leads/${a.lead_id}`} className="font-medium hover:underline">{a.nome ?? a.lead_id}</Link> <span className="text-ink-muted">{a.direcao === "in" ? "disse" : a.direcao === "corretor" ? "· corretor respondeu" : "· Mora respondeu"}</span></p><p className="truncate text-xs text-ink-muted">{a.conteudo}</p></div>
                  <span className="shrink-0 text-[11px] text-ink-faint">{relativo(a.em)}</span>
                </li>))}
            </ul>
          ) : <EmptyState icone="chat" titulo="Sem mensagens ainda" descricao="As conversas dos canais aparecem aqui em tempo real." />}
        </Card>
      </div>
    </div>
  );
}
