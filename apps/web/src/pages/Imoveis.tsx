import { useEffect, useMemo } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { ORDENACOES, REGIOES, TIPOS, buscarImoveis, preposicaoRegiao, type Filtros as F, type Ordenacao } from "../lib/api";
import { paraSlug } from "../lib/slug";
import { trilhaJsonLd, useSeo } from "../lib/seo";
import { Botao, Campo, Escolha, EstadoErro, EstadoVazio, Esqueleto } from "../lib/ui";
import { Filtros } from "../components/Filtros";
import { ImovelCard } from "../components/ImovelCard";
import { SkeletonCard } from "../components/SkeletonCard";
import { Migalha } from "../components/Migalha";
import { Ic } from "../components/Icones";
import { track } from "../lib/tracking";
import { useChat } from "../store/chat";

const PAGINA = 12;
const NUMERICOS = ["preco_min", "preco_max", "quartos", "suites", "vagas", "area_min"] as const;

function dosParams(sp: URLSearchParams): F {
  const f: F = {};
  for (const k of ["operacao", "regiao", "bairro", "tipo", "texto"] as const) {
    const v = sp.get(k); if (v) f[k] = v;
  }
  const seg = sp.get("segmento");
  if (seg === "residencial" || seg === "comercial") f.segmento = seg;
  for (const k of NUMERICOS) {
    const v = sp.get(k); if (v && !Number.isNaN(Number(v))) f[k] = Number(v);
  }
  return f;
}

/** `ordenar` vem da URL, que qualquer um edita: valor fora da lista ia direto para a API. */
function ordenacaoDaUrl(v: string | null): Ordenacao {
  return ORDENACOES.some((o) => o.v === v) ? (v as Ordenacao) : "relevancia";
}

/** Página na URL começa em 1 (o que a pessoa lê); por dentro, em 0. Lixo ou negativo vira a 1ª. */
function paginaDaUrl(v: string | null): number {
  const n = Number(v);
  return Number.isInteger(n) && n >= 1 ? n - 1 : 0;
}

// A página mora na URL: em estado local, voltar da ficha do imóvel levava à página 1, e trocar de
// filtro na página 3 buscava duas vezes (a página 3 com o filtro novo e, depois do reset, a 1).
// Montar os parâmetros sem `pagina` é o que volta para a 1ª ao trocar filtro ou ordenação — numa
// única atualização da URL, portanto numa busca só.
const paraParams = (f: F, ordenar: Ordenacao, pagina = 0) => {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(f)) if (v !== undefined && v !== "") out[k] = String(v);
  if (ordenar !== "relevancia") out.ordenar = ordenar;
  if (pagina > 0) out.pagina = String(pagina + 1);
  return out;
};

/** Catálogo. Serve duas rotas:
 *   • /imoveis — busca livre, com os filtros na URL;
 *   • /imoveis/:operacao/:bairro — página fixa por bairro, que existe para ser indexada.
 *  A segunda é a mesma tela com o filtro travado e um texto próprio; construir uma página separada
 *  só para o buscador seria manter dois catálogos.
 */
export function Imoveis() {
  const { operacao: opUrl, bairro: bairroUrl } = useParams();
  const [sp, setSp] = useSearchParams();
  const abrirChat = useChat((s) => s.abrir);

  const fixo: F = useMemo(() => (bairroUrl ? { operacao: opUrl, bairro: desslug(bairroUrl) } : {}), [opUrl, bairroUrl]);

  // Só os filtros, sem página e ordenação: mudar de página não é "filtrar" (não dispara o
  // `filtered` de novo nem cria outro objeto de filtro).
  const soFiltros = useMemo(() => {
    const c = new URLSearchParams(sp);
    c.delete("pagina"); c.delete("ordenar");
    return c.toString();
  }, [sp]);
  const f = useMemo(() => ({ ...dosParams(new URLSearchParams(soFiltros)), ...fixo }), [soFiltros, fixo]);
  const ordenar = ordenacaoDaUrl(sp.get("ordenar"));
  const pagina = paginaDaUrl(sp.get("pagina"));

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ["busca", f, ordenar, pagina],
    queryFn: () => buscarImoveis(f, ordenar, PAGINA, pagina * PAGINA),
    placeholderData: keepPreviousData,     // trocar de filtro não pisca a tela inteira
  });

  useEffect(() => { if (Object.keys(f).length) track("filtered", f as Record<string, unknown>); }, [f]);

  // "analia-franco" na URL precisa virar "Anália Franco" na tela: o slug perde o acento, e quem
  // sabe a grafia certa é a API (a consulta ignora acento, então o filtro casa de qualquer jeito).
  const bairroExibido = bairroUrl
    ? data?.bairros.find((b) => paraSlug(b.bairro) === bairroUrl)?.bairro ?? desslug(bairroUrl)
    : undefined;
  const titulo = tituloDaBusca(bairroExibido ? { ...f, bairro: bairroExibido } : f, data?.total);
  const caminho = bairroUrl ? `/imoveis/${opUrl}/${bairroUrl}` : "/imoveis";
  useSeo({
    titulo: `${titulo} | Vértice Imóveis`,
    descricao: descricaoDaBusca(f, data?.total),
    caminho,
    naoIndexar: !bairroUrl && sp.toString().length > 0,   // combinação livre de filtro não vira página indexada
    jsonLd: trilhaJsonLd([
      { nome: "Início", caminho: "/" },
      { nome: "Imóveis", caminho: "/imoveis" },
      ...(bairroExibido ? [{ nome: bairroExibido, caminho }] : []),
    ]),
  }, [titulo, caminho, data?.total]);

  const trocar = (novo: F) => setSp(paraParams({ ...novo, ...fixo }, ordenar), { replace: true });
  const total = data?.total ?? 0;
  const paginas = Math.ceil(total / PAGINA);
  // `?pagina=99` de um link antigo (o catálogo encolheu): leva à última que existe.
  useEffect(() => {
    if (data && !isFetching && paginas > 0 && pagina >= paginas) setSp(paraParams(f, ordenar, paginas - 1), { replace: true });
  }, [data, isFetching, paginas, pagina, f, ordenar, setSp]);
  const irPara = (p: number) => { setSp(paraParams(f, ordenar, p)); window.scrollTo({ top: 0 }); };

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      <Migalha itens={[
        { rotulo: "Início", para: "/" },
        bairroUrl ? { rotulo: "Imóveis", para: "/imoveis" } : { rotulo: "Imóveis" },
        ...(bairroExibido ? [{ rotulo: bairroExibido }] : []),
      ]} />

      <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold text-brand sm:text-3xl">{titulo}</h1>
          <p aria-live="polite" className="mt-1 text-sm text-ink-muted">
            {isLoading ? "Buscando imóveis…" : `${total} ${total === 1 ? "imóvel encontrado" : "imóveis encontrados"}`}
          </p>
        </div>
        <div className="w-44">
          <Campo rotulo="Ordenar por" id="ordenar">
            <Escolha id="ordenar" value={ordenar}
                     onChange={(e) => setSp(paraParams(f, e.target.value as Ordenacao), { replace: true })}>
              {ORDENACOES.map((o) => <option key={o.v} value={o.v}>{o.r}</option>)}
            </Escolha>
          </Campo>
        </div>
      </div>

      <div className="my-4">
        <Filtros value={f} bairros={data?.bairros ?? []} onChange={trocar} total={data?.total} />
      </div>

      {error && <EstadoErro descricao="Não conseguimos carregar o catálogo agora." aoTentar={() => refetch()} />}

      {isLoading && (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => <li key={i}><SkeletonCard /></li>)}
        </ul>
      )}

      {!isLoading && data && total > 0 && (
        <>
          <ul className={`grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 ${isFetching ? "opacity-60 transition" : ""}`}>
            {data.itens.map((im, i) => <li key={im.id}><ImovelCard im={im} prioridade={pagina === 0 && i < 3} /></li>)}
          </ul>
          {isFetching && <Esqueleto className="mx-auto mt-4 h-1 w-24" />}
          {paginas > 1 && (
            <nav aria-label="Paginação" className="mt-8 flex items-center justify-center gap-3">
              <Botao variante="secundario" disabled={pagina === 0} onClick={() => irPara(pagina - 1)}
                     icone={<Ic.esquerda size={16} />}>Anterior</Botao>
              <span className="text-sm text-ink-muted">Página {pagina + 1} de {paginas}</span>
              <Botao variante="secundario" disabled={pagina + 1 >= paginas} onClick={() => irPara(pagina + 1)}>
                Próxima <Ic.direita size={16} />
              </Botao>
            </nav>
          )}
        </>
      )}

      {!isLoading && data && total === 0 && (
        <EstadoVazio
          icone={<Ic.busca size={22} />}
          titulo="Nenhum imóvel com esses filtros"
          descricao="Tente tirar um filtro — ou peça à Mora: ela conhece o catálogo inteiro e sugere o que mais chega perto."
          acao={
            <div className="flex flex-wrap justify-center gap-2">
              <Botao onClick={() => abrirChat()} icone={<Ic.chat size={16} />}>Perguntar à Mora</Botao>
              <Botao variante="secundario" onClick={() => trocar({})}>Limpar filtros</Botao>
            </div>
          } />
      )}
    </div>
  );
}

const desslug = (s: string) => s.split("-").map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join(" ");
/** Título que descreve a busca — "Apartamentos de 2 quartos em Perdizes" em vez de "Imóveis".
 *  Vale para a pessoa (sabe o que está vendo) e para o buscador (h1 e <title> diferentes por página). */
function tituloDaBusca(f: F, _total?: number): string {
  const tipo = f.tipo ? `${TIPOS[f.tipo] ?? f.tipo}s`
    : f.segmento === "comercial" ? "Imóveis comerciais" : "Imóveis";
  const quartos = f.segmento === "comercial" || !f.quartos ? "" : ` de ${f.quartos}+ quartos`;
  const onde = f.bairro ? ` em ${f.bairro}`
    : f.regiao ? ` ${preposicaoRegiao(f.regiao)} ${REGIOES[f.regiao] ?? f.regiao}` : " em São Paulo";
  const op = f.operacao === "aluguel" ? " para alugar" : f.operacao === "venda" ? " à venda" : "";
  return `${tipo}${quartos}${op}${onde}`;
}

function descricaoDaBusca(f: F, total?: number): string {
  const quantos = total != null ? `${total} ` : "";
  return `${quantos}${tituloDaBusca(f).toLowerCase()} no catálogo da Vértice Imóveis. Filtre por preço, quartos, suítes e vagas — e agende a visita conversando com a Mora.`;
}
