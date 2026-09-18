import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Card, Carregando, Erro, Etiqueta, Vazio, cx, entradaCls } from "../componentes/ui";
import { api } from "../lib/api";
import { PROPOSITO, brl } from "../lib/formato";

/** Catálogo com os custos DISCRIMINADOS.
 *
 *  O ponto desta tela é o que ela faz com o desconhecido: quando falta um custo mensal, o total
 *  aparece como "incompleto", e não como um número menor. Mostrar um total que ignora o condomínio
 *  é preparar a surpresa do cliente no dia da assinatura.
 */
export function Imoveis() {
  const [finalidade, setFinalidade] = useState("rent");
  const [base, setBase] = useState<"base_price" | "monthly_total">("monthly_total");
  const [teto, setTeto] = useState("");
  const [bairro, setBairro] = useState("");

  const filtros = {
    purpose: finalidade,
    neighborhood: bairro.trim() || undefined,
    max_price_cents: teto ? String(Math.round(Number(teto) * 100)) : undefined,
    budget_basis: base,
    limit: "50",
  };
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["imoveis", filtros], queryFn: () => api.imoveis(filtros),
  });

  const porMes = finalidade === "rent" && base === "monthly_total";

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-ink">Imóveis</h1>

      <Card titulo="Busca">
        <div className="grid gap-3 sm:grid-cols-4">
          <label className="text-sm">
            <span className="mb-1 block font-medium text-inkSoft">Finalidade</span>
            <select className={entradaCls} value={finalidade} onChange={(e) => setFinalidade(e.target.value)}>
              <option value="rent">Aluguel</option>
              <option value="buy">Compra</option>
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-inkSoft">Comparar o orçamento com</span>
            <select className={entradaCls} value={base} disabled={finalidade !== "rent"}
                    onChange={(e) => setBase(e.target.value as typeof base)}>
              <option value="monthly_total">Custo mensal total</option>
              <option value="base_price">Só o valor do imóvel</option>
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-inkSoft">Até (R$)</span>
            <input className={entradaCls} inputMode="numeric" value={teto}
                   onChange={(e) => setTeto(e.target.value.replace(/\D/g, ""))} placeholder="4000" />
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-inkSoft">Bairro</span>
            <input className={entradaCls} value={bairro} onChange={(e) => setBairro(e.target.value)} />
          </label>
        </div>
        {porMes && (
          <p className="mt-2 text-[11px] text-inkFaint">
            Custo mensal = aluguel + condomínio + IPTU + outros. Imóvel com algum desses valores
            desconhecido aparece marcado como incompleto, e não é escondido do resultado.
          </p>
        )}
      </Card>

      {isLoading ? <Carregando linhas={6} />
        : error ? <Erro erro={error} aoTentar={() => refetch()} />
        : data!.items.length === 0 ? <Vazio titulo="Nenhum imóvel com esses filtros" />
        : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {data!.items.map((im) => (
              <article key={im.id} className="rounded-xl border border-line bg-surface p-3 shadow-card">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="text-sm font-medium text-ink">{im.title}</h2>
                  {im.status !== "available" && (
                    <Etiqueta tom={im.status === "unavailable" ? "ruim" : "alerta"}>
                      {im.status === "unavailable" ? "indisponível" : "reservado"}
                    </Etiqueta>
                  )}
                </div>
                <p className="mt-0.5 text-[11px] text-inkFaint">
                  {im.code} · {im.neighborhood}, {im.city} · {im.bedrooms} quarto(s) · {im.parking} vaga(s)
                </p>

                <div className="mt-2 rounded-lg bg-surface2 p-2">
                  {im.purpose === "rent" ? (
                    <>
                      <p className={cx("text-lg font-semibold tabular-nums",
                        im.monthly_total_incomplete ? "text-alerta" : "text-ink")}>
                        {im.monthly_total_incomplete ? "total incompleto" : `${brl(im.monthly_total_cents)}/mês`}
                      </p>
                      <p className="text-[11px] text-inkMuted">
                        aluguel {brl(im.base_price_cents)}
                        {im.monthly_total_incomplete && (
                          <> · falta: {im.monthly_missing.map(legenda).join(", ")}</>
                        )}
                      </p>
                    </>
                  ) : (
                    <p className="text-lg font-semibold tabular-nums text-ink">{brl(im.base_price_cents, true)}</p>
                  )}
                </div>
                <p className="mt-1 text-[11px] text-inkFaint">{PROPOSITO[im.purpose]}</p>
              </article>
            ))}
          </div>
        )}
    </div>
  );
}

function legenda(campo: string): string {
  return { condo_monthly_cents: "condomínio", property_tax_monthly_cents: "IPTU",
           other_monthly_cents: "outros" }[campo] ?? campo;
}
