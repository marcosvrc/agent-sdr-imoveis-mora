import { type LinhaModelo } from "../lib/api";
import { Badge, Modal, cx } from "./ui";

/** Dólar com casas suficientes para um custo pequeno não virar "US$ 0,00" — se o número aparece
 *  como zero, a comparação entre os modelos baratos desaparece justamente onde ela decide. */
export const usd = (v: number) =>
  "US$ " + v.toLocaleString("pt-BR", { minimumFractionDigits: v < 1 ? 4 : 2, maximumFractionDigits: v < 1 ? 4 : 2 });

const PAPEL = { conversa: "conversa", roteamento: "roteamento", analise: "análise" } as const;

/** Comparação entre os modelos disponíveis para um papel.
 *
 *  Só mostra o que o projeto mede ou decide: preço (tabela de preços), latência (mediana das
 *  chamadas reais gravadas em `uso_llm`) e o papel que o projeto recomenda (tabela de equivalência).
 *  Janela de contexto e velocidade de catálogo do fornecedor ficaram de fora porque o projeto não
 *  tem esse dado — e um número inventado aqui viraria a razão de alguém escolher o modelo errado.
 */
export function ComparacaoModelos({ aberto, onFechar, papel, linhas, atual, onEscolher }: {
  aberto: boolean;
  onFechar: () => void;
  papel: string;
  linhas: LinhaModelo[];
  atual: string;
  onEscolher: (modelo: string) => void;
}) {
  const base = linhas[0]?.custo;
  const porUso = base?.base === "uso";

  return (
    <Modal aberto={aberto} onFechar={onFechar} largura="max-w-4xl"
           titulo={<>Modelos para <span className="text-ink-muted">{PAPEL[papel as "conversa"] ?? papel}</span></>}>
      <p className="mb-3 rounded-lg bg-info-soft px-3 py-2 text-xs text-ink-muted">
        {porUso
          ? <>A coluna de custo é contrafactual: são os <b>{base.chamadas.toLocaleString("pt-BR")} chamadas</b> que
              este papel fez nos últimos {base.dias} dias, reprecificadas com a tabela de cada modelo. É estimativa,
              não previsão — trocar de modelo muda o tamanho da resposta, e cache não se comporta igual entre
              provedores.</>
          : <>Ainda não há uso gravado neste papel, então o custo é uma <b>estimativa</b> sobre um mix de
              referência (3&nbsp;000 tokens de entrada para 1&nbsp;000 de saída). Depois de algumas conversas,
              esta coluna passa a usar o seu consumo real.</>}
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-ink-muted">
            <tr className="border-b border-line">
              <th className="py-2 pr-3 font-medium">Modelo</th>
              <th className="py-2 pr-3 font-medium">US$ por 1M <span className="text-ink-faint">entrada · saída</span></th>
              <th className="py-2 pr-3 font-medium">Latência mediana</th>
              <th className="py-2 pr-3 font-medium">{porUso ? `Custo · ${base.dias} dias` : "Custo estimado"}</th>
              <th className="py-2 font-medium">Projeto usa para</th>
            </tr>
          </thead>
          <tbody>
            {linhas.map((l) => {
              const eAtual = l.modelo === atual;
              return (
                <tr key={l.modelo}
                    onClick={() => { onEscolher(l.modelo); onFechar(); }}
                    className={cx("cursor-pointer border-b border-line/60 hover:bg-surface-2",
                                  eAtual && "bg-info-soft/50")}>
                  <td className="py-2 pr-3">
                    <span className="font-medium text-ink">{l.modelo}</span>
                    <span className="ml-1.5 text-ink-faint">{l.provedor}</span>
                    {eAtual && <Badge tom="info">em uso</Badge>}
                  </td>
                  <td className="py-2 pr-3 tabular-nums text-ink-muted">
                    {l.preco.entrada.toLocaleString("pt-BR")} · {l.preco.saida.toLocaleString("pt-BR")}
                  </td>
                  <td className="py-2 pr-3 tabular-nums">
                    {/* Sem chamada gravada não há velocidade a informar. Um travessão diz isso; um
                        número de catálogo mentiria com aparência de medição. */}
                    {l.latencia.mediana_ms == null
                      ? <span className="text-ink-faint">— nunca usado aqui</span>
                      : <>{(l.latencia.mediana_ms / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}s
                          <span className="ml-1 text-ink-faint">
                            ({l.latencia.amostras}{l.latencia.escopo === "geral" ? ", outros papéis" : ""})
                          </span></>}
                  </td>
                  <td className="py-2 pr-3 tabular-nums font-medium text-ink">{usd(l.custo.usd)}</td>
                  <td className="py-2">
                    {l.recomendado_para
                      ? <Badge>{PAPEL[l.recomendado_para as "conversa"] ?? l.recomendado_para}</Badge>
                      : <span className="text-ink-faint">—</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-[11px] text-ink-faint">
        Latência é a mediana das chamadas reais deste ambiente, não especificação do fornecedor — e por isso
        depende do tamanho do seu prompt. Janela de contexto não aparece aqui porque o projeto não guarda esse
        dado, e preenchê-lo de memória seria convidar uma escolha baseada em número inventado.
      </p>
    </Modal>
  );
}
