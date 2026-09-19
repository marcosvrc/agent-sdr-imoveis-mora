import { useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink, Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { Botao, Carregando, FaixaSintetica, cx, foco } from "./componentes/ui";
import { ErroApi, api } from "./lib/api";
import { Auditoria } from "./paginas/Auditoria";
import { Clientes } from "./paginas/Clientes";
import { Encaminhamentos } from "./paginas/Encaminhamentos";
import { Entrar } from "./paginas/Entrar";
import { Funil } from "./paginas/Funil";
import { Imoveis } from "./paginas/Imoveis";
import { LeadDetalhe } from "./paginas/LeadDetalhe";
import { OportunidadeDetalhe } from "./paginas/OportunidadeDetalhe";
import { Visao } from "./paginas/Visao";
import { Visitas } from "./paginas/Visitas";

const MENU = [
  { para: "/", r: "Visão geral" },
  { para: "/funil", r: "Funil" },
  { para: "/clientes", r: "Clientes" },
  { para: "/imoveis", r: "Imóveis" },
  { para: "/visitas", r: "Visitas" },
  { para: "/encaminhamentos", r: "Encaminhamentos" },
];

export function App() {
  // `/auth/me` é a fonte da verdade sobre estar logado: o cookie é HttpOnly, então o JavaScript
  // não tem como olhar e concluir sozinho. Perguntar ao servidor é a única resposta honesta.
  const { data, isLoading, error } = useQuery({ queryKey: ["eu"], queryFn: api.eu });

  if (isLoading) {
    return <div className="mx-auto max-w-md p-8"><Carregando linhas={2} /></div>;
  }
  if (error instanceof ErroApi && error.status === 401) return <Entrar />;
  if (error) return <Entrar erro={error} />;

  const ator = data!.data;
  const admin = ator.role === "admin";

  return (
    <div className="flex min-h-screen flex-col">
      <FaixaSintetica />
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <Menu ator={ator} admin={admin} />
        <main className="min-w-0 flex-1 p-4 lg:p-6">
          <Routes>
            <Route path="/" element={<Visao />} />
            <Route path="/funil" element={<Funil />} />
            <Route path="/clientes" element={<Clientes />} />
            <Route path="/clientes/:id" element={<LeadDetalhe />} />
            <Route path="/oportunidades/:id" element={<OportunidadeDetalhe />} />
            <Route path="/imoveis" element={<Imoveis />} />
            <Route path="/visitas" element={<Visitas />} />
            <Route path="/encaminhamentos" element={<Encaminhamentos />} />
            {admin && <Route path="/auditoria" element={<Auditoria />} />}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

function Menu({ ator, admin }: { ator: { name: string; role: string | null }; admin: boolean }) {
  const qc = useQueryClient();
  const ir = useNavigate();

  async function sair() {
    await api.sair().catch(() => undefined);
    // Limpa o cache ANTES de navegar: sem isso, a tela seguinte pisca com os dados de quem acabou
    // de sair — que é exatamente o que ninguém quer num computador compartilhado.
    qc.clear();
    ir("/");
  }

  const item = ({ isActive }: { isActive: boolean }) =>
    cx("block rounded-md px-3 py-2 text-sm", foco,
      isActive ? "bg-marca text-white" : "text-inkSoft hover:bg-surface2");

  return (
    <nav aria-label="Seções" className="shrink-0 border-b border-line bg-surface p-3 lg:w-56 lg:border-b-0 lg:border-r">
      <p className="px-3 pb-2 text-xs font-semibold uppercase tracking-wide text-inkFaint">Vértice Imóveis · CRM</p>
      <ul className="flex flex-wrap gap-1 lg:block lg:space-y-0.5">
        {MENU.map((m) => (
          <li key={m.para}>
            <NavLink to={m.para} end={m.para === "/"} className={item}>{m.r}</NavLink>
          </li>
        ))}
        {admin && (
          <li><NavLink to="/auditoria" className={item}>Auditoria</NavLink></li>
        )}
      </ul>
      <div className="mt-4 border-t border-line pt-3 lg:mt-auto">
        <p className="px-3 text-xs text-inkMuted">{ator.name}</p>
        <p className="px-3 text-[11px] text-inkFaint">{ator.role === "admin" ? "administrador" : "corretor"}</p>
        <Botao className="mt-2 w-full justify-center" onClick={sair}>Sair</Botao>
      </div>
    </nav>
  );
}
