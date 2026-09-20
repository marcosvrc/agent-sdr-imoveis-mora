import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, REGIOES, type Config } from "../lib/api";
import { REGIAO } from "../lib/format";
import { Badge, Button, Card, Field, Input, PageHeader, Select, Skeleton, Toggle, cx } from "../components/ui";
import { Ic } from "../components/Icons";
import { FollowupForm } from "../components/FollowupForm";
import { ModelosForm } from "../components/ModelosForm";

type Secao = "agente" | "followup" | "agenda" | "cobertura" | "handoff" | "modelos" | "canais";
const SECOES: { k: Secao; r: string; d: string }[] = [
  { k: "agente", r: "Persona do agente", d: "Nome, tom e limites da conversa" },
  { k: "followup", r: "Follow-up automático", d: "Cadência, ritmo e janela de horário" },
  { k: "agenda", r: "Agenda de visitas", d: "Slots oferecidos e duração" },
  { k: "cobertura", r: "Área de cobertura", d: "Regiões que a Mora oferece" },
  { k: "handoff", r: "Handoff para corretor", d: "Quando passar a conversa" },
  { k: "modelos", r: "Modelos de IA", d: "Qual modelo cada nível usa (ADR-0010)" },
  { k: "canais", r: "Canais e modelos", d: "Status da integração (somente leitura)" },
];

export function Configuracoes() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["config"], queryFn: api.config });
  const [secao, setSecao] = useState<Secao>("agente");
  const [form, setForm] = useState<Record<string, unknown>>({});
  const [salvo, setSalvo] = useState(false);
  useEffect(() => { if (data && secao !== "canais") setForm(data.config[secao] ?? {}); }, [data, secao]);
  const salvar = useMutation({ mutationFn: () => api.salvarConfig(secao, form), onSuccess: () => { qc.invalidateQueries({ queryKey: ["config"] }); qc.invalidateQueries({ queryKey: ["previa-followup"] }); setSalvo(true); setTimeout(() => setSalvo(false), 2000); } });
  const restaurar = useMutation({ mutationFn: () => api.restaurarConfig(secao), onSuccess: () => { qc.invalidateQueries({ queryKey: ["config"] }); qc.invalidateQueries({ queryKey: ["previa-followup"] }); } });
  const set = (k: string, v: unknown) => setForm((f) => ({ ...f, [k]: v }));
  const alterado = data && secao !== "canais" && JSON.stringify(form) !== JSON.stringify(data.config[secao]);
  const difDefault = data && secao !== "canais" && JSON.stringify(data.config[secao]) !== JSON.stringify(data.defaults[secao]);

  return (
    <div>
      <PageHeader titulo="Configurações" descricao="Parâmetros da Mora. O follow-up vale no próximo turno do agente; as demais seções ainda são declarativas." />
      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <Card semPadding>
          <ul className="divide-y divide-line">{SECOES.map((s) => <li key={s.k}><button onClick={() => setSecao(s.k)} className={cx("w-full px-4 py-3 text-left hover:bg-surface-2", secao === s.k && "bg-info-soft")}><p className="text-sm font-medium">{s.r}</p><p className="text-xs text-ink-muted">{s.d}</p></button></li>)}</ul>
        </Card>
        <Card titulo={SECOES.find((s) => s.k === secao)?.r} acoes={secao !== "canais" && <span className="flex items-center gap-2">{difDefault && <Badge tom="info">personalizado</Badge>}{salvo && <Badge tom="good" icone={<Ic.check size={10} />}>salvo</Badge>}</span>}>
          {isLoading || !data ? <Skeleton className="h-64" /> : secao === "canais" ? <Canais c={data.canais} /> : (
            <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); salvar.mutate(); }}>
              {secao === "agente" && <>
                <div className="grid gap-3 sm:grid-cols-2"><Field label="Nome do agente"><Input value={String(form.nome ?? "")} onChange={(e) => set("nome", e.target.value)} /></Field><Field label="Empresa"><Input value={String(form.empresa ?? "")} onChange={(e) => set("empresa", e.target.value)} /></Field></div>
                <Field label="Tom de voz"><Input value={String(form.tom ?? "")} onChange={(e) => set("tom", e.target.value)} placeholder="cordial e direto" /></Field>
                <div className="grid gap-3 sm:grid-cols-2"><Field label="Máximo de frases por mensagem"><Input type="number" min={1} max={6} value={Number(form.max_frases ?? 3)} onChange={(e) => set("max_frases", Number(e.target.value))} /></Field><Field label="Uso de emojis"><Select value={String(form.emojis ?? "raros")} onChange={(e) => set("emojis", e.target.value)}><option value="nunca">Nunca</option><option value="raros">Raros</option><option value="moderado">Moderado</option></Select></Field></div>
                <Toggle on={!!form.apresentar_como_assistente} onChange={(v) => set("apresentar_como_assistente", v)} label="Apresentar-se sempre como assistente virtual, nunca como pessoa" />
              </>}
              {secao === "followup" && <FollowupForm form={form} set={set} />}
              {secao === "agenda" && <>
                <Field label="Horários oferecidos" dica="Clique para ativar/desativar"><div className="flex flex-wrap gap-1.5">{[8, 9, 10, 11, 14, 15, 16, 17, 18].map((h) => { const slots = (form.slots as number[]) ?? []; const on = slots.includes(h); return <button type="button" key={h} onClick={() => set("slots", on ? slots.filter((x) => x !== h) : [...slots, h].sort((a, b) => a - b))} className={cx("rounded-full border px-3 py-1 text-xs font-medium", on ? "border-brand bg-brand text-brand-ink" : "border-line text-ink-muted hover:bg-surface-2")}>{h}h</button>; })}</div></Field>
                <div className="grid gap-3 sm:grid-cols-2"><Field label="Duração da visita (min)"><Input type="number" min={15} step={15} value={Number(form.duracao_min ?? 60)} onChange={(e) => set("duracao_min", Number(e.target.value))} /></Field><Field label="Antecedência oferecida (dias)"><Input type="number" min={1} max={14} value={Number(form.antecedencia_dias ?? 5)} onChange={(e) => set("antecedencia_dias", Number(e.target.value))} /></Field></div>
                <Toggle on={!!form.dias_uteis} onChange={(v) => set("dias_uteis", v)} label="Somente em dias úteis" />
              </>}
              {secao === "cobertura" && <>
                <Field label="Cidade"><Input value={String(form.cidade ?? "")} onChange={(e) => set("cidade", e.target.value)} /></Field>
                <Field label="Regiões atendidas" dica="Fora dessas regiões a Mora avisa o cliente e sugere a mais próxima"><div className="flex flex-wrap gap-1.5">{REGIOES.map((r) => { const rs = (form.regioes as string[]) ?? []; const on = rs.includes(r); return <button type="button" key={r} onClick={() => set("regioes", on ? rs.filter((x) => x !== r) : [...rs, r])} className={cx("rounded-full border px-3 py-1 text-xs font-medium", on ? "border-brand bg-brand text-brand-ink" : "border-line text-ink-muted hover:bg-surface-2")}>{REGIAO[r]}</button>; })}</div></Field>
              </>}
              {secao === "modelos" && <ModelosForm form={form} set={set} efetivo={data.canais.llm.efetivo} />}
              {secao === "handoff" && <>
                <Field label="Palavras que acionam o handoff" dica="Separadas por vírgula"><Input value={((form.palavras_gatilho as string[]) ?? []).join(", ")} onChange={(e) => set("palavras_gatilho", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} /></Field>
                <Toggle on={!!form.auto_quando_quente} onChange={(v) => set("auto_quando_quente", v)} label="Encaminhar automaticamente leads quentes ao corretor" />
              </>}
              <div className="flex items-center justify-between border-t border-line pt-4">
                <Button type="button" variante="fantasma" tamanho="sm" onClick={() => restaurar.mutate()} disabled={!difDefault || restaurar.isPending}>Restaurar padrão</Button>
                <div className="flex gap-2"><Button type="button" onClick={() => setForm(data.config[secao])} disabled={!alterado}>Descartar</Button><Button type="submit" variante="primario" disabled={!alterado || salvar.isPending}>Salvar alterações</Button></div>
              </div>
              {salvar.isError && <p className="rounded-lg bg-bad-soft px-3 py-2 text-xs text-bad-strong">{(salvar.error as Error).message}</p>}
            </form>
          )}
        </Card>
      </div>
    </div>
  );
}

function Canais({ c }: { c: Config["canais"] }) {
  const Linha = ({ icone, nome, ok, detalhe }: { icone: React.ReactNode; nome: string; ok: boolean; detalhe: string }) => (
    <li className="flex items-center gap-3 py-3"><span className="rounded-md bg-surface-2 p-2 text-ink-muted">{icone}</span><div className="flex-1"><p className="text-sm font-medium">{nome}</p><p className="text-xs text-ink-muted">{detalhe}</p></div>{ok ? <Badge tom="good" icone={<Ic.check size={10} />}>configurado</Badge> : <Badge tom="warn">pendente</Badge>}</li>
  );
  return (
    <ul className="divide-y divide-line">
      <Linha icone={<Ic.globe size={16} />} nome="Chat do site" ok={c.web.configurado} detalhe="WebSocket · widget na landing e nas páginas de imóvel" />
      <Linha icone={<Ic.telegram size={16} />} nome="Telegram" ok={c.telegram.configurado} detalhe={c.telegram.configurado ? `bot @${c.telegram.usuario ?? "?"}` : "preencha SDR_TELEGRAM_BOT_TOKEN no local/.env — criado na hora com o @BotFather, sem aprovação"} />
      <Linha icone={<Ic.spark size={16} />} nome={`LLM · ${c.llm.provider}`} ok detalhe={`conversa: ${c.llm.modelo_conversa} · roteamento: ${c.llm.modelo_roteamento}`} />
      <Linha icone={<Ic.bolt size={16} />} nome={`Embeddings · ${c.embeddings.provider}`} ok detalhe="RAG híbrido: filtros SQL + similaridade no pgvector" />
    </ul>
  );
}
