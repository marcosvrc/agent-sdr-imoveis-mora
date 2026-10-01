import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { conectar, type EventoCanal, type RespostaAgente } from "../lib/ws";
import { track } from "../lib/tracking";
import { brl, TIPOS, preposicaoTipo } from "../lib/api";
import type { ImovelResumo } from "../store/chat";
import { MensagemBolha, Digitando } from "./MensagemBolha";
import { CardImovelChat } from "./CardImovelChat";
import { BotoesOpcoes } from "./BotoesOpcoes";
import { CardVisita, type Visita } from "./CardVisita";
import { MoraAvatar } from "../components/MoraAvatar";
import { NOVA_CONVERSA_A_CADA_VISITA, descartarSessao } from "../lib/session";
import { carregarHistorico } from "../lib/historico";
import { TELEGRAM_USUARIO as USUARIO_TELEGRAM } from "../lib/imobiliaria";

/** Uma bolha. `reenviar` existe quando o envio falhou: o botão "Tentar de novo" manda a mesma coisa. */
type Bolha = {
  de: "lead" | "Mora"; texto: string; em: string; r?: RespostaAgente; aviso?: boolean;
  reenviar?: { texto: string; rotulo: string; botao: boolean };
};

/** Nenhuma espera é infinita: avisamos que está demorando e, passando disso, oferecemos um humano.
 *  RESGATE_MS folgado de propósito: a busca de imóveis chama embeddings (Ollama, no perfil local) e,
 *  rodando em CPU comum, um turno completo pode passar de 40-50s sem nada estar quebrado — visto ao
 *  vivo em teste local. Baixo demais aqui só engana o cliente, oferecendo humano bem no meio de uma
 *  resposta que já estava a caminho. */
const AVISO_MS = 10_000;
const RESGATE_MS = 60_000;
const LIMITE_TEXTO = 1000;
/** Horário aparece no fim de cada sequência do mesmo autor, ou quando passa este intervalo. */
const PAUSA_COM_HORARIO_MS = 5 * 60_000;

const agora = () => new Date().toISOString();
const horaCurta = (iso: string) =>
  new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

// Frase que menciona o imóvel de onde o cliente veio — o agente recebe o mesmo dado por trás
// (handler.py lê `imovel_origem`), isto é só a bolha de saudação já nascer falando daquilo,
// em vez de o cliente ter que repetir o que já deixou claro ao clicar "conversar sobre este imóvel".
function saudacaoDoImovel(im: ImovelResumo): string {
  const tipo = (TIPOS[im.tipo] ?? im.tipo).toLowerCase();
  const preco = brl(im.preco) + (im.operacao === "aluguel" ? "/mês" : "");
  return `Oi! Sou a Mora, assistente virtual da Vértice Imóveis. Vi que você está de olho ${preposicaoTipo(im.tipo)} ${tipo} em ${im.bairro}, por ${preco}. Quer que eu conte mais sobre ele, compare com opções parecidas ou já agende uma visita?`;
}

// Atalhos da primeira mensagem: o cliente reconhece o que quer em vez de ter que formular
// (Nielsen 6). Quem prefere escrever continua com o campo de texto logo abaixo.
const ATALHOS_INICIAIS = ["Comprar", "Alugar", "Investir"];
const ATALHOS_DO_IMOVEL = ["Me conte mais sobre ele", "Ver opções parecidas", "Agendar visita"];

/** Foco automático só onde há teclado físico: no celular ele abriria o teclado por cima da conversa. */
const temTecladoFisico = () => typeof window !== "undefined" && window.matchMedia?.("(pointer: fine)").matches;

export function ChatWidget({ imovelOrigem, imovelResumo, altura = "h-[70vh]", aoFechar, expandido, aoExpandir }: { imovelOrigem?: string; imovelResumo?: ImovelResumo; altura?: string; aoFechar?: () => void; expandido?: boolean; aoExpandir?: () => void }) {
  const saudacao = (): Bolha => ({
    de: "Mora", em: agora(),
    texto: imovelResumo ? saudacaoDoImovel(imovelResumo) : "Olá! Eu sou a Mora, assistente virtual da Vértice Imóveis. Estou aqui para entender o que você procura e ajudar a encontrar o imóvel ideal para o seu próximo momento.",
  });
  const [bolhas, setBolhas] = useState<Bolha[]>(() => [saudacao()]);
  // Muda a cada "Nova conversa" (modo de teste): derruba a conexão e abre outra com sessão nova.
  const [geracao, setGeracao] = useState(0);
  const [texto, setTexto] = useState("");
  const [online, setOnline] = useState(false);
  const [digitando, setDigitando] = useState(false);
  const [demorando, setDemorando] = useState(false);
  const [resgate, setResgate] = useState(false);
  const [novas, setNovas] = useState(false);              // chegou mensagem enquanto o cliente lia lá em cima
  const conn = useRef<ReturnType<typeof conectar>>();
  const lista = useRef<HTMLDivElement>(null);
  const campo = useRef<HTMLTextAreaElement>(null);
  const pertoDoFim = useRef(true);
  const timers = useRef<number[]>([]);
  const enviados = useRef(new Map<string, { texto: string; rotulo: string; botao: boolean }>());
  const ultimoResumoAnunciado = useRef(imovelResumo?.id);

  const limparTimers = useCallback(() => { timers.current.forEach(clearTimeout); timers.current = []; }, []);
  const pararEspera = useCallback(() => { limparTimers(); setDigitando(false); setDemorando(false); setResgate(false); }, [limparTimers]);

  // Se o cliente já tinha o chat aberto e clica em "conversar sobre este imóvel" em OUTRA ficha,
  // o widget não remonta (mantém a conversa) — então avisamos a mudança de contexto numa nova bolha.
  useEffect(() => {
    if (!imovelResumo || imovelResumo.id === ultimoResumoAnunciado.current) return;
    ultimoResumoAnunciado.current = imovelResumo.id;
    setBolhas((b) => [...b, { de: "Mora", em: agora(), texto: `Também vi que você deu uma olhada ${preposicaoTipo(imovelResumo.tipo)} ${(TIPOS[imovelResumo.tipo] ?? imovelResumo.tipo).toLowerCase()} em ${imovelResumo.bairro}, por ${brl(imovelResumo.preco)}${imovelResumo.operacao === "aluguel" ? "/mês" : ""}. Quer falar sobre esse também?` }]);
  }, [imovelResumo]);

  // Recarregou a página no meio da conversa: redesenha o que já foi dito (Nielsen 1 e 6). Só
  // substitui a tela se nada novo chegou enquanto o histórico carregava.
  useEffect(() => {
    let vivo = true;
    carregarHistorico().then((h) => {
      if (!vivo || !h.length) return;
      setBolhas((b) => (b.length === 1 ? [b[0], ...h] : b));
    });
    return () => { vivo = false; };
  }, [geracao]);

  useEffect(() => {
    track("opened_chat", { imovel_id: imovelOrigem });
    conn.current = conectar(
      (r) => {
        pararEspera();
        setBolhas((b) => [...b, { de: "Mora", texto: r.texto, r, em: agora() }]);
        if (temTecladoFisico()) campo.current?.focus();
      },
      (s) => setOnline(s === "on"),
      (e: EventoCanal) => {
        if (e.evento === "falha_envio") {
          pararEspera();
          const original = e.ref ? enviados.current.get(e.ref) : undefined;
          setBolhas((b) => [...b, {
            de: "Mora", aviso: true, em: agora(), reenviar: original,
            texto: e.texto ?? "Não consegui registrar sua mensagem. Pode tentar de novo?",
          }]);
        }
      },
    );
    if (temTecladoFisico()) campo.current?.focus();
    return () => { conn.current?.fechar(); limparTimers(); };
  }, [imovelOrigem, pararEspera, limparTimers, geracao]);

  const novaConversa = () => {
    conn.current?.fechar();
    descartarSessao();
    pararEspera();
    setBolhas([saudacao()]);
    setGeracao((g) => g + 1);
  };

  // Rolagem que respeita quem está lendo: só desce sozinha se o cliente já estava no fim (ou se
  // foi ele quem acabou de escrever). Lendo uma mensagem antiga, ele recebe um aviso em vez de
  // ser arrastado para baixo no meio da frase.
  const aoRolar = () => {
    const el = lista.current;
    if (!el) return;
    pertoDoFim.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    if (pertoDoFim.current) setNovas(false);
  };
  const descer = (suave = true) => {
    const el = lista.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: suave ? "smooth" : "auto" });
    setNovas(false);
  };
  useLayoutEffect(() => {
    const ultimaDoCliente = bolhas[bolhas.length - 1]?.de === "lead";
    if (pertoDoFim.current || ultimaDoCliente) descer();
    else setNovas(true);
  }, [bolhas]);
  useEffect(() => { if (pertoDoFim.current) descer(); }, [digitando, demorando, resgate]);

  // Campo de texto que cresce com a mensagem (até ~5 linhas) e volta ao tamanho de uma linha.
  useLayoutEffect(() => {
    const el = campo.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [texto]);

  const enviar = (t: string, rotulo = t, botao = false) => {
    if (!t.trim()) return;
    setBolhas((b) => [...b, { de: "lead", texto: rotulo, em: agora() }]);
    setTexto("");
    limparTimers();
    setDigitando(true); setDemorando(false); setResgate(false);
    // botao=true: o canal marca a mensagem como TipoMensagem.BOTAO (mesmo contrato do Telegram).
    // saudacao_exibida: o widget sempre abre com a bolha de boas-vindas da Mora; sem este aviso, a
    // resposta ao primeiro "oi" se apresentava de novo ("Oi! Eu sou a Mora…") logo abaixo dela.
    const ref = conn.current?.enviar(t, { saudacao_exibida: true, ...(imovelOrigem ? { imovel_origem: imovelOrigem } : {}), ...(botao ? { botao: true } : {}) });
    if (ref) enviados.current.set(ref, { texto: t, rotulo, botao });
    timers.current.push(window.setTimeout(() => setDemorando(true), AVISO_MS));
    timers.current.push(window.setTimeout(() => { setDemorando(false); setResgate(true); }, RESGATE_MS));
  };

  // Enter envia; Shift+Enter quebra a linha. Durante a composição de acentos (IME), Enter é do teclado.
  const aoTeclar = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      enviar(texto);
    }
  };

  const ultima = bolhas[bolhas.length - 1];
  const inicio = bolhas.length === 1 && !digitando;
  const opcoes = inicio ? (imovelResumo ? ATALHOS_DO_IMOVEL : ATALHOS_INICIAIS)
    : ultima.de === "Mora" && !digitando && !resgate ? ultima.r?.opcoes ?? [] : [];
  const restantes = LIMITE_TEXTO - texto.length;

  return (
    <div className={`flex ${altura} flex-col overflow-hidden rounded-2xl bg-white shadow ring-1 ring-slate-200`}>
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5 text-sm">
        <span className="relative" aria-hidden>
          <MoraAvatar tamanho={32} />
          <span className={`absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full ring-2 ring-white ${online ? "bg-estado-ok" : "bg-estado-alerta"}`} />
        </span>
        <span className="flex min-w-0 flex-col leading-tight">
          <span className="font-medium">Mora</span>
          {/* Quem é e em que estado está, na mesma linha de leitura. O texto acompanha a bolinha:
              cor sozinha não transmite estado (WCAG 1.4.1). */}
          <span className="text-xs text-ink-muted">
            assistente virtual ·{" "}
            <span className="sr-only">Estado da conexão: </span>
            <span className={online ? "text-estado-ok" : "text-estado-alerta"}>{online ? "online" : "reconectando…"}</span>
          </span>
        </span>
        {NOVA_CONVERSA_A_CADA_VISITA && (
          <button type="button" onClick={novaConversa} title="Modo de teste: começa um atendimento do zero, como um cliente novo"
                  className="rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 hover:bg-amber-100">
            Nova conversa
          </button>
        )}
        <span className="ml-auto flex items-center gap-1">
          {aoExpandir && (
            <button onClick={aoExpandir} aria-label={expandido ? "Reduzir o chat" : "Expandir o chat"} aria-pressed={expandido}
                    title={expandido ? "Reduzir" : "Expandir"}
                    className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100 hover:text-slate-700">
              {expandido
                ? <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7" /></svg>
                : <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" /></svg>}
            </button>
          )}
          {aoFechar && (
            <button onClick={aoFechar} aria-label="Fechar chat" title="Fechar (a conversa continua salva)"
                    className="grid h-8 w-8 place-items-center rounded-full text-slate-500 hover:bg-slate-100 hover:text-slate-700">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
            </button>
          )}
        </span>
      </div>

      <div className="relative flex-1 overflow-hidden">
        {/* role=log + aria-live: sem isto, quem usa leitor de tela não fica sabendo que a
            Mora respondeu — a bolha aparece na tela e não é anunciada em lugar nenhum. */}
        <div ref={lista} onScroll={aoRolar} role="log" aria-live="polite" aria-relevant="additions text"
             aria-label="Mensagens da conversa" className="h-full space-y-1.5 overflow-y-auto bg-ground p-4">
          {bolhas.map((b, i) => {
            const prox = bolhas[i + 1];
            const fimDoGrupo = !prox || prox.de !== b.de
              || new Date(prox.em).getTime() - new Date(b.em).getTime() > PAUSA_COM_HORARIO_MS;
            const novoGrupo = i > 0 && bolhas[i - 1].de !== b.de;
            return (
              <div key={i} className={`space-y-2 ${novoGrupo ? "pt-2" : ""}`}>
                {b.r?.imoveis?.length ? (
                  <div className="space-y-2 pl-8">{b.r.imoveis.map((c) => <CardImovelChat key={c.id} card={c} />)}</div>
                ) : null}
                <MensagemBolha de={b.de} texto={b.texto} aviso={b.aviso}
                               avatar={b.de === "Mora" && fimDoGrupo} hora={fimDoGrupo ? horaCurta(b.em) : undefined}>
                  {b.reenviar && i === bolhas.length - 1 && (
                    <button onClick={() => enviar(b.reenviar!.texto, b.reenviar!.rotulo, b.reenviar!.botao)}
                            className="mt-1.5 rounded-full border border-amber-400 px-3 py-1 text-xs font-medium text-amber-900 hover:bg-amber-100">
                      Tentar de novo
                    </button>
                  )}
                </MensagemBolha>
                {b.r?.acao === "agendar" && b.r.dados?.visita ? <div className="pl-8"><CardVisita visita={b.r.dados.visita as Visita} /></div> : null}
              </div>
            );
          })}
          {digitando && !demorando && !resgate && <div className="pt-2"><Digitando /></div>}
          {demorando && (
            <div className="flex items-center gap-2 pt-2 pl-8 text-sm text-slate-600" role="status">
              <span className="flex gap-0.5" aria-hidden>{[0, 1, 2].map((i) => <span key={i} className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400 motion-reduce:animate-none" style={{ animationDelay: `${i * 150}ms` }} />)}</span>
              Ainda estou procurando as melhores opções para você…
            </div>
          )}
          {resgate && (
            <div className="ml-8 rounded-2xl bg-white p-3 text-sm shadow-sm ring-1 ring-amber-200">
              <p className="text-slate-700">Desculpe a demora — estou com dificuldade para responder agora. Um corretor pode te atender na hora:</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {/* Telegram só aceita um payload curto em /start (sem espaço/pontuação) — "humano" já
                    basta: é uma das palavras-gatilho de handoff (ver DEFAULTS.handoff em config.py). */}
                <a href={`https://t.me/${USUARIO_TELEGRAM}?start=humano`}
                   target="_blank" rel="noreferrer" onClick={() => track("clicked_telegram", {})}
                   className="rounded-full bg-sky-500 px-3 py-1.5 text-xs font-medium text-white">Falar no Telegram</a>
                <button onClick={() => enviar("Quero falar com um corretor")} className="rounded-full border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700">Tentar de novo aqui</button>
              </div>
            </div>
          )}
        </div>
        {novas && (
          <button onClick={() => descer()} className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-brand px-3 py-1.5 text-xs font-medium text-white shadow-soft">
            Nova mensagem ↓
          </button>
        )}
      </div>

      {opcoes.length ? <BotoesOpcoes opcoes={opcoes} onEscolher={(id, rotulo) => enviar(id, rotulo, true)} /> : null}
      <form className="border-t border-line p-2" onSubmit={(e) => { e.preventDefault(); enviar(texto); }}>
        <div className="flex items-end gap-2">
          <label htmlFor="chat-mensagem" className="sr-only">Escreva sua mensagem para a Mora</label>
          <textarea id="chat-mensagem" ref={campo} rows={1} maxLength={LIMITE_TEXTO}
                    className="min-h-[2.75rem] flex-1 resize-none rounded-md border border-line-forte px-3 py-2.5 text-sm leading-snug text-ink placeholder:text-ink-soft focus:border-brand-accent focus:outline-none"
                    autoComplete="off" aria-describedby="chat-dica"
                    placeholder={online ? "Escreva sua mensagem…" : "Sem conexão — enviaremos ao reconectar"}
                    value={texto} onChange={(e) => setTexto(e.target.value)} onKeyDown={aoTeclar} />
          <button className="h-11 rounded-md bg-brand px-4 text-sm font-semibold text-white transition hover:bg-brand-accentDark disabled:cursor-not-allowed disabled:opacity-40"
                  type="submit" disabled={!texto.trim()}>Enviar</button>
        </div>
        <div id="chat-dica" className="flex flex-wrap items-center gap-x-3 gap-y-1 px-1 pt-1.5 text-[11px] leading-snug text-ink-muted">
          {/* Saída para uma pessoa sempre à vista, não só quando algo dá errado (NN/g: escape hatch). */}
          {!resgate && (
            <button type="button" onClick={() => enviar("Quero falar com um corretor", "Quero falar com um corretor")}
                    className="font-medium text-brand-accentDark underline-offset-2 hover:underline">
              Falar com um corretor
            </button>
          )}
          {/* LGPD: dizer para que serve o dado no momento em que ele é pedido, não numa página à parte. */}
          <span>
            Seus dados servem só a este atendimento.{" "}
            <a href="/privacidade" className="underline underline-offset-2 hover:text-ink">Como tratamos</a>
          </span>
          {restantes < 150 && <span className="ml-auto tabular-nums" aria-live="polite">{restantes} caracteres restantes</span>}
        </div>
      </form>
    </div>
  );
}
