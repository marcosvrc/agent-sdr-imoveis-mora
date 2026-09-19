// Layout do painel: sidebar recolhível (só ícones) persistida, drawer no mobile, topbar com estado do tempo real.
import { useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { logout } from "../lib/auth";
import { useTempoReal } from "../lib/ws";
import { Ic, type IconName } from "./Icons";
import { Avatar, cx } from "./ui";
import { Notificacoes } from "./Notificacoes";
import { SeletorTema } from "./SeletorTema";

// Este painel é da MORA, não da imobiliária. Ficha de cliente, funil comercial, visitas e
// oportunidades vivem no CRM (docs/decisions.md D-01) — "Clientes" e "Agenda" saíram daqui porque
// eram a mesma informação em dois lugares, e duas telas que discordam sobre o mesmo cliente é pior
// que uma tela só. O que fica é o que só a Mora sabe: como o agente está atendendo.
type Item = { to: string; label: string; icone: IconName; fim?: boolean };
const OPERACAO: Item[] = [
  { to: "/", label: "Visão geral", icone: "overview", fim: true },
  { to: "/leads", label: "Leads", icone: "leads" },
  { to: "/conversas", label: "Conversas", icone: "chat" },
];
const ADMIN: Item[] = [
  { to: "/imoveis", label: "Imóveis", icone: "building" },
  { to: "/corretores", label: "Corretores", icone: "badge" },
  { to: "/governanca", label: "Governança de IA", icone: "gauge" },
  { to: "/auditoria", label: "Auditoria", icone: "shield" },
  { to: "/saude", label: "Saúde do sistema", icone: "bolt" },
  { to: "/configuracoes", label: "Configurações", icone: "settings" },
];
export const TITULOS: Record<string, string> = { "/": "Visão geral", "/leads": "Leads", "/conversas": "Conversas", "/imoveis": "Imóveis", "/corretores": "Corretores", "/governanca": "Governança de IA", "/auditoria": "Auditoria", "/saude": "Saúde do sistema", "/configuracoes": "Configurações" };

const KEY = "mora.sidebar";
const lerColapsado = () => { try { return localStorage.getItem(KEY) === "1"; } catch { return false; } };

export function Shell() {
  const [colapsado, setColapsado] = useState(lerColapsado);
  const [drawer, setDrawer] = useState(false);
  const [aoVivo, setAoVivo] = useState(false);
  const nav = useNavigate();
  const loc = useLocation();
  const qc = useQueryClient();
  useEffect(() => { try { localStorage.setItem(KEY, colapsado ? "1" : "0"); } catch { /* ignore */ } }, [colapsado]);
  useEffect(() => { setDrawer(false); }, [loc.pathname]);
  // Tempo real: qualquer evento invalida as consultas de operação (leads, funil, atividade)
  useTempoReal(useCallback((e) => { setAoVivo(true); if (e.evento === "mensagem") { qc.invalidateQueries({ queryKey: ["leads"] }); qc.invalidateQueries({ queryKey: ["metricas"] }); qc.invalidateQueries({ queryKey: ["atividade"] }); qc.invalidateQueries({ queryKey: ["funil"] }); qc.invalidateQueries({ queryKey: ["notificacoes"] }); } }, [qc]), setAoVivo);

  const titulo = TITULOS[loc.pathname] ?? (loc.pathname.startsWith("/leads/") ? "Lead" : "");
  const sair = () => { logout(); nav("/login"); };

  const Nav = ({ compacto }: { compacto: boolean }) => (
    <nav className="flex flex-1 flex-col gap-4 px-2 py-3">
      <Grupo titulo="Atendimento" compacto={compacto} itens={OPERACAO} />
      <Grupo titulo="Administração" compacto={compacto} itens={ADMIN} />
    </nav>
  );

  return (
    <div className="flex min-h-screen bg-canvas text-ink">
      {/* Sidebar desktop */}
      <aside className={cx("sticky top-0 hidden h-screen shrink-0 flex-col border-r border-line bg-surface transition-[width] duration-200 md:flex", colapsado ? "w-16" : "w-60")}>
        <div className={cx("flex h-14 items-center border-b border-line", colapsado ? "justify-center" : "gap-2 px-4")}>
          <Logo />
          {!colapsado && <div className="leading-tight"><div className="text-sm font-semibold">Mora</div><div className="text-[11px] text-ink-muted">Painel do agente</div></div>}
        </div>
        <Nav compacto={colapsado} />
        <div className="border-t border-line p-2">
          <button onClick={() => setColapsado((c) => !c)} title={colapsado ? "Expandir menu" : "Recolher menu"} className={cx("flex h-9 w-full items-center gap-2 rounded-lg px-2.5 text-xs text-ink-muted hover:bg-surface-2 hover:text-ink", colapsado && "justify-center")}>
            {colapsado ? <Ic.chevronRight size={16} /> : <><Ic.chevronLeft size={16} /><span>Recolher menu</span></>}
          </button>
        </div>
      </aside>

      {/* Drawer mobile */}
      {drawer && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setDrawer(false)} />
          <aside className="relative flex h-full w-64 flex-col bg-surface shadow-2xl">
            <div className="flex h-14 items-center gap-2 border-b border-line px-4"><Logo /><div className="text-sm font-semibold">Mora</div><button className="ml-auto rounded-md p-1 text-ink-muted hover:bg-surface-2" onClick={() => setDrawer(false)} aria-label="Fechar menu"><Ic.x size={18} /></button></div>
            <Nav compacto={false} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface px-4 backdrop-blur md:px-6">
          <button className="rounded-md p-1.5 text-ink-muted hover:bg-surface-2 md:hidden" onClick={() => setDrawer(true)} aria-label="Abrir menu"><Ic.menu size={20} /></button>
          <h2 className="truncate text-sm font-semibold text-ink md:text-base">{titulo}</h2>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-[11px] text-ink-muted sm:inline-flex" title="Conexão em tempo real com os canais">
              <span className={cx("h-1.5 w-1.5 rounded-full", aoVivo ? "bg-good" : "bg-ink-faint")} />{aoVivo ? "ao vivo" : "conectando…"}
            </span>
            <SeletorTema />
            <Notificacoes />
            <button onClick={() => qc.invalidateQueries()} className="rounded-md p-1.5 text-ink-muted hover:bg-surface-2" title="Atualizar dados"><Ic.refresh size={16} /></button>
            <div className="ml-1 flex items-center gap-2 border-l border-line pl-3">
              <Avatar nome="Corretor Dev" tamanho={28} />
              <div className="hidden leading-tight lg:block"><div className="text-xs font-medium">Corretor</div><div className="text-[11px] text-ink-muted">corretor@local</div></div>
              <button onClick={sair} className="rounded-md p-1.5 text-ink-muted hover:bg-surface-2 hover:text-ink" title="Sair"><Ic.logout size={16} /></button>
            </div>
          </div>
        </header>
        <main className="flex-1 px-4 py-5 md:px-6 md:py-6"><div className="mx-auto max-w-[1400px]"><Outlet /></div></main>
      </div>
    </div>
  );
}

function Grupo({ titulo, itens, compacto }: { titulo: string; itens: Item[]; compacto: boolean }) {
  return (
    <div>
      {!compacto && <p className="mb-1 px-2.5 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">{titulo}</p>}
      {compacto && <div className="mx-2 mb-1 border-t border-line" />}
      <ul className="space-y-0.5">
        {itens.map((i) => { const Icon = Ic[i.icone]; return (
          <li key={i.to}>
            <NavLink to={i.to} end={i.fim} title={compacto ? i.label : undefined}
              className={({ isActive }) => cx("group flex h-9 items-center gap-2.5 rounded-lg text-sm transition", compacto ? "justify-center px-0" : "px-2.5",
                isActive ? "bg-brand text-brand-ink shadow-sm" : "text-ink-muted hover:bg-surface-2 hover:text-ink")}>
              <Icon size={18} className="shrink-0" />{!compacto && <span className="truncate">{i.label}</span>}
            </NavLink>
          </li>); })}
      </ul>
    </div>
  );
}

function Logo() {
  return <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand text-brand-ink"><Ic.spark size={16} /></span>;
}
