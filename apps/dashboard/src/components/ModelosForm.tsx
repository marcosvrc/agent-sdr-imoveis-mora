import { useEffect, useState } from "react";
import { api, type Comparacao, type Config, type LinhaModelo } from "../lib/api";
import { Badge, Button, Field, Input, Select, cx } from "./ui";
import { ComparacaoModelos, usd } from "./ComparacaoModelos";
import { Ic } from "./Icons";

const NIVEIS = [
  { k: "conversa", r: "Conversa", d: "O que o cliente lê: qualificador, consultor e agendador. Qualidade importa mais que preço." },
  { k: "roteamento", r: "Roteamento e extração", d: "Supervisor e leitura do cartão. Roda em toda mensagem — é onde o preço pesa." },
  { k: "analise", r: "Briefing e análise", d: "Resumo para o corretor. Roda fora da conversa, então latência não importa. Vazio = usa o de conversa." },
] as const;

const PROVIDERS = ["", "anthropic", "openai", "ollama"];
const OUTRO = "__outro__";

type Teste = { ok: boolean; latencia_ms: number; resposta?: string; erro?: string; tem_preco: boolean };

/** Trocar o modelo pelo painel vale no próximo turno do agente. Três travas de propósito:
 *  o combo só oferece modelo com preço cadastrado (custo zerado desliga o teto de orçamento), o
 *  backend recusa de novo no PUT, e o botão Testar faz uma chamada real antes de salvar — porque
 *  a lista vem do catálogo do servidor, mas ainda assim só o provedor sabe o que existe hoje. */
export function ModelosForm({ form, set, efetivo, catalogo }: {
  form: Record<string, unknown>;
  set: (k: string, v: unknown) => void;
  efetivo: Config["canais"]["llm"]["efetivo"];
  catalogo: Config["canais"]["llm"]["catalogo"];
}) {
  const [testes, setTestes] = useState<Record<string, Teste | "carregando">>({});
  // Quem digitou um ID que não está no catálogo continua podendo: o combo ganha "outro…" em vez de
  // virar uma gaiola. Lista de servidor envelhece menos que lista de frontend, mas envelhece.
  const [livres, setLivres] = useState<Record<string, boolean>>({});
  // Um modelo trocado com o resultado verde do modelo ANTERIOR ainda na tela seria uma mentira
  // confortável: quem salvasse acharia que testou. Qualquer mexida no nível limpa o resultado.
  const limpar = (k: string) => setTestes(({ [k]: _, ...resto }) => resto);

  // Custo e latência por papel. Carrega em separado do resto da configuração porque é leitura de
  // uso (agregação sobre `uso_llm`) e não configuração: se falhar, a tela de modelos continua
  // funcionando sem os números, em vez de não abrir.
  const [comparacao, setComparacao] = useState<Comparacao | null>(null);
  const [modal, setModal] = useState<string | null>(null);
  useEffect(() => { api.compararModelos().then(setComparacao).catch(() => setComparacao(null)); }, []);

  const provedorDe = (k: string) => String(form[`${k}_provider`] ?? "") || efetivo?.[k]?.provider || "";
  /** Do mais barato para o mais caro, porque é a ordem em que a pergunta "qual eu escolho?" se
   *  responde. Só entram os modelos do provedor selecionado — o catálogo é quem diz quais existem;
   *  a comparação só reordena e enriquece. */
  const linhasDe = (k: string): LinhaModelo[] =>
    (comparacao?.papeis[k] ?? []).filter((l) => l.provedor === provedorDe(k));
  const opcoesDe = (k: string) => {
    const ordenadas = linhasDe(k).map((l) => l.modelo);
    const doCatalogo = catalogo?.[provedorDe(k)] ?? [];
    // O catálogo manda: um modelo que a comparação não conhece ainda pode ser salvo, e some da
    // lista se eu confiasse só na comparação.
    return [...ordenadas.filter((m) => doCatalogo.includes(m)),
            ...doCatalogo.filter((m) => !ordenadas.includes(m))];
  };
  const rotuloDe = (k: string, m: string) => {
    const l = linhasDe(k).find((x) => x.modelo === m);
    if (!l) return m;
    return `${m} — ${usd(l.custo.usd)}${l.custo.base === "uso" ? "" : " est."}`;
  };

  const trocarProvedor = (k: string, novo: string) => {
    set(`${k}_provider`, novo);
    limpar(k);
    const modelo = String(form[k] ?? "");
    const lista = catalogo?.[novo || efetivo?.[k]?.provider || ""] ?? [];
    // Modelo que não existe no provedor novo não pode ficar no campo: salvaria um 404 para o
    // próximo turno do cliente. Vazio é o estado seguro — o ambiente decide e a tradução por papel
    // (modelo_do_provedor) escolhe o equivalente lá.
    if (modelo && lista.length && !lista.includes(modelo)) {
      set(k, "");
      setLivres((l) => ({ ...l, [k]: false }));
    }
  };

  const escolherModelo = (k: string, v: string) => {
    limpar(k);
    if (v === OUTRO) { setLivres((l) => ({ ...l, [k]: true })); set(k, ""); return; }
    set(k, v);
  };

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
        const escolhido = String(form[k] ?? "");
        const opcoes = opcoesDe(k);
        // Sem catálogo para o provedor (Ollama, ou uma API velha que ainda não manda a lista) ou
        // pedido explícito de "outro…": campo livre. Um valor fora da lista também abre o campo
        // sozinho, senão a tela apagaria em silêncio o que já estava salvo.
        // Cair no campo livre CALADO seria o mesmo defeito de sempre: funciona, e ninguém descobre
        // por quê. Quando não é o Ollama, a linha de baixo diz que a lista não chegou.
        const campoLivre = livres[k] || opcoes.length === 0 || (!!escolhido && !opcoes.includes(escolhido));
        return (
          <div key={k} className="rounded-xl border border-line p-3">
            <div className="mb-3 flex items-start justify-between gap-2">
              <div>
                <p className="text-sm font-medium">{r}</p>
                <p className="text-xs text-ink-muted">{d}</p>
              </div>
              {atual && <Badge tom={atual.origem === "painel" ? "info" : undefined}>{atual.origem}</Badge>}
            </div>

            {/* Provedor primeiro: é ele que decide quais modelos existem, então perguntar o modelo
                antes seria pedir uma escolha que a próxima pergunta pode invalidar. Nenhuma coluna
                carrega dica aqui — as três têm a mesma altura e os campos alinham de fato. */}
            <div className="grid items-end gap-3 sm:grid-cols-[minmax(0,190px)_minmax(0,1fr)_auto]">
              <Field label="Provedor">
                <Select value={String(form[`${k}_provider`] ?? "")}
                        onChange={(e) => trocarProvedor(k, e.target.value)}>
                  {PROVIDERS.map((p) => <option key={p} value={p}>{p || "usa o do ambiente"}</option>)}
                </Select>
              </Field>

              <Field label="Modelo">
                <div className="flex items-center gap-1.5">
                  {campoLivre ? (
                    <Input value={escolhido} placeholder={atual?.modelo ?? "usa o do ambiente"}
                           onChange={(e) => { limpar(k); set(k, e.target.value); }} />
                  ) : (
                    <Select value={escolhido} onChange={(e) => escolherModelo(k, e.target.value)}>
                      <option value="">usa o do ambiente{atual ? ` (${atual.modelo})` : ""}</option>
                      {opcoes.map((m) => <option key={m} value={m}>{rotuloDe(k, m)}</option>)}
                      <option value={OUTRO}>outro — digitar o ID…</option>
                    </Select>
                  )}
                  {/* O combo responde "qual é mais barato"; o modal responde "por quê" — preço de
                      entrada e saída separados, latência medida aqui e o papel que o projeto
                      recomenda. Cabe do lado, e não no lugar, porque a escolha rápida é a comum. */}
                  {linhasDe(k).length > 0 && (
                    <Button type="button" variante="fantasma" tamanho="sm" className="h-9 shrink-0 px-2"
                            title="Comparar custo e velocidade dos modelos deste provedor"
                            aria-label="Comparar modelos" onClick={() => setModal(k)}>
                      <Ic.coins size={15} />
                    </Button>
                  )}
                </div>
              </Field>

              <Button type="button" tamanho="sm" className="h-9" onClick={() => testar(k)}
                      disabled={teste === "carregando"} icone={<Ic.bolt size={13} />}>
                {teste === "carregando" ? "Testando…" : "Testar"}
              </Button>
            </div>

            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-ink-faint">
              {atual && <span>em uso agora: {atual.modelo} · {atual.provider}</span>}
              {campoLivre && opcoes.length > 0 && (
                <button type="button" className="underline hover:text-ink-muted"
                        onClick={() => { setLivres((l) => ({ ...l, [k]: false })); limpar(k); set(k, ""); }}>
                  voltar para a lista
                </button>
              )}
              {campoLivre && opcoes.length === 0 && (
                provedorDe(k) === "ollama"
                  ? <span>Ollama não tem lista: vale o que a máquina baixou com <code>ollama pull</code>.</span>
                  : <span className="text-warn-strong">
                      A API não mandou a lista de modelos de <b>{provedorDe(k) || "—"}</b> — provavelmente
                      está rodando uma versão anterior a esta tela. Campo livre até ela subir de novo.
                    </span>
              )}
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

      {modal && (
        <ComparacaoModelos aberto onFechar={() => setModal(null)} papel={modal} linhas={linhasDe(modal)}
                           atual={String(form[modal] ?? "") || efetivo?.[modal]?.modelo || ""}
                           onEscolher={(m) => escolherModelo(modal, m)} />
      )}

      {/* O reserva é decisão de operação — quem assume quando o provedor primário cai — e estava
          só no .env, exigindo recriar container para mudar. Aqui vale no próximo turno. */}
      <div className="rounded-xl border border-line p-4">
        <div className="mb-1 flex items-center gap-2">
          <Ic.shield size={15} className="text-ink-faint" />
          <h3 className="text-sm font-semibold">Provedor de reserva</h3>
        </div>
        <p className="mb-3 text-xs text-ink-muted">
          Assume quando o primário falha — indisponibilidade, timeout ou cota. Sem reserva, cada turno
          vira mensagem de desculpa e encaminhamento ao corretor. O ID do modelo é traduzido sozinho
          entre provedores, então basta nomear o outro.
        </p>
        <Field label="Quem assume a queda">
          <Select value={String(form.fallback_provider ?? "")}
                  onChange={(e) => set("fallback_provider", e.target.value)}>
            <option value="">usa o do ambiente (.env)</option>
            {PROVIDERS.filter(Boolean).map((p) => <option key={p} value={p}>{p}</option>)}
            <option value="nenhum">nenhum — sem reserva</option>
          </Select>
        </Field>
        {String(form.fallback_provider ?? "") === "nenhum" && (
          <p className="mt-2 rounded-lg bg-warn-soft px-3 py-2 text-xs text-warn-strong">
            Sem reserva: se o provedor cair, o cliente recebe uma desculpa e o corretor recebe o lead.
          </p>
        )}
      </div>
    </div>
  );
}
