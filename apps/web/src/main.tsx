import React, { Suspense, lazy } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import { Layout } from "./components/Layout";
import { Landing } from "./pages/Landing";

// A home entra no bundle inicial (é onde a maioria chega); o resto carrega quando a rota é aberta.
const Imoveis = lazy(() => import("./pages/Imoveis").then((m) => ({ default: m.Imoveis })));
const ImovelDetalhe = lazy(() => import("./pages/ImovelDetalhe").then((m) => ({ default: m.ImovelDetalhe })));
const Favoritos = lazy(() => import("./pages/Favoritos").then((m) => ({ default: m.Favoritos })));
const Privacidade = lazy(() => import("./pages/Privacidade").then((m) => ({ default: m.Privacidade })));
const NaoEncontrada = lazy(() => import("./pages/NaoEncontrada").then((m) => ({ default: m.NaoEncontrada })));

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, retry: 1, refetchOnWindowFocus: false } } });

/** Endereço antigo (/imoveis/SP-0001) continua funcionando: redireciona para a URL com slug.
 *  Link compartilhado meses atrás não pode virar 404 por causa de um redesenho. */
function RedirecionaFichaAntiga() {
  const { id = "" } = useParams();
  return <Navigate to={`/imovel/${id.toLowerCase()}`} replace />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Suspense fallback={<div className="min-h-[60vh]" aria-busy="true" aria-label="Carregando" />}>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/" element={<Landing />} />
              <Route path="/imoveis" element={<Imoveis />} />
              {/* Página por bairro: /imoveis/venda/perdizes — existe para ser indexada. */}
              <Route path="/imoveis/:operacao/:bairro" element={<Imoveis />} />
              <Route path="/imovel/:slug" element={<ImovelDetalhe />} />
              <Route path="/imoveis/:id" element={<RedirecionaFichaAntiga />} />
              <Route path="/favoritos" element={<Favoritos />} />
              <Route path="/privacidade" element={<Privacidade />} />
              <Route path="*" element={<NaoEncontrada />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
