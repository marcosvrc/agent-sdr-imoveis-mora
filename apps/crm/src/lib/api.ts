/** Cliente da API do CRM.
 *
 *  Duas coisas que a especificação obriga e que são fáceis de perder de vista no front:
 *
 *  1. **`credentials: "include"` em toda chamada.** A sessão humana é um cookie HttpOnly — o
 *     JavaScript não o enxerga, e é justamente esse o ponto: um token que o script lê é um token
 *     que um XSS rouba. Sem `include`, o navegador simplesmente não o envia e tudo vira 401.
 *  2. **Nenhum token de serviço aqui.** O painel é gente; o token de serviço é do backend do
 *     agente. Qualquer `VITE_*` vai para dentro do bundle que o visitante baixa.
 */
export const BASE = (import.meta.env.VITE_CRM_API as string) || "http://localhost:8100";

export class ErroApi extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: Record<string, unknown> = {},
    readonly requestId = "",
  ) {
    super(message);
  }
}

type Opcoes = { metodo?: string; corpo?: unknown; versao?: number; chave?: string };

async function chamar<T>(rota: string, { metodo = "GET", corpo, versao, chave }: Opcoes = {}): Promise<T> {
  const cabecalhos: Record<string, string> = {};
  if (corpo !== undefined) cabecalhos["Content-Type"] = "application/json";
  if (versao !== undefined) cabecalhos["If-Match"] = `"${versao}"`;
  // A chave de idempotência descreve a AÇÃO LÓGICA. `crypto.randomUUID()` por clique é o certo
  // aqui: cada clique do corretor é uma ação nova. O que ela protege é o reenvio da MESMA
  // requisição — clique duplo, rede lenta, botão apertado de novo por impaciência.
  if (chave) cabecalhos["Idempotency-Key"] = chave;

  let r: Response;
  try {
    r = await fetch(`${BASE}${rota}`, {
      method: metodo,
      headers: cabecalhos,
      credentials: "include",
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
  } catch {
    // `fetch` rejeita sem status em falha de rede E em bloqueio de CORS, com a mesma mensagem
    // inútil ("failed to fetch"). Sem tratar aqui, o painel diria "não foi possível carregar" na
    // tela de login — e a pessoa iria procurar o erro na senha, que está certa.
    throw new ErroApi(0, "API_INACESSIVEL",
      `Não consegui falar com a API em ${BASE}. Verifique se ela está no ar e se este endereço está ` +
      "na lista de origens permitidas (CRM_ALLOWED_ORIGINS).");
  }

  if (r.status === 204) return undefined as T;
  const dados = await r.json().catch(() => ({}));
  if (!r.ok) {
    const e = dados?.error ?? {};
    throw new ErroApi(r.status, e.code ?? `HTTP_${r.status}`,
      e.message ?? "Não foi possível concluir.", e.details ?? {}, dados?.request_id ?? "");
  }
  return dados as T;
}

export type Pagina<T> = { items: T[]; next_cursor: string | null };
export type Envelope<T> = { data: T; request_id: string };

export const api = {
  entrar: (email: string, password: string) =>
    chamar<Envelope<{ id: string; name: string; role: string }>>("/v1/auth/login",
      { metodo: "POST", corpo: { email, password }, chave: crypto.randomUUID() }),
  sair: () => chamar<void>("/v1/auth/logout", { metodo: "POST", chave: crypto.randomUUID() }),
  eu: () => chamar<Envelope<Ator>>("/v1/auth/me"),

  painel: () => chamar<Envelope<Painel>>("/v1/dashboard"),

  leads: (q: Record<string, string | undefined>) =>
    chamar<Pagina<LeadResumo>>(`/v1/leads${consulta(q)}`),
  lead: (id: string) => chamar<Envelope<LeadDetalhe>>(`/v1/leads/${id}`),
  historico: (id: string) => chamar<Pagina<Interacao>>(`/v1/leads/${id}/interactions`),
  alterarLead: (id: string, corpo: Record<string, unknown>, versao: number) =>
    chamar<Envelope<LeadDetalhe>>(`/v1/leads/${id}`,
      { metodo: "PATCH", corpo, versao, chave: crypto.randomUUID() }),

  oportunidades: (q: Record<string, string | undefined>) =>
    chamar<Pagina<Oportunidade>>(`/v1/opportunities${consulta(q)}`),
  oportunidade: (id: string) => chamar<Envelope<OportunidadeDetalhe>>(`/v1/opportunities/${id}`),
  mover: (id: string, target_stage: string, reason: string | null, versao: number) =>
    chamar<Envelope<Oportunidade>>(`/v1/opportunities/${id}/transitions`,
      { metodo: "POST", corpo: { target_stage, reason }, versao, chave: crypto.randomUUID() }),

  imoveis: (q: Record<string, string | undefined>) => chamar<Pagina<Imovel>>(`/v1/properties${consulta(q)}`),

  visitas: (q: Record<string, string | undefined>) => chamar<Pagina<Visita>>(`/v1/visits${consulta(q)}`),
  moverVisita: (id: string, target_status: string, reason: string | null, versao: number) =>
    chamar<Envelope<Visita>>(`/v1/visits/${id}/transitions`,
      { metodo: "POST", corpo: { target_status, reason }, versao, chave: crypto.randomUUID() }),

  handoffs: (status: string) => chamar<Pagina<Handoff>>(`/v1/handoffs?status=${status}`),
  moverHandoff: (id: string, corpo: Record<string, unknown>, versao: number) =>
    chamar<Envelope<Handoff>>(`/v1/handoffs/${id}/transitions`,
      { metodo: "POST", corpo, versao, chave: crypto.randomUUID() }),

  tarefas: (q: Record<string, string | undefined>) => chamar<Pagina<Tarefa>>(`/v1/tasks${consulta(q)}`),
  auditoria: (q: Record<string, string | undefined>) => chamar<Pagina<Evento>>(`/v1/audit-events${consulta(q)}`),
};

function consulta(q: Record<string, string | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) if (v) p.set(k, v);
  const s = p.toString();
  return s ? `?${s}` : "";
}

// ---------------------------------------------------------------- tipos

export type Ator = { actor_type: string; id: string; name: string; role: string | null; scopes: string[] };
export type Painel = {
  por_estagio: Record<string, number>; leads_ativos: number; tarefas_vencidas: number;
  visitas_futuras: number; visitas_solicitadas: number; handoffs_pendentes: number;
  imoveis_disponiveis: number; generated_at: string;
};
export type LeadResumo = {
  id: string; name: string; email: string | null; phone_e164: string | null;
  external_contact_id: string | null; source: string; contact_policy: ContactPolicy;
  archived_at: string | null; created_at: string; version: number;
};
export type ContactPolicy = "unknown" | "allowed" | "blocked";
export type LeadDetalhe = LeadResumo & {
  opportunities: { id: string; purpose: Proposito; stage: Estagio; atendimento: Atendimento; version: number }[];
};
export type Proposito = "rent" | "buy";
export type Estagio = "new" | "in_service" | "qualified" | "visit_scheduled" | "negotiation" | "won" | "lost";
export type Atendimento = "agent" | "human_pending" | "human";
export type Oportunidade = {
  id: string; lead_id: string; lead_name?: string; purpose: Proposito; stage: Estagio;
  atendimento: Atendimento; lost_reason: string | null; created_at: string; version: number;
};
export type Preferencias = {
  city: string | null; neighborhoods: string[]; property_types: string[];
  budget_min_cents: number | null; budget_max_cents: number | null;
  budget_basis: "base_price" | "monthly_total"; bedrooms_min: number | null;
  parking_min: number | null; requirements: string[];
};
export type OportunidadeDetalhe = Oportunidade & {
  preferences: Preferencias | null;
  interests: { property_id: string; code: string; title: string; status: string; notes: string | null }[];
  visits: Visita[]; tasks: Tarefa[]; handoffs: Handoff[];
};
export type Imovel = {
  id: string; code: string; title: string; description: string | null; city: string;
  neighborhood: string; type: string; purpose: Proposito; bedrooms: number; parking: number;
  status: string; base_price_cents: number; monthly_total_cents: number | null;
  monthly_total_incomplete: boolean; monthly_missing: string[];
};
export type Visita = {
  id: string; opportunity_id: string; property_id: string; slot_id: string;
  status: "requested" | "confirmed" | "completed" | "cancelled" | "no_show";
  starts_at: string; ends_at: string; cancellation_reason: string | null; version: number;
};
export type Tarefa = {
  id: string; opportunity_id: string; title: string; kind: "follow_up" | "internal";
  due_at: string | null; status: "open" | "done" | "cancelled"; version: number;
};
export type Handoff = {
  id: string; opportunity_id: string; reason: string; summary: string;
  status: "pending" | "accepted" | "resolved"; lead_name?: string; lead_id?: string;
  stage?: Estagio; version: number;
};
export type Interacao = {
  id: string; channel: string; direction: "inbound" | "outbound" | "internal";
  summary: string; occurred_at: string; opportunity_id: string | null;
};
export type Evento = {
  id: string; actor_type: string; actor_name: string | null; action: string;
  entity_type: string; entity_id: string | null; occurred_at: string;
  changes_json: Record<string, unknown>;
};
