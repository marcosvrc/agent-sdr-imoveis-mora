// Saúde do sistema (ADR-0011): observabilidade sem stack — tudo vem de três tabelas do Postgres
// que já roda. A tela respondia "o cliente está esperando demais?" e "algum worker morreu?". A
// pergunta seguinte — POR QUE está lento — já estava gravada em colunas que ninguém exibia:
// `turnos.canal`, `turnos.estagio`, `turnos.nos` (o caminho no grafo) e o histórico de `saude`.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Saude as SaudeDados, type RecorteTurnos } from "../lib/api";
import { dataHora, num, relativo } from "../lib/format";
import { Badge, Card, EmptyState, PageHeader, Skeleton, StatTile, Table, cx } from "../components/ui";
import { EsperaPorHora, FilasNoTempo, NosLentos } from "../components/chartsSaude";
import { Ic } from "../components/Icons";

const PERIODOS = [6, 24, 72];
const seg = (ms: number) => (ms >= 10_000 ? `${(ms / 1000).toFixed(0)}s` : `${(ms / 1000).toFixed(1)}s`);
const pct = (v: number) => `${v.toString().replace(".", ",")}%`;

/** Faixas de espera do cliente: acima de 10s ele percebe, acima de 30s ele desiste. */
const tomDaEspera = (ms: number): "bad" | "warn" | "good" => (ms > 30_000 ? "bad" : ms > 10_000 ? "warn" : "good");

type Motivo = { tom: "bad" | "warn"; texto: string };

/** Veredito único no topo, com os motivos que o produziram.
 *
 *  A regra é escrita aqui e mostrada junto: um selo "degradado" sem dizer o que o acendeu obriga
 *  quem olha a caçar o número pela tela inteira — e é assim que um alerta vira ruído ignorado.
 */
function diagnosticar(d: SaudeDados): { tom: "good" | "warn" | "bad"; motivos: Motivo[] } {
  const motivos: Motivo[] = [];
  const t = d.turnos;
  const mortos = d.servicos.filter((s) => !s.vivo);
  const fila = d.amostra ? Object.values(d.amostra.filas).reduce((a, b) => a + b, 0) : 0;

  if (mortos.length) motivos.push({ tom: "bad", texto: `${mortos.map((s) => s.servico).join(", ")} sem dar sinal — mensagens ficam na fila sem ser processadas` });
  if (t.total && t.p95_ms > 30_000) motivos.push({ tom: "bad", texto: `1 em cada 20 clientes espera mais de ${seg(t.p95_ms)}` });
  else if (t.total && t.p95_ms > 10_000) motivos.push({ tom: "warn", texto: `espera ruim (p95) em ${seg(t.p95_ms)} — acima de 10s o cliente percebe` });
  if (t.taxa_falha > 10) motivos.push({ tom: "bad", texto: `${pct(t.taxa_falha)} dos turnos terminaram mal` });
  else if (t.taxa_falha > 5) motivos.push({ tom: "warn", texto: `${pct(t.taxa_falha)} dos turnos terminaram mal` });
  if (fila > 50) motivos.push({ tom: "bad", texto: `${num(fila)} mensagens esperando na fila` });
  else if (fila > 10) motivos.push({ tom: "warn", texto: `${num(fila)} mensagens esperando na fila` });
  for (const p of d.provedores) {
    if (p.taxa_erro > 5) motivos.push({ tom: p.taxa_erro > 20 ? "bad" : "warn", texto: `${p.provedor} recusou ${pct(p.taxa_erro)} das chamadas` });
  }
  if (!d.amostra) motivos.push({ tom: "warn", texto: "nenhuma amostra de fila — o laço do scheduler não está gravando" });

  return { tom: motivos.some((m) => m.tom === "bad") ? "bad" : motivos.length ? "warn" : "good", motivos };
}

export function Saude() {
  const [horas, setHoras] = useState(24);
  const { data, isLoading, dataUpdatedAt } = useQuery({ queryKey: ["saude", horas], queryFn: () => api.saude(horas), refetchInterval: 15_000 });

  return (
    <div className="space-y-4">
      <PageHeader titulo="Saúde do sistema" descricao="Quanto o cliente espera, o que está na fila, quais serviços estão de pé — e onde o tempo está indo"
        acoes={
          <div className="flex items-center gap-3">
            {dataUpdatedAt > 0 && <span className="hidden text-xs text-ink-faint sm:inline">atualizado {relativo(new Date(dataUpdatedAt).toISOString())}</span>}
            <div className="inline-flex rounded-lg border border-line bg-surface p-0.5 text-xs">
              {PERIODOS.map((h) => (
                <button key={h} onClick={() => setHoras(h)}
                  className={cx("rounded-md px-2.5 py-1.5 font-medium", horas === h ? "bg-brand text-brand-ink" : "text-ink-muted hover:text-ink")}>
                  {h}h
                </button>
              ))}
            </div>
          </div>} />

      {isLoading || !data ? <Skeleton className="h-96" /> : <Conteudo d={data} />}
    </div>
  );
}

const ESTADO = {
  good: { rotulo: "Operando normalmente", classe: "border-good-line bg-good-soft text-good-strong", icone: Ic.check },
  warn: { rotulo: "Degradado", classe: "border-warn-line bg-warn-soft text-warn-strong", icone: Ic.info },
  bad: { rotulo: "Com problema", classe: "border-bad-line bg-bad-soft text-bad-strong", icone: Ic.info },
} as const;

function Conteudo({ d }: { d: SaudeDados }) {
  const t = d.turnos;
  const { tom, motivos } = diagnosticar(d);
  const estado = ESTADO[tom];
  const fila = d.amostra ? Object.values(d.amostra.filas).reduce((a, b) => a + b, 0) : 0;

  return (
    <div className="space-y-4">
      <div className={cx("rounded-xl border px-4 py-3 shadow-card", estado.classe)}>
        <div className="flex items-center gap-2">
          <estado.icone size={16} />
          <span className="text-sm font-semibold">{estado.rotulo}</span>
          <span className="text-xs opacity-80">· últimas {d.horas}h · {num(t.total)} turnos atendidos</span>
        </div>
        {motivos.length > 0 && (
          <ul className="mt-2 space-y-1 text-xs">
            {motivos.map((m) => (
              <li key={m.texto} className="flex items-start gap-1.5">
                <span className={cx("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                                    m.tom === "bad" ? "bg-[var(--status-bad)]" : "bg-[var(--status-warn)]")} />
                {m.texto}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <StatTile label="Turnos atendidos" valor={num(t.total)} icone="chat"
          ajuda="Cada mensagem de cliente que o agente processou até responder, nas últimas horas do período escolhido." />
        <StatTile label="Espera típica (p50)" valor={t.total ? seg(t.p50_ms) : "—"} icone="clock"
          ajuda="Metade dos clientes esperou menos que isso. Medido do recebimento da mensagem até a resposta sair — não é a latência de uma chamada de LLM isolada." />
        <StatTile label="Espera ruim (p95)" valor={t.total ? seg(t.p95_ms) : "—"} icone="clock" destaque={t.p95_ms > 30_000}
          ajuda="1 em cada 20 clientes esperou mais que isso. É o número que revela lentidão intermitente, que a média esconde." />
        <StatTile label="Turnos com falha" valor={pct(t.taxa_falha)} icone="shield" destaque={t.taxa_falha > 5}
          ajuda="Turnos que terminaram em erro, bloqueio de orçamento ou corte por vazão — qualquer coisa diferente de uma resposta normal." />
        <StatTile label="Na fila agora" valor={d.amostra ? num(fila) : "—"} icone="handoff" destaque={fila > 50}
          ajuda="Soma das mensagens esperando em todas as filas, na última amostra que o scheduler gravou (a cada 30s). Fila que não esvazia significa que o consumidor não está dando conta ou parou." />
      </div>

      <Card titulo="Espera por hora"
        acoes={<span className="text-xs text-ink-muted">barra clara = volume · barra escura = p95 · linha vermelha = falhas</span>}>
        {t.serie.length === 0
          ? <EmptyState titulo="Sem turnos no período" descricao="Nada foi atendido nas últimas horas — nem sempre é problema, mas vale conferir os serviços abaixo." />
          : <EsperaPorHora serie={t.serie} />}
      </Card>

      {/* A seção que responde "por quê". Canal e estágio primeiro porque recortam o mesmo número
          que o topo mostra; o grafo depois, porque exige a ressalva de presença vs. duração. */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card titulo="Espera por canal"
          acoes={<span className="text-xs text-ink-muted">p50 · p95</span>}>
          <Recorte linhas={d.por_canal} vazio="Sem turnos no período." />
        </Card>
        <Card titulo="Espera por estágio do lead"
          acoes={<span className="text-xs text-ink-muted">p50 · p95</span>}>
          <Recorte linhas={d.por_estagio} vazio="Sem turnos no período." />
        </Card>
      </div>

      <Card titulo="Onde o tempo está indo"
        acoes={d.nos_lentos.lentos > 0
          ? <span className="text-xs text-ink-muted">{num(d.nos_lentos.lentos)} turnos acima de {seg(d.nos_lentos.corte_ms)}</span>
          : undefined}>
        {d.nos_lentos.nos.length === 0
          ? <EmptyState titulo="Sem caminho registrado" descricao="Nenhum turno no período, ou os turnos não gravaram por quais nós passaram." />
          : (
            <>
              <NosLentos nos={d.nos_lentos.nos} />
              {/* A ressalva não é rodapé educado: sem ela, alguém lê "agendador 100%" como "o
                  agendador gastou o tempo" e vai otimizar o nó errado. */}
              <p className="mt-3 border-t border-line pt-3 text-xs text-ink-muted">
                Isto é <b>presença</b>, não duração: o turno grava por quais nós passou, não quanto tempo
                levou em cada um. Um nó que aparece muito mais nos turnos lentos do que nos demais é um
                <b> suspeito</b> — o corte é o p95 do próprio período ({seg(d.nos_lentos.corte_ms)}), e não um
                limiar fixo, senão num dia bom a lista ficaria sempre vazia.
              </p>
            </>
          )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2" titulo="Fila e conexões ao longo do tempo"
          acoes={d.amostra ? <span className="text-xs text-ink-muted">amostra de {relativo(d.amostra.em)}</span> : undefined}>
          {d.serie_filas.length === 0
            ? <EmptyState titulo="Sem amostras" descricao="O laço do scheduler é quem grava isto a cada 30s. Se está vazio, ele não está rodando." />
            : (
              <>
                <FilasNoTempo serie={d.serie_filas} />
                <p className="mt-2 text-xs text-ink-muted">
                  Pico por intervalo, não média: uma fila que encheu por dois minutos desaparece inteira numa
                  média horária. Fila estável e fila subindo são situações opostas com o mesmo número final.
                </p>
              </>
            )}
        </Card>

        <Card titulo="Serviços">
          <ul className="space-y-2 text-sm">
            {d.servicos.length === 0 && <li className="text-ink-muted">Nenhum serviço registrou batimento ainda.</li>}
            {d.servicos.map((s) => (
              <li key={s.servico} className="rounded-lg border border-line px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-2">
                    <span className={cx("h-2 w-2 rounded-full", s.vivo ? "bg-[var(--status-good)]" : "bg-[var(--status-bad)]")} />
                    <span className="font-medium">{s.servico}</span>
                  </span>
                  <span className="text-xs text-ink-muted" title={dataHora(s.em)}>
                    {s.vivo ? relativo(s.em) : `parado há ${Math.round(s.ha_segundos / 60)} min`}
                  </span>
                </div>
                {/* O batimento já carregava este JSON e a tela jogava fora. É o que cada worker
                    escolheu contar de si mesmo — não custa nada mostrar e às vezes é a pista. */}
                {Object.keys(s.detalhe ?? {}).length > 0 && (
                  <dl className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-ink-faint">
                    {Object.entries(s.detalhe).map(([k, v]) => (
                      <span key={k}><dt className="inline">{k}:</dt> <dd className="inline text-ink-muted">{String(v)}</dd></span>
                    ))}
                  </dl>
                )}
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card titulo="Provedores de LLM"
          acoes={<span className="text-xs text-ink-muted">disponibilidade, não custo</span>}>
          <Table colunas={["Provedor", { h: "Chamadas", cls: "text-right" }, { h: "Erro", cls: "text-right" }, { h: "p95", cls: "text-right" }]}
            vazio={d.provedores.length ? undefined : "Nenhuma chamada de LLM no período."}>
            {d.provedores.map((p) => (
              <tr key={p.provedor} className="border-t border-line">
                <td className="px-3 py-2 font-medium">{p.provedor}</td>
                <td className="px-3 py-2 text-right tabular-nums">{num(p.chamadas)}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {p.erros ? <Badge tom={p.taxa_erro > 20 ? "bad" : p.taxa_erro > 5 ? "warn" : "neutro"}>{pct(p.taxa_erro)}</Badge>
                           : <span className="text-ink-faint">—</span>}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{p.p95_ms ? seg(p.p95_ms) : "—"}</td>
              </tr>
            ))}
          </Table>
          <p className="mt-3 text-xs text-ink-muted">
            Quando a espera sobe sem a fila crescer, costuma ser aqui: o agente não está atrasado, está
            esperando o provedor.
          </p>
        </Card>

        <Card titulo="Como cada turno terminou">
          <Table colunas={["Resultado", { h: "Turnos", cls: "text-right" }]}
            vazio={t.total ? undefined : "Sem turnos no período."}>
            {Object.entries(t.por_resultado).map(([r, n]) => (
              <tr key={r} className="border-t border-line">
                <td className="px-3 py-2"><Badge tom={r === "ok" ? "good" : r === "handoff" ? "info" : "warn"}>{r}</Badge></td>
                <td className="px-3 py-2 text-right tabular-nums">{num(n)}</td>
              </tr>
            ))}
          </Table>
          {t.acima_de_30s > 0 && (
            <p className="mt-3 text-xs text-ink-muted">
              {num(t.acima_de_30s)} {t.acima_de_30s === 1 ? "turno passou" : "turnos passaram"} de 30s — pior caso do período: {seg(t.pior_ms)}.
            </p>
          )}
        </Card>
      </div>
    </div>
  );
}

/** Tabela de recorte (canal ou estágio) com barra de p95 relativa ao pior da própria tabela.
 *
 *  Relativa à tabela, e não a um máximo fixo: o que se quer enxergar aqui é a diferença ENTRE as
 *  linhas — qual canal está pior que o outro —, e uma escala absoluta achataria todas quando o
 *  sistema está bem. O número em segundos fica do lado para a barra não virar a única leitura. */
function Recorte({ linhas, vazio }: { linhas: RecorteTurnos[]; vazio: string }) {
  if (linhas.length === 0) return <p className="py-6 text-center text-sm text-ink-muted">{vazio}</p>;
  const teto = Math.max(...linhas.map((l) => l.p95_ms), 1);
  return (
    <ul className="space-y-3">
      {linhas.map((l) => (
        <li key={l.chave}>
          <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
            <span className="font-medium">{l.chave}</span>
            <span className="text-xs text-ink-muted tabular-nums">
              {num(l.turnos)} turnos · {seg(l.p50_ms)} <span className="text-ink-faint">p50</span> ·{" "}
              <b className={cx(tomDaEspera(l.p95_ms) === "bad" && "text-bad-strong",
                               tomDaEspera(l.p95_ms) === "warn" && "text-warn-strong")}>{seg(l.p95_ms)}</b>{" "}
              <span className="text-ink-faint">p95</span>
              {l.falhas > 0 && <> · <span className="text-bad-strong">{num(l.falhas)} com falha</span></>}
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
            <div className={cx("h-full rounded-full",
                               tomDaEspera(l.p95_ms) === "bad" ? "bg-[var(--status-bad)]"
                               : tomDaEspera(l.p95_ms) === "warn" ? "bg-[var(--status-warn)]" : "bg-brand")}
                 style={{ width: `${Math.max(2, (l.p95_ms / teto) * 100)}%` }} />
          </div>
        </li>
      ))}
    </ul>
  );
}
