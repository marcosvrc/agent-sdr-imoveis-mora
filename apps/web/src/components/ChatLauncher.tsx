import { useEffect, useRef, useState } from "react";
import { useChat } from "../store/chat";
import { ChatWidget } from "../chat/ChatWidget";
import { BotaoIcone } from "../lib/ui";
import { Ic } from "./Icones";
import { MoraAvatar } from "./MoraAvatar";

/** Lançador do chat, presente em toda página: o visitante não perde a conversa ao navegar.
 *  Só monta o widget (e abre o WebSocket) na primeira abertura — antes disso é só um botão.
 *
 *  Mudanças de acessibilidade: o painel é um diálogo nomeado, o Escape fecha, o foco volta para o
 *  botão que abriu, e o convite que aparece sozinho depois de 5s respeita quem pediu menos
 *  movimento — além de não roubar o foco de quem está lendo. */
export function ChatLauncher() {
  const { aberto, jaAbriu, imovelOrigem, imovelResumo, alternar, fechar } = useChat();
  const [convite, setConvite] = useState(false);
  // Preferência de quem está vendo, lembrada entre visitas. Sem armazenamento (aba anônima,
  // bloqueio), simplesmente começa reduzido.
  const [expandido, setExpandido] = useState(() => {
    try { return localStorage.getItem("mora_chat_expandido") === "1"; } catch { return false; }
  });
  const alternarTamanho = () => setExpandido((e) => {
    try { localStorage.setItem("mora_chat_expandido", e ? "0" : "1"); } catch { /* sem armazenamento */ }
    return !e;
  });
  const botao = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (jaAbriu) return;
    const t = window.setTimeout(() => setConvite(true), 5000);
    return () => clearTimeout(t);
  }, [jaAbriu]);

  useEffect(() => {
    if (!aberto) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { fechar(); botao.current?.focus(); } };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [aberto, fechar]);

  return (
    <div className="lancador-chat fixed bottom-4 right-4 z-40 flex flex-col items-end gap-3 transition-[bottom] sm:bottom-6 sm:right-6">
      {aberto && (
        <div role="dialog" aria-label="Conversa com a Mora, assistente virtual"
             // Expandido: tela cheia no celular; no computador, um painel largo que deixa a leitura
             // confortável sem esconder a página — o cliente continua vendo o imóvel que abriu.
             className={expandido
               ? "fixed inset-0 z-50 animate-pop-in sm:static sm:inset-auto sm:w-[min(94vw,760px)]"
               : "w-[min(92vw,380px)] animate-pop-in"}>
          <ChatWidget imovelOrigem={imovelOrigem} imovelResumo={imovelResumo}
                      altura={expandido ? "h-full sm:h-[min(86vh,860px)]" : "h-[min(70vh,560px)]"}
                      expandido={expandido} aoExpandir={alternarTamanho}
                      aoFechar={() => { fechar(); botao.current?.focus(); }} />
        </div>
      )}

      {!aberto && convite && (
        <button onClick={() => { alternar(); setConvite(false); }}
                className="max-w-[250px] animate-fade-up rounded-lg rounded-br-sm bg-surface p-3 text-left text-sm shadow-soft ring-1 ring-line transition hover:ring-brand-accent">
          <span className="flex gap-2.5">
            <span aria-hidden><MoraAvatar tamanho={32} /></span>
            <span>
              <span className="font-semibold text-brand">Mora</span>
              <span className="block text-ink-muted">Posso ajudar a achar o imóvel certo — me conta o que você procura?</span>
            </span>
          </span>
        </button>
      )}

      <BotaoIcone ref={botao} rotulo={aberto ? "Fechar conversa com a Mora" : "Abrir conversa com a Mora"}
                  aria-expanded={aberto}
                  onClick={() => { alternar(); setConvite(false); }}
                  className={aberto ? "h-14 w-14 bg-brand text-white shadow-soft hover:bg-brand-accentDark hover:text-white"
                                    : "h-14 w-14 overflow-hidden p-0 shadow-soft ring-2 ring-white transition hover:scale-105"}>
        {/* fechado, quem chama é a Mora (o retrato); aberto, o botão vira o "fechar" de sempre */}
        {aberto ? <Ic.fechar size={22} /> : <span aria-hidden><MoraAvatar tamanho={56} /></span>}
      </BotaoIcone>
    </div>
  );
}
