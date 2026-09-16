import { useEffect, useRef, useState } from "react";
import { useChat } from "../store/chat";
import { ChatWidget } from "../chat/ChatWidget";
import { BotaoIcone } from "../lib/ui";
import { Ic } from "./Icones";

/** Lançador do chat, presente em toda página: o visitante não perde a conversa ao navegar.
 *  Só monta o widget (e abre o WebSocket) na primeira abertura — antes disso é só um botão.
 *
 *  Mudanças de acessibilidade: o painel é um diálogo nomeado, o Escape fecha, o foco volta para o
 *  botão que abriu, e o convite que aparece sozinho depois de 5s respeita quem pediu menos
 *  movimento — além de não roubar o foco de quem está lendo. */
export function ChatLauncher() {
  const { aberto, jaAbriu, imovelOrigem, imovelResumo, alternar, fechar } = useChat();
  const [convite, setConvite] = useState(false);
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
        <div role="dialog" aria-label="Conversa com a Mora, assistente virtual" className="w-[min(92vw,380px)] animate-pop-in">
          <ChatWidget imovelOrigem={imovelOrigem} imovelResumo={imovelResumo}
                      altura="h-[min(70vh,560px)]" aoFechar={() => { fechar(); botao.current?.focus(); }} />
        </div>
      )}

      {!aberto && convite && (
        <button onClick={() => { alternar(); setConvite(false); }}
                className="max-w-[250px] animate-fade-up rounded-lg rounded-br-sm bg-surface p-3 text-left text-sm shadow-soft ring-1 ring-line transition hover:ring-brand-accent">
          <span className="font-semibold text-brand">Mora</span>
          <span className="block text-ink-muted">Posso ajudar a achar o imóvel certo — me conta o que você procura?</span>
        </button>
      )}

      <BotaoIcone ref={botao} rotulo={aberto ? "Fechar conversa com a Mora" : "Abrir conversa com a Mora"}
                  aria-expanded={aberto}
                  onClick={() => { alternar(); setConvite(false); }}
                  className="h-14 w-14 bg-brand text-white shadow-soft hover:bg-brand-accentDark hover:text-white">
        {aberto ? <Ic.fechar size={22} /> : <Ic.chat size={24} />}
      </BotaoIcone>
    </div>
  );
}
