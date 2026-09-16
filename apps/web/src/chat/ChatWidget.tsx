import { useCallback, useEffect, useRef, useState } from "react";
import { conectar, type EventoCanal, type RespostaAgente } from "../lib/ws";
import { track } from "../lib/tracking";
import { brl, TIPOS, preposicaoTipo } from "../lib/api";
import type { ImovelResumo } from "../store/chat";
import { MensagemBolha } from "./MensagemBolha";
import { CardImovelChat } from "./CardImovelChat";
import { BotoesOpcoes } from "./BotoesOpcoes";
import { CardVisita, type Visita } from "./CardVisita";

type Bolha = { de: "lead" | "Mora"; texto: string; r?: RespostaAgente; aviso?: boolean };

/** Nenhuma espera é infinita: avisamos que está demorando e, passando disso, oferecemos um humano.
 *  RESGATE_MS folgado de propósito: a busca de imóveis chama embeddings (Ollama, no perfil local) e,
 *  rodando em CPU comum, um turno completo pode passar de 40-50s sem nada estar quebrado — visto ao
 *  vivo em teste local. Baixo demais aqui só engana o cliente, oferecendo humano bem no meio de uma
 *  resposta que já estava a caminho. */
const AVISO_MS = 10_000;
const RESGATE_MS = 60_000;
import { TELEGRAM_USUARIO as USUARIO_TELEGRAM } from "../lib/imobiliaria";

// Frase que menciona o imóvel de onde o cliente veio — o agente recebe o mesmo dado por trás
// (handler.py lê `imovel_origem`), isto é só a bolha de saudação já nascer falando daquilo,
// em vez de o cliente ter que repetir o que já deixou claro ao clicar "conversar sobre este imóvel".
function saudacaoDoImovel(im: ImovelResumo): string {
  const tipo = (TIPOS[im.tipo] ?? im.tipo).toLowerCase();
  const preco = brl(im.preco) + (im.operacao === "aluguel" ? "/mês" : "");
  return `Oi! Sou a Mora, assistente virtual da Vértice Imóveis. Vi que você está de olho ${preposicaoTipo(im.tipo)} ${tipo} em ${im.bairro}, por ${preco}. Quer que eu conte mais sobre ele, compare com opções parecidas ou já agende uma visita?`;
}

export function ChatWidget({ imovelOrigem, imovelResumo, altura = "h-[70vh]", aoFechar }: { imovelOrigem?: string; imovelResumo?: ImovelResumo; altura?: string; aoFechar?: () => void }) {
  const [bolhas, setBolhas] = useState<Bolha[]>([{
    de: "Mora",
    texto: imovelResumo ? saudacaoDoImovel(imovelResumo) : "Olá! Eu sou a Mora, assistente virtual da Vértice Imóveis. Estou aqui para entender o que você procura e ajudar a encontrar o imóvel ideal para o seu próximo momento.",
  }]);
  const [texto, setTexto] = useState("");
  const [online, setOnline] = useState(false);
  const [digitando, setDigitando] = useState(false);
  const [demorando, setDemorando] = useState(false);
  const [resgate, setResgate] = useState(false);
  const conn = useRef<ReturnType<typeof conectar>>();
  const fim = useRef<HTMLDivElement>(null);
  const timers = useRef<number[]>([]);
  const ultimoResumoAnunciado = useRef(imovelResumo?.id);

  const limparTimers = useCallback(() => { timers.current.forEach(clearTimeout); timers.current = []; }, []);
  const pararEspera = useCallback(() => { limparTimers(); setDigitando(false); setDemorando(false); setResgate(false); }, [limparTimers]);

  // Se o cliente já tinha o chat aberto e clica em "conversar sobre este imóvel" em OUTRA ficha,
  // o widget não remonta (mantém a conversa) — então avisamos a mudança de contexto numa nova bolha.
  useEffect(() => {
    if (!imovelResumo || imovelResumo.id === ultimoResumoAnunciado.current) return;
    ultimoResumoAnunciado.current = imovelResumo.id;
    setBolhas((b) => [...b, { de: "Mora", texto: `Também vi que você deu uma olhada ${preposicaoTipo(imovelResumo.tipo)} ${(TIPOS[imovelResumo.tipo] ?? imovelResumo.tipo).toLowerCase()} em ${imovelResumo.bairro}, por ${brl(imovelResumo.preco)}${imovelResumo.operacao === "aluguel" ? "/mês" : ""}. Quer falar sobre esse também?` }]);
  }, [imovelResumo]);

  useEffect(() => {
    track("opened_chat", { imovel_id: imovelOrigem });
    conn.current = conectar(
      (r) => { pararEspera(); setBolhas((b) => [...b, { de: "Mora", texto: r.texto, r }]); },
      (s) => setOnline(s === "on"),
      (e: EventoCanal) => {
        if (e.evento === "falha_envio") {
          pararEspera();
          setBolhas((b) => [...b, { de: "Mora", texto: e.texto ?? "Não consegui registrar sua mensagem. Pode tentar de novo?", aviso: true }]);
        }
      },
    );
    return () => { conn.current?.fechar(); limparTimers(); };
  }, [imovelOrigem, pararEspera, limparTimers]);
  useEffect(() => { fim.current?.scrollIntoView({ behavior: "smooth" }); }, [bolhas, digitando, demorando, resgate]);

  const enviar = (t: string, rotulo = t, botao = false) => {
    if (!t.trim()) return;
    setBolhas((b) => [...b, { de: "lead", texto: rotulo }]);
    setTexto("");
    limparTimers();
    setDigitando(true); setDemorando(false); setResgate(false);
    // botao=true: o canal marca a mensagem como TipoMensagem.BOTAO (mesmo contrato do WhatsApp)
    conn.current?.enviar(t, { ...(imovelOrigem ? { imovel_origem: imovelOrigem } : {}), ...(botao ? { botao: true } : {}) });
    timers.current.push(window.setTimeout(() => setDemorando(true), AVISO_MS));
    timers.current.push(window.setTimeout(() => { setDemorando(false); setResgate(true); }, RESGATE_MS));
  };

  const ultima = bolhas[bolhas.length - 1];
  const mostrarOpcoes = ultima.de === "Mora" && !!ultima.r?.opcoes?.length && !digitando && !resgate;

  return (
    <div className={`flex ${altura} flex-col overflow-hidden rounded-2xl bg-white shadow ring-1 ring-slate-200`}>
      <div className="flex items-center gap-2 border-b border-line px-4 py-2.5 text-sm">
        <span className={`h-2 w-2 rounded-full ${online ? "bg-estado-ok" : "bg-estado-alerta"}`} aria-hidden />
        <span className="font-medium">Mora</span><span className="text-ink-muted">· assistente virtual</span>
        {/* O texto acompanha a bolinha: cor sozinha não transmite estado (WCAG 1.4.1). */}
        <span className={aoFechar ? "text-xs" : "ml-auto text-xs"}>
          <span className="sr-only">Estado da conexão: </span>
          <span className={online ? "text-estado-ok" : "text-estado-alerta"}>{online ? "online" : "reconectando…"}</span>
        </span>
        {aoFechar && (
          <button onClick={aoFechar} aria-label="Fechar chat" className="ml-auto grid h-6 w-6 place-items-center rounded-full text-slate-400 hover:bg-slate-100 hover:text-slate-600">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        )}
      </div>
      {/* role=log + aria-live: sem isto, quem usa leitor de tela não fica sabendo que a
          Mora respondeu — a bolha aparece na tela e não é anunciada em lugar nenhum. */}
      <div role="log" aria-live="polite" aria-relevant="additions text" aria-label="Mensagens da conversa"
           className="flex-1 space-y-3 overflow-y-auto bg-ground p-4">
        {bolhas.map((b, i) => (
          <div key={i} className="space-y-2">
            {b.r?.imoveis?.map((c) => <CardImovelChat key={c.id} card={c} />)}
            <MensagemBolha de={b.de} texto={b.texto} />
            {b.r?.acao === "agendar" && b.r.dados?.visita ? <CardVisita visita={b.r.dados.visita as Visita} /> : null}
          </div>
        ))}
        {digitando && !demorando && !resgate && <MensagemBolha de="Mora" texto="…" />}
        {demorando && (
          <div className="flex items-center gap-2 rounded-2xl bg-white px-3 py-2 text-sm text-slate-600 shadow-sm ring-1 ring-slate-200">
            <span className="flex gap-0.5">{[0, 1, 2].map((i) => <span key={i} className="h-1.5 w-1.5 animate-pulse rounded-full bg-slate-400" style={{ animationDelay: `${i * 150}ms` }} />)}</span>
            Ainda estou procurando as melhores opções para você…
          </div>
        )}
        {resgate && (
          <div className="rounded-2xl bg-white p-3 text-sm shadow-sm ring-1 ring-amber-200">
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
        <div ref={fim} />
      </div>
      {mostrarOpcoes ? <BotoesOpcoes opcoes={ultima.r!.opcoes} onEscolher={(id, rotulo) => enviar(id, rotulo, true)} /> : null}
      <form className="border-t border-line p-2" onSubmit={(e) => { e.preventDefault(); enviar(texto); }}>
        <div className="flex gap-2">
          <label htmlFor="chat-mensagem" className="sr-only">Escreva sua mensagem para a Mora</label>
          <input id="chat-mensagem" className="h-11 flex-1 rounded-md border border-line-forte px-3 text-sm text-ink placeholder:text-ink-soft focus:border-brand-accent focus:outline-none"
                 autoComplete="off"
                 placeholder={online ? "Escreva sua mensagem…" : "Sem conexão — enviaremos ao reconectar"}
                 value={texto} onChange={(e) => setTexto(e.target.value)} />
          <button className="h-11 rounded-md bg-brand px-4 text-sm font-semibold text-white transition hover:bg-brand-accentDark" type="submit">Enviar</button>
        </div>
        {/* LGPD: dizer para que serve o dado no momento em que ele é pedido, não numa página à parte. */}
        <p className="px-1 pt-1.5 text-[11px] leading-snug text-ink-muted">
          Ao enviar, seus dados são usados só para este atendimento.{" "}
          <a href="/privacidade" className="underline underline-offset-2 hover:text-ink">Como tratamos seus dados</a>.
        </p>
      </form>
    </div>
  );
}
