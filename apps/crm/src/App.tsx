import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Botao, Carregando, FaixaSintetica, SeletorTema, cx, foco } from "./componentes/ui";
import { Ic } from "./componentes/Icones";
import { ErroApi, api } from "./lib/api";
import { aplicar, temaSalvo } from "./lib/tema";
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
  { para: "/", r: "Visão geral", icone: "visao" },
  { para: "/funil", r: "Funil", icone: "funil" },
  { para: "/clientes", r: "Clientes", icone: "clientes" },
  { para: "/imoveis", r: "Imóveis", icone: "imoveis" },
  { para: "/visitas", r: "Visitas", icone: "visitas" },
  { para: "/encaminhamentos", r: "Encaminhamentos", icone: "encaminhamentos" },
] as const;

export function App() {
  // O tema é aplicado antes de qualquer consulta: esperar o `/auth/me` responder faria a tela de
  // login piscar clara para quem escolheu escuro.
  useEffect(() => { aplicar(temaSalvo()); }, []);

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
      {/* Primeiro item focável da página: quem navega por teclado não precisa percorrer o menu
          inteiro em toda troca de tela para chegar ao que veio ler. */}
      <a href="#conteudo"
         className={cx("sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50",
                       "focus:rounded-md focus:bg-marca focus:px-3 focus:py-2 focus:text-sm focus:text-marcaInk", foco)}>
        Pular para o conteúdo
      </a>
      <FaixaSintetica />
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <Menu ator={ator} admin={admin} />
        <main id="conteudo" tabIndex={-1} className="min-w-0 flex-1 p-4 lg:p-6">
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
  const local = useLocation();
  const [aberto, setAberto] = useState(false);

  // No celular o menu é uma gaveta; trocar de tela tem de fechá-la, senão a pessoa toca num item
  // e continua olhando para o menu, sem sinal de que alguma coisa aconteceu.
  useEffect(() => { setAberto(false); }, [local.pathname]);

  async function sair() {
    await api.sair().catch(() => undefined);
    // Limpa o cache ANTES de navegar: sem isso, a tela seguinte pisca com os dados de quem acabou
    // de sair — que é exatamente o que ninguém quer num computador compartilhado.
    qc.clear();
    ir("/");
  }

  const item = ({ isActive }: { isActive: boolean }) =>
    cx("flex items-center gap-2.5 rounded-md px-3 py-2 text-sm", foco,
      isActive ? "bg-marca font-medium text-marcaInk" : "text-inkSoft hover:bg-surface2 hover:text-ink");

  const links = (
    <ul className="space-y-0.5">
      {MENU.map((m) => {
        const Icone = Ic[m.icone];
        return (
          <li key={m.para}>
            <NavLink to={m.para} end={m.para === "/"} className={item}>
              <Icone size={16} className="shrink-0" />{m.r}
            </NavLink>
          </li>
        );
      })}
      {admin && (
        <li className="pt-1">
          <NavLink to="/auditoria" className={item}><Ic.auditoria size={16} className="shrink-0" />Auditoria</NavLink>
        </li>
      )}
    </ul>
  );

  return (
    <nav aria-label="Seções" className="shrink-0 border-b border-line bg-surface lg:flex lg:w-60 lg:flex-col lg:border-b-0 lg:border-r">
      <div className="flex items-center justify-between gap-2 px-3 py-3 lg:px-4">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">Vértice Imóveis</p>
          {/* O nome do produto fica visível o tempo todo: a cor distingue os dois apps de longe,
              mas quem está chegando precisa ler qual dos dois abriu. */}
          <p className="text-[11px] font-medium uppercase tracking-wide text-acento">CRM · operação</p>
        </div>
        <div className="flex items-center gap-1">
          <SeletorTema />
          <button type="button" onClick={() => setAberto((a) => !a)} aria-expanded={aberto} aria-controls="menu-secoes"
                  aria-label={aberto ? "Fechar menu" : "Abrir menu"}
                  className={cx("rounded-md p-1.5 text-inkMuted hover:bg-surface2 hover:text-ink lg:hidden", foco)}>
            {aberto ? <Ic.limpar size={18} /> : <Ic.menu size={18} />}
          </button>
        </div>
      </div>

      <div id="menu-secoes" className={cx("px-3 pb-3 lg:block lg:flex-1 lg:px-3", aberto ? "block" : "hidden")}>
        {links}
      </div>

      <div className={cx("border-t border-line px-3 py-3 lg:block", aberto ? "block" : "hidden lg:block")}>
        <p className="truncate px-1 text-xs font-medium text-inkSoft">{ator.name}</p>
        <p className="px-1 text-[11px] text-inkFaint">{ator.role === "admin" ? "administrador" : "corretor"}</p>
        <Botao className="mt-2 w-full justify-center" onClick={sair}><Ic.sair size={14} /> Sair</Botao>
      </div>
    </nav>
  );
}
