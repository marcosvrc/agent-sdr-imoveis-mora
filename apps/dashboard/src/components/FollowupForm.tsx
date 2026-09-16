// Cadência do follow-up. É a única seção de Configurações que o agente lê em tempo de execução,
// então a prévia à direita mostra exatamente quando cada tentativa cairia com o que está na tela.
import { useQuery } from "@tanstack/react-query";
import { api, type PreviaFollowup } from "../lib/api";
import { dataHora } from "../lib/format";
import { Badge, Button, Field, Input, Toggle, cx } from "../components/ui";
import { Ic } from "../components/Icons";

const TEMPERATURAS = [
  { k: "quente", r: "Quente", d: "cartão completo, urgência alta", icone: Ic.flame, tom: "text-bad-strong" },
  { k: "morno", r: "Morno", d: "conversa em andamento", icone: Ic.thermometer, tom: "text-warn" },
  { k: "frio", r: "Frio", d: "mal começou a conversar", icone: Ic.snowflake, tom: "text-info" },
] as const;

type Form = Record<string, unknown>;

/** 2880 → "2 d"; 90 → "1h30". Minutos crus não dizem nada a quem está configurando. */
export function humano(min: number): string {
  if (min < 60) return `${Math.round(min)} min`;
  if (min < 60 * 24) {
    const h = Math.floor(min / 60), m = Math.round(min % 60);
    return m ? `${h}h${String(m).padStart(2, "0")}` : `${h}h`;
  }
  const d = min / (60 * 24);
  return `${Number.isInteger(d) ? d : d.toFixed(1)} d`;
}

export function FollowupForm({ form, set }: { form: Form; set: (k: string, v: unknown) => void }) {
  const tempos = (form.tempos_min as number[]) ?? [];
  const ritmo = (form.ritmo as Record<string, number>) ?? {};
  const ativo = form.ativo !== false;

  const mudarTempo = (i: number, v: number) => set("tempos_min", tempos.map((t, j) => (j === i ? v : t)));
  const remover = (i: number) => set("tempos_min", tempos.filter((_, j) => j !== i));
  const adicionar = () => set("tempos_min", [...tempos, (tempos.at(-1) ?? 60) * 2]);

  return (
    <div className="space-y-5">
      <div className="rounded-lg border border-line bg-surface-2 px-3 py-2.5">
        <Toggle on={ativo} onChange={(v) => set("ativo", v)} label="Follow-up automático ligado" />
        <p className="mt-1 text-xs text-ink-muted">
          Desligado, a Mora só responde quando o cliente escreve — nenhum lead é retomado sozinho.
        </p>
      </div>

      <fieldset disabled={!ativo} className={cx("space-y-5", !ativo && "opacity-50")}>
        <Field label="Tentativas" dica="Tempo desde a última mensagem do cliente. A ordem é a sequência de tentativas.">
          <div className="space-y-2">
            {tempos.map((t, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className="w-16 text-xs text-ink-muted">{i + 1}ª</span>
                <Input type="number" min={5} value={t} onChange={(e) => mudarTempo(i, Number(e.target.value))} className="w-28" />
                <span className="text-xs text-ink-muted">minutos · {humano(t)}</span>
                {tempos.length > 1 && (
                  <button type="button" onClick={() => remover(i)} aria-label={`Remover a ${i + 1}ª tentativa`}
                    className="ml-auto rounded-md p-1.5 text-ink-muted hover:bg-bad-soft hover:text-bad-strong"><Ic.trash size={14} /></button>
                )}
              </div>
            ))}
            {tempos.length < 10 && (
              <Button type="button" tamanho="sm" icone={<Ic.plus size={14} />} onClick={adicionar}>Adicionar tentativa</Button>
            )}
          </div>
        </Field>

        <Field label="Ritmo por temperatura" dica="Multiplica o tempo acima. Menor que 1 volta mais cedo; maior que 1 espaça.">
          <div className="grid gap-3 sm:grid-cols-3">
            {TEMPERATURAS.map(({ k, r, d, icone: Icone, tom }) => (
              <div key={k} className="rounded-lg border border-line p-3">
                <div className="flex items-center gap-1.5 text-sm font-medium"><Icone size={14} className={tom} />{r}</div>
                <p className="mb-2 mt-0.5 text-xs text-ink-muted">{d}</p>
                <Input type="number" min={0.05} max={10} step={0.05} value={ritmo[k] ?? 1}
                  onChange={(e) => set("ritmo", { ...ritmo, [k]: Number(e.target.value) })} />
                <p className="mt-1 text-xs text-ink-muted">
                  1ª tentativa em {tempos[0] ? humano(tempos[0] * (ritmo[k] ?? 1)) : "—"}
                </p>
              </div>
            ))}
          </div>
        </Field>

        <Field label="Janela de envio" dica="Fora dela o follow-up espera a próxima abertura — ninguém recebe mensagem de madrugada.">
          <div className="grid gap-3 sm:grid-cols-2">
            <Input type="time" value={String(form.janela_inicio ?? "08:00")} onChange={(e) => set("janela_inicio", e.target.value)} />
            <Input type="time" value={String(form.janela_fim ?? "20:00")} onChange={(e) => set("janela_fim", e.target.value)} />
          </div>
        </Field>
        <Toggle on={!!form.dias_uteis} onChange={(v) => set("dias_uteis", v)} label="Somente em dias úteis" />
      </fieldset>

      <Previa ativo={ativo} />
    </div>
  );
}

/** Prévia do que está SALVO — o aviso deixa claro que alterações na tela ainda não contam. */
function Previa({ ativo }: { ativo: boolean }) {
  const { data } = useQuery({ queryKey: ["previa-followup"], queryFn: () => api.previaFollowup("morno") });
  const previa: PreviaFollowup["previa"] = data?.previa ?? [];
  return (
    <div className="rounded-xl border border-line bg-surface p-3">
      <div className="mb-2 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-ink-muted">
        <Ic.clock size={14} /> Como está valendo agora
        <Badge tom="neutro">lead morno</Badge>
      </div>
      {!ativo || previa.length === 0 ? (
        <p className="text-sm text-ink-muted">Nenhum follow-up seria enviado com a configuração salva.</p>
      ) : (
        <ol className="space-y-1.5">
          {previa.map((p) => (
            <li key={p.tentativa} className="flex items-center gap-2 text-sm">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-surface-2 text-xs font-medium">{p.tentativa}</span>
              <span className="text-ink-muted">daqui a {humano(p.minutos)}</span>
              <span className="ml-auto tabular-nums text-xs text-ink-muted">{dataHora(p.em)}</span>
            </li>
          ))}
        </ol>
      )}
      <p className="mt-2 text-xs text-ink-muted">Simulado a partir de agora, já respeitando a janela. Salve para atualizar.</p>
    </div>
  );
}
