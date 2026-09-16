export type Imovel = {
  id: string; tipo: string; operacao: "venda" | "aluguel"; cidade: string; regiao: string; bairro: string;
  quartos: number; suites: number; vagas: number; area_m2: number; preco: number; condominio: number | null;
  descricao: string; fotos: string[]; destaque_investimento: boolean; pontos_referencia?: string[];
};

/** Filtros da vitrine. Espelham 1:1 os parâmetros de `GET /imoveis/busca` — quando um campo novo
 *  entra na API ele entra aqui, e a tela ganha o controle correspondente. */
export type Filtros = {
  operacao?: string; regiao?: string; bairro?: string; tipo?: string;
  preco_min?: number; preco_max?: number; quartos?: number; suites?: number; vagas?: number;
  area_min?: number; texto?: string;
};

export type Ordenacao = "relevancia" | "preco_asc" | "preco_desc" | "area_desc";

export type ResultadoBusca = {
  itens: Imovel[]; total: number; bairros: { bairro: string; n: number }[]; limite: number; offset: number;
};

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const qs = (o: Record<string, unknown>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  return p.toString();
};

/** Página do catálogo. Devolve o total junto: é o que permite dizer "38 encontrados" e paginar no
 *  servidor, em vez de baixar os 200 imóveis no navegador só para contar. */
export async function buscarImoveis(f: Filtros, ordenar: Ordenacao, limite: number, offset: number): Promise<ResultadoBusca> {
  const r = await fetch(`${BASE}/imoveis/busca?${qs({ ...f, ordenar, limite, offset })}`);
  if (!r.ok) throw new Error("falha ao buscar imóveis");
  return r.json();
}

export async function listarImoveis(f: Filtros = {}, limite = 60): Promise<Imovel[]> {
  const r = await fetch(`${BASE}/imoveis?${qs({ ...f, limite })}`);
  if (!r.ok) throw new Error("falha ao listar imóveis");
  return r.json();
}

export async function obterImovel(id: string): Promise<Imovel> {
  const r = await fetch(`${BASE}/imoveis/${encodeURIComponent(id)}`);
  if (!r.ok) throw new Error("imóvel não encontrado");
  return r.json();
}

export const REGIOES: Record<string, string> = { zona_sul: "Zona Sul", zona_oeste: "Zona Oeste", zona_norte: "Zona Norte", zona_leste: "Zona Leste", centro: "Centro" };
/** "na Zona Sul", mas "no Centro". Sem isto o rodapé escrevia "Imóveis na Centro". */
export const preposicaoRegiao = (regiao: string) => (regiao === "centro" ? "no" : "na");

export const TIPOS: Record<string, string> = { apartamento: "Apartamento", casa: "Casa", studio: "Studio" };

export const ORDENACOES: { v: Ordenacao; r: string }[] = [
  { v: "relevancia", r: "Mais relevantes" },
  { v: "preco_asc", r: "Menor preço" },
  { v: "preco_desc", r: "Maior preço" },
  { v: "area_desc", r: "Maior área" },
];

export const brl = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

/** "na casa", "no apartamento" — o artigo depende do tipo, não da operação. */
export const preposicaoTipo = (tipo: string) => (tipo === "casa" ? "na" : "no");

/** Nome canônico do imóvel: título da ficha, alt da foto e <title> da aba usam este.
 *  Um lugar só, para não existirem três formas de nomear a mesma coisa.
 *
 *  "em" e não "no/na": aqui a preposição rege o BAIRRO, não o tipo — e o artigo do bairro varia
 *  ("no Brooklin", "na Bela Vista", "em Perdizes"). Sem uma lista de artigos por bairro, "em" é a
 *  única forma sempre correta. (`preposicaoTipo` continua valendo onde a regência é do imóvel:
 *  "de olho na casa", "de olho no apartamento".) */
export const nomeImovel = (im: Imovel) => {
  const tipo = TIPOS[im.tipo] ?? im.tipo;
  const quartos = im.quartos > 0 ? ` de ${im.quartos} quarto${im.quartos === 1 ? "" : "s"}` : "";
  return `${tipo}${quartos} em ${im.bairro}`;
};
