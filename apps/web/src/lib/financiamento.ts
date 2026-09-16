/** Simulação de parcela e custo mensal.
 *
 *  A conta é real (Tabela Price). O que é estimativa aparece rotulado como estimativa na tela:
 *  a taxa de juros é uma referência editável pelo visitante, não uma oferta, e o IPTU é derivado de
 *  um percentual médio porque o dado não existe na base. Nada aqui é proposta de crédito — texto
 *  nesse sentido acompanha o bloco na interface.
 */

/** Percentual do valor do imóvel usado como IPTU anual quando o dado real não existe.
 *  0,8% a.a. é a ordem de grandeza usual em São Paulo para imóvel residencial; é ESTIMATIVA. */
export const IPTU_ANUAL_ESTIMADO = 0.008;

export const ENTRADA_PADRAO = 0.2;          // 20% — mínimo comum em financiamento imobiliário
export const JUROS_ANUAL_PADRAO = 0.1049;   // referência editável na tela, não uma taxa contratada
export const PRAZOS_ANOS = [10, 15, 20, 25, 30];

/** Tabela Price: parcela fixa. i = juros ao mês, n = número de parcelas. */
export function parcelaPrice(valorFinanciado: number, jurosAnual: number, anos: number): number {
  const i = Math.pow(1 + jurosAnual, 1 / 12) - 1;      // taxa anual efetiva → mensal equivalente
  const n = anos * 12;
  if (valorFinanciado <= 0 || n <= 0) return 0;
  if (i === 0) return valorFinanciado / n;
  return (valorFinanciado * i) / (1 - Math.pow(1 + i, -n));
}

export type Simulacao = { entrada: number; financiado: number; parcela: number; total: number; jurosAnual: number; anos: number };

export function simular(preco: number, entradaPct = ENTRADA_PADRAO, jurosAnual = JUROS_ANUAL_PADRAO, anos = 30): Simulacao {
  const entrada = Math.round(preco * entradaPct);
  const financiado = preco - entrada;
  const parcela = parcelaPrice(financiado, jurosAnual, anos);
  return { entrada, financiado, parcela, total: parcela * anos * 12 + entrada, jurosAnual, anos };
}

export const iptuMensalEstimado = (preco: number) => (preco * IPTU_ANUAL_ESTIMADO) / 12;

/** Custo mensal de ocupação: o número que decide a compra e que quase nenhum site mostra.
 *
 *  Na venda dá para estimar o IPTU, porque o valor do imóvel é conhecido. No aluguel, não: o IPTU
 *  sai do valor venal, que o anúncio não informa — então ele fica de fora e a tela diz isso, em vez
 *  de inventar um número a partir do aluguel. */
export function custoMensal(preco: number, condominio: number | null, operacao: string) {
  const partes = operacao === "aluguel"
    ? [{ r: "Aluguel", v: preco, estimado: false }, { r: "Condomínio", v: condominio ?? 0, estimado: false }]
    : [{ r: "Condomínio", v: condominio ?? 0, estimado: false },
       { r: "IPTU (estimado)", v: iptuMensalEstimado(preco), estimado: true }];
  const usadas = partes.filter((p) => p.v > 0);
  return {
    partes: usadas,
    total: usadas.reduce((s, p) => s + p.v, 0),
    faltaIptu: operacao === "aluguel",
  };
}
