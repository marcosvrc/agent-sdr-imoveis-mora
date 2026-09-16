import { Link } from "react-router-dom";

/** Trilha de navegação. O <ol> importa: a ordem é semântica, e o dado estruturado equivalente
 *  (trilhaJsonLd em lib/seo.ts) é o que faz o buscador mostrar a trilha no resultado. */
export function Migalha({ itens }: { itens: { rotulo: string; para?: string }[] }) {
  return (
    <nav aria-label="Você está aqui">
      <ol className="flex flex-wrap items-center gap-1.5 text-xs text-ink-muted">
        {itens.map((it, i) => (
          <li key={i} className="flex items-center gap-1.5">
            {i > 0 && <span aria-hidden className="text-ink-soft">/</span>}
            {it.para
              ? <Link to={it.para} className="hover:text-brand-accentDark hover:underline">{it.rotulo}</Link>
              : <span className="font-medium text-ink" aria-current="page">{it.rotulo}</span>}
          </li>
        ))}
      </ol>
    </nav>
  );
}
