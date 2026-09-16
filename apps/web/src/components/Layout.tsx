import { Suspense, lazy } from "react";
import { Outlet } from "react-router-dom";
import { Header } from "./Header";
import { Footer } from "./Footer";
import { AvisoPrivacidade } from "./AvisoPrivacidade";

// O chat é o maior pedaço de JS do site e a maioria das visitas nunca o abre: carregar sob demanda
// tira ~30% do bundle inicial do caminho crítico.
const ChatLauncher = lazy(() => import("./ChatLauncher").then((m) => ({ default: m.ChatLauncher })));

export function Layout() {
  return (
    <div className="flex min-h-screen flex-col bg-ground">
      {/* Primeiro tab da página: pula o cabeçalho inteiro e vai para o conteúdo. */}
      <a href="#conteudo" className="pular-para-conteudo">Pular para o conteúdo</a>
      {/* Antes do cabeçalho: no celular é uma faixa no fluxo, então precisa nascer no topo do documento. */}
      <AvisoPrivacidade />
      <Header />
      <main id="conteudo" tabIndex={-1} className="w-full flex-1 outline-none"><Outlet /></main>
      <Footer />
      <Suspense fallback={null}><ChatLauncher /></Suspense>
    </div>
  );
}
