import { useState } from "react";
import { api, type Config } from "../lib/api";
import { Badge, Button, Field, Input, Select, cx } from "./ui";
import { Ic } from "./Icons";

const NIVEIS = [
  { k: "conversa", r: "Conversa", d: "O que o cliente lê: qualificador, consultor e agendador. Qualidade importa mais que preço." },
  { k: "roteamento", r: "Roteamento e extração", d: "Supervisor e leitura do cartão. Roda em toda mensagem — é onde o preço pesa." },
  { k: "analise", r: "Briefing e análise", d: "Resumo para o corretor. Roda fora da conversa, então latência não importa. Vazio = usa o de conversa." },
] as const;

const PROVIDERS = ["", "bedrock", "anthropic", "openai", "ollama"];

type Teste = { ok: boolean; latencia_ms: number; resposta?: string; erro?: string; tem_preco: boolean };

/** Trocar o modelo pelo painel vale no próximo turno do agente. Duas travas de propósito:
 *  o backend recusa modelo sem preço cadastrado (custo zerado desliga o teto de orçamento), e o
 *  botão Testar faz uma chamada real antes de salvar — lista fixa envelhece, campo livre derruba. */
export function ModelosForm({ form, set, efetivo }: {
  form: Record<string, unknown>;
  set: (k: string, v: unknown) => void;
  efetivo: Config["canais"]["llm"]["efetivo"];
}) {
  const [testes, setTestes] = useState<Record<string, Teste | "carregando">>({});

  const testar = async (nivel: string) => {
    const modelo = String(form[nivel] ?? "") || efetivo?.[nivel]?.modelo || "";
    if (!modelo) return;
    setTestes((t) => ({ ...t, [nivel]: "carregando" }));
    try {
      const r = await api.testarModelo(modelo, String(form[`${nivel}_provider`] ?? "") || undefined);
      setTestes((t) => ({ ...t, [nivel]: r }));
    } catch (e) {
      setTestes((t) => ({ ...t, [nivel]: { ok: false, latencia_ms: 0, erro: (e as Error).message, tem_preco: false } }));
    }
  };

  return (
    <div className="space-y-5">
      <p className="rounded-lg bg-info-soft px-3 py-2 text-xs text-ink-muted">
        Campo vazio usa o modelo do ambiente (<code>.env</code>). Salvar vale no próximo turno do agente —
        teste antes: um ID que não existe no provedor só apareceria como falha na conversa do cliente.
      </p>

      {NIVEIS.map(({ k, r, d }) => {
        const atual = efetivo?.[k];
        const teste = testes[k];
        return (
          <div key={k} className="rounded-xl border border-line p-3">
            <div className="mb-2 flex items-start justify-between gap-2">
              <div>
                <p className="text-sm font-medium">{r}</p>
                <p className="text-xs text-ink-muted">{d}</p>
              </div>
              {atual && <Badge tom={atual.origem === "painel" ? "info" : undefined}>{atual.origem}</Badge>}
            </div>

            <div className="grid gap-3 sm:grid-cols-[1fr_150px_auto] sm:items-end">
              <Field label="Modelo" dica={atual ? `em uso agora: ${atual.modelo}` : undefined}>
                <Input value={String(form[k] ?? "")} placeholder={atual?.modelo ?? "usa o do ambiente"}
                       onChange={(e) => set(k, e.target.value)} />
              </Field>
              <Field label="Provedor">
                <Select value={String(form[`${k}_provider`] ?? "")} onChange={(e) => set(`${k}_provider`, e.target.value)}>
                  {PROVIDERS.map((p) => <option key={p} value={p}>{p || "usa o do ambiente"}</option>)}
                </Select>
              </Field>
              <Button type="button" tamanho="sm" onClick={() => testar(k)} disabled={teste === "carregando"}
                      icone={<Ic.bolt size={13} />}>
                {teste === "carregando" ? "Testando…" : "Testar"}
              </Button>
            </div>

            {teste && teste !== "carregando" && (
              <div className={cx("mt-2 rounded-lg px-3 py-2 text-xs",
                                 teste.ok ? "bg-good-soft text-good-strong" : "bg-bad-soft text-bad-strong")}>
                {teste.ok
                  ? <>Respondeu em {teste.latencia_ms}ms{teste.resposta ? ` — “${teste.resposta}”` : ""}</>
                  : <>Falhou: {teste.erro}</>}
                {!teste.tem_preco && (
                  <p className="mt-1 font-medium">
                    Sem preço cadastrado. O custo seria contabilizado como zero e o teto mensal em dólar
                    deixaria de valer — cadastre em Governança antes de salvar.
                  </p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
