import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AvisoOrdemParcial, Botao, CabecalhoPagina, Card, Carregando, Erro, Etiqueta, Paginacao,
         Vazio, cx, entradaCls, foco, usePaginaCursor } from "../componentes/ui";
import { Link } from "react-router-dom";
import { Ic } from "../componentes/Icones";
import { api, type Imovel } from "../lib/api";
import { ordenar, useAtraso, useFiltrosNaUrl, type Ordem } from "../lib/filtros";
import { PROPOSITO, SITUACAO_IMOVEL, brl } from "../lib/formato";

const POR_PAGINA = "24";
type Campo = "preco" | "quartos" | "bairro";
// Cartão não tem cabeçalho de coluna para clicar, então a ordenação vira um seletor. O rótulo diz
// "entre os carregados" quando há mais página — ver AvisoOrdemParcial.
const ORDENS: { k: string; r: string }[] = [
  { k: "", r: "Ordem do servidor (mais recentes)" },
  { k: "preco", r: "Preço — menor primeiro" },
  { k: "preco:desc", r: "Preço — maior primeiro" },
  { k: "quartos:desc", r: "Mais quartos" },
  { k: "bairro", r: "Bairro (A–Z)" },
];

/** Catálogo com os custos DISCRIMINADOS.
 *
 *  O ponto desta tela é o que ela faz com o desconhecido: quando falta um custo mensal, o total
 *  aparece como "incompleto", e não como um número menor. Mostrar um total que ignora o condomínio
 *  é preparar a surpresa do cliente no dia da assinatura.
 */
export function Imoveis() {
  const { valores, definir, limpar, algumFiltro } = useFiltrosNaUrl(
    { finalidade: "rent", base: "monthly_total", teto: "", bairro: "", ordem: "" });
  const [bairro, setBairro] = useState(valores.bairro);
  const [teto, setTeto] = useState(valores.teto);
  const bairroAtrasado = useAtraso(bairro);
  const tetoAtrasado = useAtraso(teto, 500);   // número leva mais tempo para terminar de digitar
  const pag = usePaginaCursor();

  useEffect(() => { definir({ bairro: bairroAtrasado, teto: tetoAtrasado }); }, [bairroAtrasado, tetoAtrasado]);   // eslint-disable-line react-hooks/exhaustive-deps
  // Botão voltar do navegador: a URL muda, o estado do React não fica sabendo sozinho.
  useEffect(() => { if (valores.bairro !== bairroAtrasado) setBairro(valores.bairro); }, [valores.bairro]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (valores.teto !== tetoAtrasado) setTeto(valores.teto); }, [valores.teto]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { pag.reiniciar(); }, [bairroAtrasado, tetoAtrasado, valores.finalidade, valores.base]);   // eslint-disable-line react-hooks/exhaustive-deps

  const finalidade = valores.finalidade;
  const base = valores.base as "base_price" | "monthly_total";
  const filtros = {
    purpose: finalidade,
    neighborhood: bairroAtrasado.trim() || undefined,
    max_price_cents: tetoAtrasado ? String(Math.round(Number(tetoAtrasado) * 100)) : undefined,
    budget_basis: base,
    limit: POR_PAGINA,
    cursor: pag.cursor,
  };
  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["imoveis", filtros], queryFn: () => api.imoveis(filtros),
  });

  const porMes = finalidade === "rent" && base === "monthly_total";
  const [campo, dir] = valores.ordem.split(":");
  const ordem: Ordem<Campo> | null = campo ? { campo: campo as Campo, desc: dir === "desc" } : null;
  const itens = ordenar(data?.items ?? [], ordem, (im, c) =>
    c === "bairro" ? im.neighborhood
    : c === "quartos" ? im.bedrooms
    // Ordenar aluguel pelo preço-base quando a tela inteira fala em custo mensal daria uma ordem
    // que contradiz o número grande do cartão.
    : (porMes ? im.monthly_total_cents ?? im.base_price_cents : im.base_price_cents));

  return (
    <div className="space-y-4">
      <CabecalhoPagina titulo="Imóveis"
        descricao="Custo mensal discriminado. Total incompleto aparece marcado, nunca como um número menor."
        acoes={<>
          {algumFiltro && <Botao onClick={() => { limpar(); setBairro(""); setTeto(""); }}><Ic.limpar size={14} /> Limpar filtros</Botao>}
          <Link to="/imoveis/novo" className={cx("inline-flex items-center gap-1.5 rounded-md border border-transparent bg-marca px-2.5 py-1.5 text-sm font-medium text-marcaInk hover:opacity-90", foco)}>
            + Novo imóvel
          </Link>
        </>} />

      <Card titulo="Busca" acoes={isFetching ? <span className="text-[11px] text-inkFaint">buscando…</span> : undefined}>
        <div className="grid gap-3 sm:grid-cols-4">
          <label className="text-sm">
            <span className="mb-1 block font-medium text-inkSoft">Finalidade</span>
            <select className={entradaCls} value={finalidade} onChange={(e) => definir({ finalidade: e.target.value })}>
              <option value="rent">Aluguel</option>
              <option value="buy">Compra</option>
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block font-medium text-inkSoft">Comparar o orçamento com</span>
            <select className={entradaCls} value={base} disabled={finalidade !== "rent"}
                    onChange={(e) => definir({ base: e.target.value })}>
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
        : itens.length === 0 ? <Vazio titulo="Nenhum imóvel com esses filtros"
                                      descricao="Tente ampliar o teto de preço ou tirar o bairro." />
        : (
          <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <label className="flex items-center gap-2 text-xs text-inkMuted">
              Ordenar por
              <select className={cx(entradaCls, "w-auto py-1 text-xs")} value={valores.ordem}
                      onChange={(e) => definir({ ordem: e.target.value })}>
                {ORDENS.map((o) => <option key={o.k} value={o.k}>{o.r}</option>)}
              </select>
            </label>
            <span className="text-xs text-inkFaint">{itens.length} imóveis nesta página</span>
          </div>
          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {itens.map((im) => (
              <article key={im.id} className="rounded-xl border border-line bg-surface p-3 shadow-card">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="text-sm font-medium text-ink">{im.title}</h2>
                  {im.status !== "available" && (
                    <Etiqueta tom={SITUACAO_IMOVEL[im.status]?.tom ?? "alerta"}>
                      {SITUACAO_IMOVEL[im.status]?.r ?? im.status}
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
                <p className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-inkFaint">
                  {PROPOSITO[im.purpose]}
                  {/* Procura: dois clientes no mesmo imóvel é normal, e saber disso muda a
                      prioridade do corretor. Some quando é um só — "1 cliente" não é notícia. */}
                  {(im.interested_count ?? 0) > 1 && (
                    <Etiqueta tom="info">{im.interested_count} clientes de olho</Etiqueta>
                  )}
                </p>
                <Situacao im={im} />
              </article>
            ))}
          </div>
          <div className="mt-3 overflow-hidden rounded-xl border border-line bg-surface">
            <AvisoOrdemParcial mostrar={!!ordem && !!data!.next_cursor} />
            <Paginacao rotulo="imóveis" mostrando={itens.length} pagina={pag.pagina} primeira={pag.primeira}
                       temProxima={!!data!.next_cursor} aoVoltar={pag.voltar}
                       aoAvancar={() => data!.next_cursor && pag.avancar(data!.next_cursor)} />
          </div>
          </>
        )}
    </div>
  );
}

/** Tirar do catálogo e devolver.
 *
 *  O controle mora no CARTÃO do imóvel, e não numa tela de edição separada: a decisão acontece
 *  olhando preço e bairro, e obrigar a abrir outra tela é o que faz alguém deixar para depois — e
 *  "depois" é a Mora oferecendo por mais uma semana um imóvel que já tem dono.
 *
 *  Sair do catálogo pede motivo; voltar, não. É a assimetria do próprio servidor, repetida aqui
 *  para o campo aparecer antes de o botão falhar.
 */
function Situacao({ im }: { im: Imovel }) {
  const qc = useQueryClient();
  const [abrindo, setAbrindo] = useState(false);
  const [alvo, setAlvo] = useState("");
  const [motivo, setMotivo] = useState("");

  const mudar = useMutation({
    mutationFn: () => api.mudarSituacao(im.id, alvo, motivo.trim() || null),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["imoveis"] });
      setAbrindo(false); setAlvo(""); setMotivo("");
    },
  });

  const opcoes = Object.keys(SITUACAO_IMOVEL).filter((k) => k !== im.status);
  const pedeMotivo = alvo !== "" && alvo !== "available";

  if (!abrindo) {
    return (
      <div className="mt-2 flex gap-1.5 border-t border-line pt-2">
        <Botao type="button" className="flex-1 justify-center text-xs" onClick={() => setAbrindo(true)}>
          Mudar situação
        </Botao>
        <Link to={`/imoveis/${im.id}/agenda`}
              className={cx("inline-flex items-center rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs font-medium text-inkSoft hover:bg-surface2", foco)}>
          Agenda
        </Link>
      </div>
    );
  }
  return (
    <div className="mt-2 space-y-1.5 border-t border-line pt-2">
      {mudar.error ? <Erro erro={mudar.error} /> : null}
      <select className={cx(entradaCls, "text-xs")} value={alvo} aria-label={`Nova situação de ${im.code}`}
              onChange={(e) => setAlvo(e.target.value)}>
        <option value="">Para…</option>
        {opcoes.map((k) => <option key={k} value={k}>{SITUACAO_IMOVEL[k].r}</option>)}
      </select>
      {alvo && <p className="text-[11px] text-inkMuted">{SITUACAO_IMOVEL[alvo].ajuda}</p>}
      {pedeMotivo && (
        <input className={cx(entradaCls, "text-xs")} placeholder="Motivo (obrigatório)"
               aria-label="Motivo" value={motivo} onChange={(e) => setMotivo(e.target.value)} />
      )}
      <div className="flex gap-1.5">
        <Botao type="button" variante="primario" className="flex-1 justify-center text-xs"
               ocupado={mudar.isPending} disabled={!alvo || (pedeMotivo && !motivo.trim())}
               onClick={() => mudar.mutate()}>Confirmar</Botao>
        <Botao type="button" className="text-xs"
               onClick={() => { setAbrindo(false); setAlvo(""); setMotivo(""); }}>Cancelar</Botao>
      </div>
    </div>
  );
}

function legenda(campo: string): string {
  return { condo_monthly_cents: "condomínio", property_tax_monthly_cents: "IPTU",
           other_monthly_cents: "outros" }[campo] ?? campo;
}
