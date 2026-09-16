import type { ReactNode } from "react";
import { IMOBILIARIA, type Campo } from "../lib/imobiliaria";
import { cx } from "../lib/ui";
import { Ic } from "./Icones";

/** Dado institucional que ainda não é real aparece assim: visível, mas marcado.
 *
 *  A alternativa seria esconder o campo (o visitante não sabe que falta) ou inventar (o visitante
 *  acredita numa credencial falsa). Marcar é a única opção que não engana ninguém — e serve de
 *  lembrete permanente de que aquilo precisa ser preenchido antes de o site ir ao ar. */
export function DadoInstitucional({ campo, icone, className }: { campo: Campo; icone?: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex flex-wrap items-center gap-1.5", className)}>
      {icone}
      <span className={campo.placeholder ? "text-ink-soft" : ""}>{campo.valor}</span>
      {campo.placeholder && (
        <span title="Dado de exemplo — substituir pelo real antes de publicar"
              className="rounded border border-dashed border-amber-400 bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-estado-alerta">
          exemplo
        </span>
      )}
    </span>
  );
}

const GARANTIAS = [
  { i: <Ic.relogio size={18} />, t: "Resposta na hora", d: "A Mora atende 24h por dia; um corretor assume sempre que você pedir." },
  { i: <Ic.escudo size={18} />, t: "Seus dados protegidos", d: "Só pedimos nome e contato quando você quer agendar. Nada é vendido a terceiros." },
  { i: <Ic.casa size={18} />, t: "Catálogo verificado", d: "Preço, área e condomínio vêm do cadastro do imóvel, não de anúncio replicado." },
];

/** Três promessas verificáveis contra o que o sistema realmente faz. Não é prova social — não há
 *  avaliação, nota nem depoimento aqui, porque não existe nenhum verdadeiro para exibir. */
export function FaixaGarantias({ className }: { className?: string }) {
  return (
    <ul className={cx("grid gap-4 sm:grid-cols-3", className)}>
      {GARANTIAS.map((g) => (
        <li key={g.t} className="flex gap-3 rounded-lg bg-surface p-4 ring-1 ring-line">
          <span className="mt-0.5 shrink-0 text-brand-accentDark" aria-hidden>{g.i}</span>
          <span>
            <span className="block text-sm font-semibold text-ink">{g.t}</span>
            <span className="mt-0.5 block text-sm text-ink-muted">{g.d}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** Bloco de identificação: CRECI, CNPJ, endereço, horário. No Brasil, anúncio de imóvel sem CRECI
 *  visível não é só desconfiança — é irregular perante o Conselho. */
export function IdentificacaoLegal({ className }: { className?: string }) {
  return (
    <div className={cx("space-y-1.5 text-sm text-ink-muted", className)}>
      <p className="font-medium text-ink">{IMOBILIARIA.nome.valor}</p>
      <p><DadoInstitucional campo={IMOBILIARIA.creci} /></p>
      <p><DadoInstitucional campo={IMOBILIARIA.cnpj} /> · CNPJ</p>
      <p><DadoInstitucional campo={IMOBILIARIA.endereco} icone={<Ic.local size={15} />} /></p>
      <p><DadoInstitucional campo={IMOBILIARIA.horario} icone={<Ic.relogio size={15} />} /></p>
      <p><DadoInstitucional campo={IMOBILIARIA.responsavelTecnico} /> · responsável técnico</p>
    </div>
  );
}
