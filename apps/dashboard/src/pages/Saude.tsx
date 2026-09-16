// Saúde do sistema (ADR-0011): observabilidade sem stack — tudo vem de três tabelas do Postgres
// que já roda. O que se quer responder aqui é "o cliente está esperando demais?" e "algum worker
// morreu?", que é exatamente o que não dava para ver quando o agente parou de responder.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Saude as SaudeDados } from "../lib/api";
import { dataHora, num, relativo } from "../lib/format";
import { Badge, Card, EmptyState, PageHeader, Skeleton, StatTile, Table, cx } from "../components/ui";
import { Ic } from "../components/Icons";

const PERIODOS = [6, 24, 72];
const seg = (ms: number) => (ms >= 10_000 ? `${(ms / 1000).toFixed(0)}s` : `${(ms / 1000).toFixed(1)}s`);

/** Faixas de espera do cliente: acima de 10s ele percebe, acima de 30s ele desiste. */
const tomDaEspera = (ms: number): "bad" | "warn" | "good" => (ms > 30_000 ? "bad" : ms > 10_000 ? "warn" : "good");

export function Saude() {
  const [horas, setHoras] = useState(24);
  const { data, isLoading } = useQuery({ queryKey: ["saude", horas], queryFn: () => api.saude(horas), refetchInterval: 15_000 });

  return (
    <div className="space-y-4">
      <PageHeader titulo="Saúde do sistema" descricao="Quanto o cliente espera por resposta, o que está na fila e quais serviços estão de pé"
        acoes={
          <div className="inline-flex rounded-lg border border-line bg-surface p-0.5 text-xs">
            {PERIODOS.map((h) => (
              <button key={h} onClick={() => setHoras(h)}
                className={cx("rounded-md px-2.5 py-1.5 font-medium", horas === h ? "bg-brand text-brand-ink" : "text-ink-muted hover:text-ink")}>
                {h}h
              </button>
            ))}
          </div>} />

      {isLoading || !data ? <Skeleton className="h-96" /> : <Conteudo d={data} />}
    </div>
  );
}

function Conteudo({ d }: { d: SaudeDados }) {
  const t = d.turnos;
  const mortos = d.servicos.filter((s) => !s.vivo);

  return (
    <div className="space-y-4">
      {mortos.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-bad-line bg-bad-soft px-4 py-3 text-sm text-bad-strong shadow-card">
          <Ic.info size={16} />
          <span className="font-medium">
            {mortos.length === 1 ? "Um serviço parou de dar sinal" : `${mortos.length} serviços pararam de dar sinal`}:
            {" "}{mortos.map((s) => s.servico).join(", ")}.
          </span>
          <span className="text-bad-strong">Enquanto isso, mensagens ficam na fila sem ser processadas.</span>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Turnos atendidos" valor={num(t.total)} icone="chat"
          ajuda="Cada mensagem de cliente que o agente processou até responder, nas últimas horas do período escolhido." />
        <StatTile label="Espera típica (p50)" valor={t.total ? seg(t.p50_ms) : "—"} icone="clock"
          ajuda="Metade dos clientes esperou menos que isso. Medido do recebimento da mensagem até a resposta sair — não é a latência de uma chamada de LLM isolada." />
        <StatTile label="Espera ruim (p95)" valor={t.total ? seg(t.p95_ms) : "—"} icone="clock" destaque={t.p95_ms > 30_000}
          ajuda="1 em cada 20 clientes esperou mais que isso. É o número que revela lentidão intermitente, que a média esconde." />
        <StatTile label="Turnos com falha" valor={`${t.taxa_falha.toString().replace(".", ",")}%`} icone="shield" destaque={t.taxa_falha > 5}
          ajuda="Turnos que terminaram em erro, bloqueio de orçamento ou corte por vazão — qualquer coisa diferente de uma resposta normal." />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2" titulo="Espera por hora"
          acoes={<span className="text-xs text-ink-muted">p95 · barra vermelha = turno com falha</span>}>
          {t.serie.length === 0
            ? <EmptyState titulo="Sem turnos no período" descricao="Nada foi atendido nas últimas horas — nem sempre é problema, mas vale conferir os serviços ao lado." />
            : <Serie serie={t.serie} />}
        </Card>

        <Card titulo="Serviços">
          <ul className="space-y-2 text-sm">
            {d.servicos.length === 0 && <li className="text-ink-muted">Nenhum serviço registrou batimento ainda.</li>}
            {d.servicos.map((s) => (
              <li key={s.servico} className="flex items-center justify-between gap-2 rounded-lg border border-line px-3 py-2">
                <span className="flex items-center gap-2">
                  <span className={cx("h-2 w-2 rounded-full", s.vivo ? "bg-[var(--status-good)]" : "bg-[var(--status-bad)]")} />
                  <span className="font-medium">{s.servico}</span>
                </span>
                <span className="text-xs text-ink-muted" title={dataHora(s.em)}>{s.vivo ? relativo(s.em) : `parado há ${Math.round(s.ha_segundos / 60)} min`}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card titulo="Filas"
          acoes={d.amostra ? <span className="text-xs text-ink-muted">amostra de {relativo(d.amostra.em)}</span> : undefined}>
          {!d.amostra
            ? <EmptyState titulo="Sem amostra" descricao="O laço do scheduler é quem grava isto a cada 30s. Se está vazio, ele não está rodando." />
            : (
              <>
                <ul className="space-y-2 text-sm">
                  {Object.keys(d.amostra.filas).length === 0 && <li className="text-ink-muted">Nenhuma fila com mensagens esperando.</li>}
                  {Object.entries(d.amostra.filas).map(([fila, n]) => (
                    <li key={fila} className="flex items-center justify-between gap-2">
                      <span className="text-ink-muted">{fila}</span>
                      <Badge tom={n > 50 ? "bad" : n > 10 ? "warn" : "neutro"}>{num(n)} esperando</Badge>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 border-t border-line pt-3 text-xs text-ink-muted">
                  {num(d.amostra.conexoes_db)} conexões abertas no banco
                </p>
              </>
            )}
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

/** Barras por hora sem biblioteca: altura = p95 relativo ao pior do período. */
function Serie({ serie }: { serie: SaudeDados["turnos"]["serie"] }) {
  const teto = Math.max(...serie.map((p) => p.p95_ms), 1);
  return (
    <div className="flex h-48 items-end gap-1 overflow-x-auto">
      {serie.map((p) => {
        const altura = Math.max(4, Math.round((p.p95_ms / teto) * 100));
        const tom = p.falhas > 0 ? "bg-[var(--status-bad)]" : tomDaEspera(p.p95_ms) === "warn" ? "bg-[var(--status-warn)]" : "bg-brand";
        return (
          <div key={p.hora} className="flex min-w-[14px] flex-1 flex-col items-center gap-1"
            title={`${dataHora(p.hora)} · ${p.turnos} turnos · p95 ${seg(p.p95_ms)}${p.falhas ? ` · ${p.falhas} com falha` : ""}`}>
            <div className={cx("w-full rounded-t", tom)} style={{ height: `${altura}%` }} />
            <span className="text-[10px] text-ink-muted">{new Date(p.hora).getHours()}h</span>
          </div>
        );
      })}
    </div>
  );
}
