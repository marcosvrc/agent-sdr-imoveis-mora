import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import { Shell } from "./components/Shell";
import { VisaoGeral } from "./pages/VisaoGeral";
import { Leads } from "./pages/Leads";
import { LeadDetalhe } from "./pages/LeadDetalhe";
import { Conversas } from "./pages/Conversas";
import { Agenda } from "./pages/Agenda";
import { Imoveis } from "./pages/Imoveis";
import { Corretores } from "./pages/Corretores";
import { Configuracoes } from "./pages/Configuracoes";
import { Governanca } from "./pages/Governanca";
import { Auditoria } from "./pages/Auditoria";
import { Saude } from "./pages/Saude";
import { Clientes } from "./pages/Clientes";
import { Login } from "./pages/Login";
import { token } from "./lib/auth";

const qc = new QueryClient({ defaultOptions: { queries: { refetchInterval: 15000, staleTime: 5000, retry: 1 } } });
const Guard = ({ children }: { children: React.ReactNode }) => (token() ? <>{children}</> : <Navigate to="/login" replace />);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Guard><Shell /></Guard>}>
            <Route path="/" element={<VisaoGeral />} />
            <Route path="/leads" element={<Leads />} />
            <Route path="/clientes" element={<Clientes />} />
            <Route path="/leads/:id" element={<LeadDetalhe />} />
            <Route path="/conversas" element={<Conversas />} />
            <Route path="/agenda" element={<Agenda />} />
            <Route path="/imoveis" element={<Imoveis />} />
            <Route path="/corretores" element={<Corretores />} />
            <Route path="/governanca" element={<Governanca />} />
            <Route path="/auditoria" element={<Auditoria />} />
            <Route path="/saude" element={<Saude />} />
            <Route path="/configuracoes" element={<Configuracoes />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
