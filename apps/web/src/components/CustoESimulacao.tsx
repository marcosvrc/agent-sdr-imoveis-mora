import { useId, useState } from "react";
import { brl, type Imovel } from "../lib/api";
import { ENTRADA_PADRAO, JUROS_ANUAL_PADRAO, PRAZOS_ANOS, custoMensal, simular } from "../lib/financiamento";
import { Campo, Entrada, Escolha, cx } from "../lib/ui";
import { Ic } from "./Icones";

/** Custo mensal e simulação de parcela.
 *
 *  É o que separa "gostei do apartamento" de "cabe no meu mês", e nenhum dos dois números estava na
 *  ficha. Regra que se aplica aos dois blocos: o que é conta aparece como conta, o que é estimativa
 *  aparece rotulado — inclusive o IPTU, que não existe na base e é derivado de um percentual médio.
 */
export function CustoMensal({ im }: { im: Imovel }) {
  const { partes, total, faltaIptu } = custoMensal(im.preco, im.condominio, im.operacao);
  if (!partes.length) return null;

  return (
    <section aria-labelledby="custo-mensal" className="rounded-lg bg-surface p-4 ring-1 ring-line">
      <h2 id="custo-mensal" className="flex items-center gap-2 font-semibold text-ink">
        <Ic.info size={17} className="text-brand-accentDark" />Custo mensal
      </h2>
      <dl className="mt-3 space-y-1.5 text-sm">
        {partes.map((p) => (
          <div key={p.r} className="flex justify-between gap-4">
            <dt className={cx("text-ink-muted", p.estimado && "italic")}>{p.r}</dt>
            <dd className="tabular-nums text-ink">{brl(p.v)}</dd>
          </div>
        ))}
        <div className="flex justify-between gap-4 border-t border-line pt-2 font-semibold">
          <dt className="text-ink">Total por mês</dt>
          <dd className="tabular-nums text-brand">{brl(total)}</dd>
        </div>
      </dl>
      <p className="mt-2 text-xs text-ink-muted">
        {faltaIptu
          ? "O IPTU não entra nesta conta: ele é calculado sobre o valor venal do imóvel, que não consta do anúncio. Pergunte à Mora e um corretor confirma o valor."
          : "O IPTU é uma estimativa a partir do valor do imóvel; o valor exato vem no carnê do ano."}
      </p>
    </section>
  );
}

export function SimulacaoFinanciamento({ im }: { im: Imovel }) {
  const id = useId();
  const [entradaPct, setEntradaPct] = useState(ENTRADA_PADRAO);
  const [anos, setAnos] = useState(30);
  const [juros, setJuros] = useState(JUROS_ANUAL_PADRAO);
  const s = simular(im.preco, entradaPct, juros, anos);

  if (im.operacao !== "venda") return null;

  return (
    <section aria-labelledby="simulacao" className="rounded-lg bg-surface p-4 ring-1 ring-line">
      <h2 id="simulacao" className="flex items-center gap-2 font-semibold text-ink">
        <Ic.regua size={17} className="text-brand-accentDark" />Simule a parcela
      </h2>

      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <Campo rotulo="Entrada" id={`${id}-e`}>
          <Escolha id={`${id}-e`} value={entradaPct} onChange={(e) => setEntradaPct(Number(e.target.value))}>
            {[0.1, 0.2, 0.3, 0.4, 0.5].map((p) => <option key={p} value={p}>{Math.round(p * 100)}% · {brl(im.preco * p)}</option>)}
          </Escolha>
        </Campo>
        <Campo rotulo="Prazo" id={`${id}-p`}>
          <Escolha id={`${id}-p`} value={anos} onChange={(e) => setAnos(Number(e.target.value))}>
            {PRAZOS_ANOS.map((a) => <option key={a} value={a}>{a} anos</option>)}
          </Escolha>
        </Campo>
        <Campo rotulo="Juros ao ano (%)" id={`${id}-j`} dica="Referência editável">
          <Entrada id={`${id}-j`} type="number" step={0.1} min={0} max={30} inputMode="decimal"
                   value={(juros * 100).toFixed(2)}
                   onChange={(e) => setJuros(Math.max(0, Number(e.target.value)) / 100)} />
        </Campo>
      </div>

      <p className="mt-4 text-sm text-ink-muted">
        Financiando {brl(s.financiado)} em {anos} anos, a primeira parcela fica em
        <strong className="ml-1 font-display text-xl text-brand">{brl(s.parcela)}</strong>
        <span className="text-ink-muted"> por mês</span>.
      </p>
      <p className="mt-2 text-xs text-ink-muted">
        Cálculo pela Tabela Price, com a taxa que você digitou. É uma <strong>estimativa para orientar
        a conversa</strong> — não é proposta de crédito, não inclui seguros, taxas nem análise do banco,
        e a parcela real depende da instituição e do seu perfil.
      </p>
    </section>
  );
}
