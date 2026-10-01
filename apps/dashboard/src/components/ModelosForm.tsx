import { useEffect, useState } from "react";
import { api, type Comparacao, type Config, type LinhaModelo } from "../lib/api";
import { Badge, Button, Field, Input, Select, cx } from "./ui";
import { ComparacaoModelos, usd } from "./ComparacaoModelos";
import { Ic } from "./Icons";

/** Um papel por FUNÇÃO do agente (ADR-0016). A descrição e a herança vêm da API (`canais.llm.papeis`),
 *  que lê de `sdr_shared.papeis` — a mesma fonte do agente. Esta lista local só vale para uma API
 *  anterior aos papéis novos, para a tela não sumir com os três que ela já conhecia. */
const ROTULO: Record<string, string> = {
  conversa: "Conversa", roteamento: "Roteamento", extracao: "Extração do cartão",
  informacoes: "Informações (documentos)", analise: "Briefing e análise",
};
const PAPEIS_LOCAIS = [
  { papel: "conversa", herda: null, descricao: "O que o cliente lê: qualificador, consultor e agendador. Qualidade importa mais que preço." },
  { papel: "roteamento", herda: null, descricao: "Supervisor e leitura do cartão. Roda em toda mensagem — é onde o preço pesa." },
  { papel: "analise", herda: "conversa", descricao: "Resumo para o corretor. Roda fora da conversa, então latência não importa." },
];

const PROVIDERS = ["", "anthropic", "openai", "ollama", "openrouter"];
const OUTRO = "__outro__";

type Teste = { ok: boolean; latencia_ms: number; resposta?: string; erro?: string; tem_preco: boolean };

/** Trocar o modelo pelo painel vale no próximo turno do agente. Três travas de propósito:
 *  o combo só oferece modelo com preço cadastrado (custo zerado desliga o teto de orçamento), o
 *  backend recusa de novo no PUT, e o botão Testar faz uma chamada real antes de salvar — porque
 *  a lista vem do catálogo do servidor, mas ainda assim só o provedor sabe o que existe hoje. */
export function ModelosForm({ form, set, efetivo, catalogo: doServidor, papeis, openrouter }: {
  form: Record<string, unknown>;
  set: (k: string, v: unknown) => void;
  efetivo: Config["canais"]["llm"]["efetivo"];
  catalogo: Config["canais"]["llm"]["catalogo"];
  papeis?: Config["canais"]["llm"]["papeis"];
  openrouter?: Config["canais"]["llm"]["openrouter"];
}) {
  const niveis = papeis?.length ? papeis : PAPEIS_LOCAIS;
  // Modelos do OpenRouter sincronizados nesta tela entram no combo na hora. Recarregar a configuração
  // do servidor para isso apagaria o que foi mexido no formulário e ainda não foi salvo.
  const [sincronizados, setSincronizados] = useState<string[]>([]);
  const catalogo = sincronizados.length
    ? { ...doServidor, openrouter: [...new Set([...(doServidor?.openrouter ?? []), ...sincronizados])].sort() }
    : doServidor;
  const usaOpenRouter = niveis.some(({ papel }) => provedorEfetivo(papel) === "openrouter")
    || String(form.fallback_provider ?? "") === "openrouter";
  function provedorEfetivo(k: string) {
    return String(form[`${k}_provider`] ?? "") || efetivo?.[k]?.provider || "";
  }
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

  const provedorDe = provedorEfetivo;
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
        Um modelo por função do agente. Campo vazio herda do papel indicado ou usa o do ambiente
        (<code>.env</code>). Salvar vale no próximo turno — teste antes: um ID que não existe no provedor
        só apareceria como falha na conversa do cliente.
      </p>

      {usaOpenRouter && openrouter && !openrouter.zdr && (
        <p className="rounded-lg bg-warn-soft px-3 py-2 text-xs text-warn-strong">
          Retenção zero do OpenRouter está <b>desligada</b> (<code>SDR_OPENROUTER_ZDR=false</code>): ele pode
          rotear o texto do cliente para endpoints que guardam o dado. Só para bancada com dados sintéticos.
        </p>
      )}
      {usaOpenRouter && openrouter && !openrouter.configurado && (
        <p className="rounded-lg bg-bad-soft px-3 py-2 text-xs text-bad-strong">
          OpenRouter escolhido, mas <code>SDR_OPENROUTER_API_KEY</code> não está no ambiente da API — toda
          chamada vai falhar.
        </p>
      )}

      {niveis.map(({ papel: k, descricao: d, herda }) => {
        const r = ROTULO[k] ?? k;
        const atual = efetivo?.[k];
        const herdado = atual?.de && atual.de !== k;
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
                <p className="text-xs text-ink-muted">
                  {d}{herda && <> Vazio = usa o de <b>{ROTULO[herda] ?? herda}</b>.</>}
                </p>
              </div>
              {atual && <span className="shrink-0 whitespace-nowrap">{herdado
                ? <Badge>herda de {ROTULO[atual.de!] ?? atual.de}</Badge>
                : <Badge tom={atual.origem === "painel" ? "info" : undefined}>{atual.origem}</Badge>}</span>}
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
                  : provedorDe(k) === "openrouter"
                  ? <span>OpenRouter: ID no formato <code>fornecedor/modelo</code>. Ao salvar, o preço é buscado
                      no catálogo dele — ou sincronize abaixo para o modelo entrar na lista.</span>
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

      {PROVIDERS.includes("openrouter") && (
        <SincronizarOpenRouter onSincronizado={(ms) => setSincronizados((s) => [...new Set([...s, ...ms])])} />
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
          entre provedores, então basta nomear o outro. Com o OpenRouter como primário, prefira um
          reserva <b>direto</b> (anthropic ou openai): se ele cair, todo modelo que passa por ele cai junto.
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

/** Traz do catálogo do OpenRouter o preço dos modelos informados. É o que faz o modelo entrar no combo
 *  e passar na trava de preço — sem alguém copiar quatro números de uma página para um formulário,
 *  que é onde preço errado nasce. */
function SincronizarOpenRouter({ onSincronizado }: { onSincronizado: (modelos: string[]) => void }) {
  const [texto, setTexto] = useState("");
  const [estado, setEstado] = useState<"parado" | "carregando" | { gravados: string[]; faltando: string[] } | { erro: string }>("parado");
  const ids = texto.split(/[\s,]+/).map((x) => x.trim()).filter(Boolean);
  const sincronizar = async () => {
    setEstado("carregando");
    try {
      const r = await api.sincronizarOpenRouter(ids);
      const gravados = Object.keys(r.gravados);
      onSincronizado(gravados);
      setEstado({ gravados, faltando: r.nao_encontrados });
    } catch (e) {
      setEstado({ erro: (e as Error).message });
    }
  };
  return (
    <div className="rounded-xl border border-line p-4">
      <div className="mb-1 flex items-center gap-2">
        <Ic.coins size={15} className="text-ink-faint" />
        <h3 className="text-sm font-semibold">Modelos do OpenRouter</h3>
      </div>
      <p className="mb-3 text-xs text-ink-muted">
        Cole os IDs (<code>fornecedor/modelo</code>, separados por vírgula ou espaço) para trazer o preço
        publicado. Eles passam a aparecer no combo dos papéis com provedor <b>openrouter</b>.
      </p>
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <Field label="IDs">
            <Input value={texto} placeholder="google/gemini-3.5-flash-lite, mistralai/ministral-8b"
                   onChange={(e) => { setTexto(e.target.value); setEstado("parado"); }} />
          </Field>
        </div>
        <Button type="button" tamanho="sm" className="h-9" disabled={!ids.length || estado === "carregando"}
                onClick={sincronizar} icone={<Ic.bolt size={13} />}>
          {estado === "carregando" ? "Buscando…" : "Sincronizar preços"}
        </Button>
      </div>
      {typeof estado === "object" && "erro" in estado && (
        <p className="mt-2 rounded-lg bg-bad-soft px-3 py-2 text-xs text-bad-strong">Falhou: {estado.erro}</p>
      )}
      {typeof estado === "object" && "gravados" in estado && (
        <div className="mt-2 space-y-1 text-xs">
          {estado.gravados.length > 0 && (
            <p className="rounded-lg bg-good-soft px-3 py-2 text-good-strong">Preço gravado: {estado.gravados.join(", ")}</p>
          )}
          {estado.faltando.length > 0 && (
            <p className="rounded-lg bg-warn-soft px-3 py-2 text-warn-strong">
              O OpenRouter não conhece: {estado.faltando.join(", ")} — confira o ID na página do modelo.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
