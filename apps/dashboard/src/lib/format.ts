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
export const CANAL: Record<string, string> = { telegram: "Telegram", web: "Site", sistema: "Sistema" };
export const rotulo = (m: Record<string, string>, k?: string | null) => (k && m[k]) || (k ? k.replace(/_/g, " ") : "—");

/** O canal de origem, quando o lead tem canal registrado — ou deduzido do prefixo do id.
 *
 *  A dedução existia espalhada numa célula da tabela de leads. Ela amarra a APARÊNCIA do id a uma
 *  regra de negócio: mudar o prefixo apagaria a coluna sem quebrar teste nenhum. Continua sendo
 *  aproximação, mas agora numa função só — se o dia da mudança chegar, é um lugar.
 */
export function canalDoLead(l: { id: string; canais?: { canal: string }[] }): string | null {
  if (l.canais?.length) return l.canais[0].canal;
  if (l.id.startsWith("web_")) return "web";
  if (l.id.startsWith("tg_")) return "telegram";
  return null;
}

/** Como chamar o lead na tela.
 *
 *  O id NUNCA entra aqui. Ele vinha ocupando o lugar do nome em seis pontos do painel
 *  (`nome ?? id`), e o resultado era o corretor lendo `web_1QQhFOfvpH4hIHCdktHr5w` na linha onde
 *  procura uma pessoa — e um avatar com as iniciais "WE".
 *
 *  A queda é nome → contato → descrição do canal. O último é uma DESCRIÇÃO, não um nome: vem com
 *  `anonimo: true` para a tela poder apagá-lo visualmente, senão "Visitante do site" passa a ser
 *  lido como o nome da pessoa.
 *
 *  O sufixo curto existe porque uma lista com cinco "Visitante do site" idênticos é pior que o id:
 *  o corretor não sabe qual já abriu. Quatro caracteres do id bastam para distinguir na tela e não
 *  se parecem com identificador para copiar — quem quer o id inteiro usa o chip da tela do lead.
 */
export function nomeDoLead(l: { id: string; nome?: string | null; telefone?: string | null; canais?: { canal: string }[] }):
    { texto: string; anonimo: boolean; avatar: string } {
  const canal = canalDoLead(l);
  const base = canal === "web" ? "Visitante do site"
             : canal === "telegram" ? "Contato do Telegram"
             : "Contato sem identificação";
  if (l.nome?.trim()) return { texto: l.nome.trim(), anonimo: false, avatar: l.nome.trim() };
  // Telefone é contato de verdade, então vale como título — mas não como iniciais: um avatar
  // escrito "+1" não identifica ninguém. Para as iniciais vale a descrição do canal.
  if (l.telefone?.trim()) return { texto: l.telefone.trim(), anonimo: false, avatar: base };
  // O sufixo sai do FIM do id: o começo é o prefixo do canal, igual em todos, e distinguiria nada.
  const sufixo = l.id.replace(/^[a-z]+_/, "").slice(-4);
  return { texto: sufixo ? `${base} · ${sufixo}` : base, anonimo: true, avatar: base };
}

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
