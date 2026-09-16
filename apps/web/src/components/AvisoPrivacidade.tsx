import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Botao } from "../lib/ui";
import { Ic } from "./Icones";

const CHAVE = "mora_aviso_privacidade";

/** Aviso de privacidade (LGPD, art. 9º — informação clara sobre a finalidade do tratamento).
 *
 *  Não é um muro de cookies, porque não há cookie de terceiro nem publicidade: o site guarda uma
 *  sessão assinada para ligar a navegação à conversa, e favoritos no próprio navegador. O aviso
 *  informa isso e sai; a base legal é legítimo interesse para atendimento, e o consentimento de
 *  verdade é dado quando a pessoa entrega nome e telefone à Mora — no chat, não aqui.
 *
 *  Fechar guarda a escolha; não fechar não bloqueia nada, porque um aviso que impede a navegação
 *  vira clique automático e deixa de informar quem quer que seja.
 */
export function AvisoPrivacidade() {
  const [visivel, setVisivel] = useState(false);

  useEffect(() => {
    try { setVisivel(localStorage.getItem(CHAVE) !== "1"); } catch { /* sem storage: não insiste */ }
  }, []);

  const fechar = () => {
    setVisivel(false);
    try { localStorage.setItem(CHAVE, "1"); } catch { /* idem */ }
  };

  if (!visivel) return null;

  return (
    // No celular a faixa fica no FLUXO da página, no topo, e some ao rolar. Fixa, ela disputava o
    // mesmo canto com a barra de CTA da ficha e com o lançador do chat — três camadas empilhadas,
    // uma cobrindo a outra. No desktop sobra espaço, então volta a ser um cartão flutuante.
    <div role="region" aria-label="Aviso de privacidade"
         className="border-b border-line bg-surface p-4 shadow-sm sm:fixed sm:bottom-4 sm:left-4 sm:z-50 sm:max-w-md sm:rounded-lg sm:border sm:shadow-soft">
      <div className="flex gap-3">
        <span className="mt-0.5 shrink-0 text-brand-accentDark" aria-hidden><Ic.escudo size={20} /></span>
        <div className="text-sm">
          <p className="font-semibold text-ink">Como usamos seus dados</p>
          <p className="mt-1 text-ink-muted">
            Guardamos no seu navegador os imóveis que você favorita e uma sessão para ligar sua navegação
            à conversa com a Mora. Nome, telefone e e-mail só são pedidos quando você quer agendar uma
            visita — e ficam com a imobiliária, sem venda a terceiros.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Botao tamanho="sm" onClick={fechar}>Entendi</Botao>
            <Link to="/privacidade" className="text-xs font-semibold text-brand-accentDark hover:underline" onClick={fechar}>
              Ler o aviso completo
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
