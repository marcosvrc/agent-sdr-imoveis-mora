/** Peças da interface.
 *
 *  Três regras que atravessam tudo aqui, e que a seção 10 da especificação cobra:
 *
 *  • **estados loading / vazio / erro em toda consulta** — uma tela em branco enquanto carrega é
 *    indistinguível de uma tela em branco porque não há nada, e as duas pedem reações opostas;
 *  • **foco visível e navegação por teclado** — anel de foco em tudo que é interativo;
 *  • **nada de sucesso antes da resposta** — o botão fica ocupado até o servidor confirmar.
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { ErroApi } from "../lib/api";
import { TEMAS, aplicar, efetivo, observarSistema, salvar, temaSalvo, type Tema } from "../lib/tema";
import { Ic } from "./Icones";

export function cx(...v: (string | false | null | undefined)[]): string {
  return v.filter(Boolean).join(" ");
}

// Alfa embutido em `--anel-foco` de propósito: o Tailwind não aplica modificador de opacidade
// sobre uma cor que é `var()`, e `ring-acento/60` sairia sem anel nenhum — foco invisível é a
// regressão de acessibilidade mais fácil de não perceber, porque só aparece para quem usa teclado.
export const foco = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--anel-foco)] focus-visible:ring-offset-1 focus-visible:ring-offset-canvas";

export function Card({ titulo, acoes, children, semPadding }: {
  titulo?: ReactNode; acoes?: ReactNode; children: ReactNode; semPadding?: boolean;
}) {
  return (
    <section className="flex h-full min-w-0 flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-card">
      {(titulo || acoes) && (
        <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5">
          <h2 className="text-sm font-semibold text-ink">{titulo}</h2>
          {acoes}
        </header>
      )}
      <div className={cx("min-h-0 flex-1", !semPadding && "p-4")}>{children}</div>
    </section>
  );
}

// Sem modificador de opacidade nas bordas: a cor é `var()` e o Tailwind não compõe alfa sobre
// ela — as bordas coloridas simplesmente sumiriam. O fundo suave já separa a etiqueta do fundo.
const TONS = {
  neutro: "bg-surface2 text-inkSoft border-line",
  bom: "bg-bomSoft text-bom border-line",
  alerta: "bg-alertaSoft text-alerta border-line",
  ruim: "bg-ruimSoft text-ruim border-line",
  info: "bg-infoSoft text-info border-line",
} as const;

export function Etiqueta({ tom = "neutro", children }: { tom?: keyof typeof TONS; children: ReactNode }) {
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium", TONS[tom])}>
      {children}
    </span>
  );
}

export function Botao({ children, variante = "normal", ocupado, ...props }: {
  children: ReactNode; variante?: "normal" | "primario" | "perigo"; ocupado?: boolean;
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const estilo = {
    normal: "border-line bg-surface text-inkSoft hover:bg-surface2",
    primario: "border-transparent bg-marca text-marcaInk hover:opacity-90",
    perigo: "border-transparent bg-ruim text-canvas hover:opacity-90",
  }[variante];
  return (
    <button
      {...props}
      disabled={props.disabled || ocupado}
      // `aria-busy` e não só o texto: quem usa leitor de tela precisa saber que a ação está em
      // curso sem depender de enxergar o rótulo mudar.
      aria-busy={ocupado || undefined}
      className={cx("inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition",
        "disabled:cursor-not-allowed disabled:opacity-50", estilo, foco, props.className)}
    >
      {ocupado ? "Aguarde…" : children}
    </button>
  );
}

export function Carregando({ linhas = 3 }: { linhas?: number }) {
  return (
    <div className="space-y-2" role="status" aria-live="polite">
      <span className="sr-only">Carregando…</span>
      {Array.from({ length: linhas }).map((_, i) => (
        <div key={i} className="h-9 animate-pulse rounded-md bg-surface2" />
      ))}
    </div>
  );
}

export function Vazio({ titulo, descricao }: { titulo: string; descricao?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-line px-4 py-8 text-center">
      <p className="text-sm font-medium text-ink">{titulo}</p>
      {descricao && <p className="mx-auto mt-1 max-w-md text-xs text-inkMuted">{descricao}</p>}
    </div>
  );
}

/** Erro da API em português, com o código e o request_id à mão.
 *
 *  O `request_id` aparece porque é a única ponte entre o que a pessoa viu e o que está no log do
 *  servidor — sem ele, "deu erro" é tudo o que sobra para investigar. Stack trace nunca aparece
 *  aqui: a API não devolve, e o painel não inventa.
 */
export function Erro({ erro, aoTentar }: { erro: unknown; aoTentar?: () => void }) {
  const e = erro instanceof ErroApi ? erro : null;
  return (
    <div role="alert" className="rounded-lg border border-line bg-ruimSoft px-4 py-3">
      <p className="text-sm font-medium text-ruim">{e?.message ?? "Não foi possível carregar."}</p>
      {e && (
        <p className="mt-1 text-[11px] text-inkMuted">
          {e.code}
          {e.requestId && <> · requisição <code className="font-mono">{e.requestId.slice(0, 8)}</code></>}
        </p>
      )}
      {aoTentar && <Botao className="mt-2" onClick={aoTentar}>Tentar de novo</Botao>}
    </div>
  );
}

/** Faixa permanente exigida pela seção 10. Permanente mesmo: não fecha, não some ao rolar.
 *  Um CRM de laboratório confundido com o de verdade é como alguém liga para um "cliente". */
export function FaixaSintetica() {
  return (
    <div className="bg-alertaSoft px-4 py-1.5 text-center text-[11px] font-medium text-alerta">
      Ambiente de testes — dados sintéticos. Nenhum contato aqui é uma pessoa real.
    </div>
  );
}

export function Campo({ rotulo, children, dica }: { rotulo: string; children: ReactNode; dica?: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-inkSoft">{rotulo}</span>
      {children}
      {dica && <span className="mt-1 block text-[11px] text-inkFaint">{dica}</span>}
    </label>
  );
}

export const entradaCls = cx(
  "w-full rounded-md border border-lineForte bg-surface px-2.5 py-1.5 text-sm text-ink placeholder:text-inkFaint", foco);

/** Cabeçalho de página: onde estou, como volto, o que dá para fazer aqui.
 *
 *  A migalha não é enfeite de navegação — nas telas de detalhe, o CRM abre a partir de uma lista e
 *  a única saída era o botão voltar do navegador. Quem chega por um link colado não tinha saída
 *  nenhuma: ficava numa tela de cliente sem caminho para a lista de clientes.
 */
export function CabecalhoPagina({ titulo, descricao, voltar, acoes, contexto }: {
  titulo: string; descricao?: ReactNode; voltar?: { para: string; r: string }; acoes?: ReactNode; contexto?: ReactNode;
}) {
  return (
    <header className="mb-4">
      {voltar && (
        <nav aria-label="Trilha" className="mb-1">
          <Link to={voltar.para}
                className={cx("inline-flex items-center gap-1 rounded text-xs text-inkMuted hover:text-acento hover:underline", foco)}>
            <Ic.voltar size={13} /> {voltar.r}
          </Link>
        </nav>
      )}
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-ink">{titulo}</h1>
          {descricao && <p className="mt-0.5 text-sm text-inkMuted">{descricao}</p>}
          {contexto}
        </div>
        {acoes && <div className="flex shrink-0 flex-wrap items-center gap-2">{acoes}</div>}
      </div>
    </header>
  );
}

/** Cabeçalho de coluna que ordena, com o estado dito também em `aria-sort`.
 *
 *  A seta sozinha não informa quem navega por leitor de tela — e sem `aria-sort` a pessoa ouve
 *  "botão nome" três vezes seguidas sem saber qual está valendo.
 */
export function ColunaOrdenavel<K extends string>({ campo, atual, aoOrdenar, children, alinhar = "esquerda" }: {
  campo: K; atual: { campo: K; desc: boolean } | null; aoOrdenar: (campo: K) => void;
  children: ReactNode; alinhar?: "esquerda" | "direita";
}) {
  const ativa = atual?.campo === campo;
  const Seta = ativa && atual.desc ? Ic.descendo : Ic.subindo;
  return (
    <th scope="col" aria-sort={ativa ? (atual.desc ? "descending" : "ascending") : "none"}
        className={cx("px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-inkMuted",
                      alinhar === "direita" ? "text-right" : "text-left")}>
      <button type="button" onClick={() => aoOrdenar(campo)}
              className={cx("inline-flex items-center gap-1 rounded hover:text-ink", foco,
                            alinhar === "direita" && "flex-row-reverse")}>
        {children}
        <Seta size={12} className={ativa ? "text-acento" : "text-inkFaint opacity-0 group-hover:opacity-100"} />
      </button>
    </th>
  );
}

/** Paginação por cursor — que é o que a API oferece, e não é a mesma coisa que página numerada.
 *
 *  Não existe "página 7 de 12" aqui: o backend pagina por chave `(created_at, id)` e não devolve
 *  total. Inventar um contador exigiria um COUNT a cada consulta, e escrever "50+" fingindo saber
 *  seria pior — então a tela diz quantos está mostrando e oferece avançar e voltar. A pilha de
 *  cursores é o que torna o "anterior" possível: um cursor só aponta para a frente.
 */
export function usePaginaCursor() {
  const [pilha, setPilha] = useState<(string | null)[]>([null]);
  const cursor = pilha[pilha.length - 1];
  return {
    cursor: cursor ?? undefined,
    pagina: pilha.length,
    primeira: pilha.length === 1,
    avancar: (proximo: string) => setPilha((p) => [...p, proximo]),
    voltar: () => setPilha((p) => (p.length > 1 ? p.slice(0, -1) : p)),
    reiniciar: () => setPilha([null]),
  };
}

export function Paginacao({ mostrando, pagina, primeira, temProxima, aoAvancar, aoVoltar, rotulo = "itens" }: {
  mostrando: number; pagina: number; primeira: boolean; temProxima: boolean;
  aoAvancar: () => void; aoVoltar: () => void; rotulo?: string;
}) {
  if (primeira && !temProxima) {
    return <p className="px-4 py-2 text-xs text-inkFaint">{mostrando} {rotulo}</p>;
  }
  return (
    <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-2 text-xs">
      <p className="text-inkMuted">
        {mostrando} {rotulo} nesta página{pagina > 1 && <> · página {pagina}</>}
      </p>
      <div className="flex items-center gap-1.5">
        <Botao onClick={aoVoltar} disabled={primeira} aria-label="Página anterior">
          <Ic.anterior size={14} /> Anterior
        </Botao>
        <Botao onClick={aoAvancar} disabled={!temProxima} aria-label="Próxima página">
          Próxima <Ic.proximo size={14} />
        </Botao>
      </div>
    </div>
  );
}

/** Aviso de que a ordenação alcança só o que está carregado. Aparece só quando há página seguinte,
 *  porque é só aí que a ordenação da tela deixa de coincidir com a ordenação da base. */
export function AvisoOrdemParcial({ mostrar }: { mostrar: boolean }) {
  if (!mostrar) return null;
  return (
    <p className="border-t border-line bg-alertaSoft px-4 py-1.5 text-[11px] text-alerta">
      A ordenação vale para esta página. Há mais resultados adiante, e o servidor entrega sempre por
      data de criação — o primeiro daqui não é necessariamente o primeiro de todos.
    </p>
  );
}

/** Troca de tema: claro, escuro ou o que o sistema estiver usando.
 *
 *  Três opções e não um interruptor: "sistema" é o padrão de quem nunca escolheu e precisa
 *  continuar alcançável depois, senão quem trocou uma vez nunca mais volta a deixar o computador
 *  decidir. O ícone mostra o tema EM VIGOR; a marca de seleção mostra a ESCOLHA — com "sistema"
 *  às 20h, o botão é uma lua e o item marcado é Sistema.
 */
export function SeletorTema() {
  const [tema, setTema] = useState<Tema>(temaSalvo);
  const [aberto, setAberto] = useState(false);
  const [, redesenhar] = useState(0);
  const caixa = useRef<HTMLDivElement>(null);

  useEffect(() => { aplicar(tema); }, [tema]);
  useEffect(() => observarSistema(() => redesenhar((n) => n + 1)), []);
  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => { if (!caixa.current?.contains(e.target as Node)) setAberto(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setAberto(false); };
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", fora); document.removeEventListener("keydown", esc); };
  }, [aberto]);

  const ICONE: Record<Tema, keyof typeof Ic> = { claro: "sol", escuro: "lua", sistema: "sistema" };
  const IconeBotao = Ic[efetivo(tema) === "escuro" ? "lua" : "sol"];
  const escolha = TEMAS.find((t) => t.k === tema);

  return (
    <div className="relative" ref={caixa}>
      <button type="button" onClick={() => setAberto((a) => !a)} aria-expanded={aberto} aria-haspopup="menu"
              aria-label={`Tema: ${escolha?.r}. Trocar`} title={`Tema: ${escolha?.r}`}
              className={cx("rounded-md p-1.5 text-inkMuted hover:bg-surface2 hover:text-ink", foco)}>
        <IconeBotao size={16} />
      </button>
      {aberto && (
        <div role="menu" className="absolute right-0 top-full z-40 mt-1.5 w-56 overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-card">
          {TEMAS.map((t) => {
            const Icone = Ic[ICONE[t.k]];
            const marcado = t.k === tema;
            return (
              <button key={t.k} role="menuitemradio" aria-checked={marcado}
                      onClick={() => { setTema(t.k); salvar(t.k); setAberto(false); }}
                      className={cx("flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm hover:bg-surface2",
                                    marcado ? "text-ink" : "text-inkMuted", foco)}>
                <Icone size={15} className="shrink-0" />
                <span className="flex-1">{t.r}<span className="block text-[11px] text-inkFaint">{t.dica}</span></span>
                {marcado && <Ic.marcado size={15} className="shrink-0 text-acento" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
