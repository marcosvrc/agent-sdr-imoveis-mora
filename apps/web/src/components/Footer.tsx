import { Link } from "react-router-dom";
import { useChat } from "../store/chat";
import { IMOBILIARIA } from "../lib/imobiliaria";
import { REGIOES, preposicaoRegiao } from "../lib/api";
import { IdentificacaoLegal, DadoInstitucional } from "./Confianca";
import { Ic } from "./Icones";

/** O rodapé faz três trabalhos: identificar a empresa (CRECI e afins), dar caminho legal (LGPD) e
 *  oferecer links por zona — que também é a malha interna que o buscador usa para achar o catálogo. */
export function Footer() {
  const abrirChat = useChat((s) => s.abrir);

  return (
    <footer className="mt-16 border-t border-line bg-surface">
      <div className="mx-auto grid max-w-6xl gap-8 px-4 py-12 sm:px-6 md:grid-cols-4">
        <div className="space-y-3 md:col-span-2">
          <p className="flex items-center gap-2 font-display text-lg font-semibold text-brand">
            <span className="grid h-8 w-8 place-items-center rounded-md bg-brand text-xs font-semibold text-white" aria-hidden>VI</span>
            {IMOBILIARIA.nome.valor}
          </p>
          {/* Assinatura da marca aqui, e não o slogan: o slogan já abre a home, e repetir a mesma
              frase nas duas pontas da página não acrescenta nada. `descricao` continua servindo às
              meta tags e ao dado estruturado, onde o texto é lido por máquina. */}
          <p className="max-w-sm text-sm font-medium text-ink">{IMOBILIARIA.assinatura.valor}</p>
          <p className="max-w-sm text-sm text-ink-muted">{IMOBILIARIA.missao.valor}</p>
          <IdentificacaoLegal className="pt-2" />
        </div>

        <nav aria-label="Imóveis por zona" className="text-sm">
          <h2 className="mb-2.5 font-semibold text-ink">Imóveis por zona</h2>
          <ul className="space-y-2 text-ink-muted">
            {Object.entries(REGIOES).map(([k, v]) => (
              <li key={k}>
                <Link to={`/imoveis?regiao=${k}`} className="hover:text-brand-accentDark hover:underline">
                  Imóveis {preposicaoRegiao(k)} {v}
                </Link>
              </li>
            ))}
            <li><Link to="/imoveis" className="hover:text-brand-accentDark hover:underline">Catálogo completo</Link></li>
          </ul>
        </nav>

        <div className="text-sm">
          <h2 className="mb-2.5 font-semibold text-ink">Fale com a gente</h2>
          <ul className="space-y-2 text-ink-muted">
            <li>
              <button onClick={() => abrirChat()} className="inline-flex items-center gap-1.5 hover:text-brand-accentDark hover:underline">
                <Ic.chat size={15} />Conversar com a Mora
              </button>
            </li>
            <li className="inline-flex items-center gap-1.5">
              <Ic.telefone size={15} /><DadoInstitucional campo={IMOBILIARIA.telefone} />
            </li>
            <li><DadoInstitucional campo={IMOBILIARIA.email} /></li>
            <li className="pt-2"><Link to="/privacidade" className="hover:text-brand-accentDark hover:underline">Privacidade e uso de dados</Link></li>
            <li><Link to="/favoritos" className="hover:text-brand-accentDark hover:underline">Meus favoritos</Link></li>
          </ul>
        </div>
      </div>

      <div className="border-t border-line px-4 py-4 text-center text-xs text-ink-muted">
        Mora é o assistente virtual da {IMOBILIARIA.nome.valor} · projeto de demonstração acadêmica —
        os dados de contato e de registro acima são exemplos.
      </div>
    </footer>
  );
}
