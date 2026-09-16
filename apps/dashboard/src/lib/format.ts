// Formatação centralizada: valores, percentuais, datas — sempre pt-BR / America/Sao_Paulo.
const TZ = "America/Sao_Paulo";

export const brl = (v?: number | null, compact = false) =>
  v == null ? "—" : new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: compact ? 1 : 0, notation: compact ? "compact" : "standard" }).format(v);

export const num = (v?: number | null) => v == null ? "—" : new Intl.NumberFormat("pt-BR").format(v);

export const pct = (v?: number | null, casas = 0) => v == null || !isFinite(v) ? "—" : `${(v * 100).toFixed(casas).replace(".", ",")}%`;

export const duracao = (seg?: number | null) => {
  if (seg == null) return "—";
  if (seg < 60) return `${Math.round(seg)}s`;
  if (seg < 3600) return `${Math.round(seg / 60)} min`;
  return `${(seg / 3600).toFixed(1).replace(".", ",")} h`;
};

export const dataHora = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", timeZone: TZ }) : "—";

export const dataCurta = (iso: string) => new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "short", timeZone: TZ }).replace(".", "");

export const relativo = (iso?: string | null) => {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "agora";
  if (s < 3600) return `${Math.floor(s / 60)} min`;
  if (s < 86400) return `${Math.floor(s / 3600)} h`;
  return `${Math.floor(s / 86400)} d`;
};

/** Variação relativa entre períodos; null quando não há base de comparação. */
export const variacao = (atual: number, anterior: number) => anterior === 0 ? (atual === 0 ? 0 : null) : (atual - anterior) / anterior;

export const REGIAO: Record<string, string> = { zona_sul: "Zona Sul", zona_oeste: "Zona Oeste", zona_norte: "Zona Norte", zona_leste: "Zona Leste", centro: "Centro", indefinida: "Não informada" };
export const INTENCAO: Record<string, string> = { compra: "Compra", aluguel: "Aluguel", investimento: "Investimento", indefinida: "Indefinida" };
export const CANAL: Record<string, string> = { telegram: "Telegram", whatsapp: "WhatsApp", web: "Site", sistema: "Sistema" };
export const rotulo = (m: Record<string, string>, k?: string | null) => (k && m[k]) || (k ? k.replace(/_/g, " ") : "—");

/** Tokens em escala legível: 980, 12,4 mil, 3,2 mi. */
export const tokens = (v?: number | null) =>
  v == null ? "—" : v < 1000 ? String(v)
  : v < 1_000_000 ? `${(v / 1000).toFixed(1).replace(".0", "").replace(".", ",")} mil`
  : `${(v / 1_000_000).toFixed(2).replace(".", ",")} mi`;

/** Custos de LLM são centavos: precisa de mais casas que um preço de imóvel. */
export const usd = (v?: number | null) => v == null ? "—"
  : v === 0 ? "US$ 0"
  : v < 0.01 ? `US$ ${v.toFixed(4).replace(".", ",")}`
  : `US$ ${v.toFixed(2).replace(".", ",")}`;
export const brlCusto = (usdValor: number, cotacao: number) => {
  const v = usdValor * cotacao;
  return v === 0 ? "R$ 0" : v < 0.01 ? `R$ ${v.toFixed(4).replace(".", ",")}` : `R$ ${v.toFixed(2).replace(".", ",")}`;
};
