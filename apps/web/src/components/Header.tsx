import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useChat } from "../store/chat";
import { IMOBILIARIA } from "../lib/imobiliaria";
import { Botao, BotaoIcone, cx } from "../lib/ui";
import { Ic } from "./Icones";

const LINKS = [
  { to: "/imoveis?operacao=venda", label: "Comprar", chave: "venda" },
  { to: "/imoveis?operacao=aluguel", label: "Alugar", chave: "aluguel" },
  { to: "/favoritos", label: "Favoritos", chave: "favoritos" },
];

export function Header() {
  const { pathname, search } = useLocation();
  const abrirChat = useChat((s) => s.abrir);
  const [menu, setMenu] = useState(false);
  const botaoMenu = useRef<HTMLButtonElement>(null);

  // Fecha ao navegar e devolve o foco a quem abriu — sem isso o teclado fica preso no fim da página.
  useEffect(() => { setMenu(false); }, [pathname, search]);
  useEffect(() => {
    if (!menu) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { setMenu(false); botaoMenu.current?.focus(); } };
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, [menu]);

  /** "Comprar" ficava aceso na ficha de um imóvel de aluguel: a regra antiga era
   *  "está em /imoveis e a URL não diz aluguel". Agora depende do parâmetro de verdade. */
  const ativo = (chave: string) => {
    if (chave === "favoritos") return pathname === "/favoritos";
    const op = new URLSearchParams(search).get("operacao");
    return pathname.startsWith("/imoveis") && op === chave;
  };

  const cls = (chave: string) =>
    cx("rounded-md px-2 py-1.5 text-sm font-medium transition",
       ativo(chave) ? "text-brand-accentDark" : "text-ink-muted hover:text-ink");

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-surface/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
        <Link to="/" className="flex items-center gap-2 font-display text-lg font-semibold tracking-tight text-brand">
          <span className="grid h-9 w-9 place-items-center rounded-md bg-brand text-sm font-semibold text-white" aria-hidden>VI</span>
          <span className="hidden sm:inline">{IMOBILIARIA.nome.valor}</span>
          <span className="sm:hidden">Vértice</span>
        </Link>

        <nav aria-label="Principal" className="hidden items-center gap-2 md:flex">
          {LINKS.map((l) => (
            <NavLink key={l.label} to={l.to} className={cls(l.chave)}
                     aria-current={ativo(l.chave) ? "page" : undefined}>{l.label}</NavLink>
          ))}
        </nav>

        <div className="hidden items-center gap-2 md:flex">
          {/* Telefone visível é sinal de confiança: um site imobiliário sem telefone parece fachada.
              Enquanto o número for placeholder, ele aparece mas não vira link clicável. */}
          {!IMOBILIARIA.telefone.placeholder && (
            <a href={`tel:${IMOBILIARIA.telefoneLink.valor}`} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm font-medium text-ink-muted hover:text-ink">
              <Ic.telefone size={16} />{IMOBILIARIA.telefone.valor}
            </a>
          )}
          <Botao tamanho="sm" icone={<Ic.chat size={16} />} onClick={() => abrirChat()}>Falar com a Mora</Botao>
        </div>

        <BotaoIcone ref={botaoMenu} rotulo={menu ? "Fechar menu" : "Abrir menu"}
                    aria-expanded={menu} aria-controls="menu-mobile"
                    onClick={() => setMenu((v) => !v)} className="md:hidden">
          {menu ? <Ic.fechar size={22} /> : <Ic.filtro size={22} />}
        </BotaoIcone>
      </div>

      <div id="menu-mobile" hidden={!menu} className="border-t border-line bg-surface px-4 py-3 md:hidden">
        <nav aria-label="Principal (celular)" className="flex flex-col gap-1">
          {LINKS.map((l) => (
            <Link key={l.label} to={l.to} aria-current={ativo(l.chave) ? "page" : undefined}
                  className={cx("alvo-toque flex items-center rounded-md px-3 text-sm font-medium",
                                ativo(l.chave) ? "bg-brand-suave text-brand-accentDark" : "text-ink-muted")}>
              {l.label}
            </Link>
          ))}
          <Botao className="mt-1" icone={<Ic.chat size={16} />} onClick={() => { abrirChat(); setMenu(false); }}>
            Falar com a Mora
          </Botao>
        </nav>
      </div>
    </header>
  );
}
