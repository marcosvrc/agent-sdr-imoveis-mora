import { token } from "./auth";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { ...init, headers: { "content-type": "application/json", Authorization: `Bearer ${token()}`, ...(init.headers ?? {}) } });
  if (r.status === 401) { window.location.href = "/login"; throw new Error("não autenticado"); }
  if (!r.ok) {
    let detalhe = `${r.status} ${path}`;
    try { const j = await r.json(); if (j?.detail) detalhe = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* sem corpo */ }
    throw new Error(detalhe);
  }
  return r.status === 204 ? (undefined as T) : r.json();
}

export type Cartao = { intencao: string; regiao?: string; bairros: string[]; preco_min?: number; preco_max?: number; quartos?: number; tipo_imovel?: string; urgencia?: string;
  perfil_investidor?: string; ticket?: number; retorno_esperado?: string; imoveis_visualizados: string[]; pediu_visita: boolean };
export type AnaliseLead = { sentimento: string; sentimento_tendencia: string; confianca: number; engajamento: string; perfil_decisao: string; estilo_comunicacao: string;
  motivadores: string[]; objecoes: string[]; sinais_alerta: string[]; como_abordar: string[]; resumo_perfil: string };
export type Lead = { id: string; cliente_id?: string | null; outras_oportunidades?: Oportunidade[]; nome?: string; telefone?: string; estagio: string; temperatura: "quente" | "morno" | "frio"; score: number; cartao: Cartao;
  corretor_id?: string | null; corretor_nome?: string | null; resumo?: string; analise?: AnaliseLead | null; analisado_em?: string | null; analise_solicitada_em?: string | null; followups_enviados: number; criado_em: string; ultima_mensagem_em?: string; aceita_reativacao?: boolean; reativado_em?: string | null; canais?: { canal: string; identificador: string }[] };
export type Mensagem = { id: number; canal: string; direcao: "in" | "out" | "corretor"; conteudo: string; meta: Record<string, unknown>; em: string };
export type Atividade = { id: number; lead_id: string; nome?: string; canal: string; direcao: "in" | "out" | "corretor"; conteudo: string; em: string };
export type Funil = { estagios: Record<string, number>; temperaturas: Record<string, number> };
export type Visita = { id: string; lead_id: string; nome?: string; imovel_id?: string; bairro?: string; tipo: string; inicio: string; status: string; corretor_id?: string | null; corretor_nome?: string | null };
export type Imovel = { id: string; tipo: string; operacao: string; cidade: string; regiao: string; bairro: string; quartos: number; suites: number; vagas: number; area_m2: number; preco: number; condominio?: number | null; descricao: string; fotos: string[]; destaque_investimento: boolean };
export type Corretor = { id: string; nome: string; email?: string | null; telefone?: string | null; regioes: string[]; ativo: boolean; foto?: string | null; criado_em?: string; leads_handoff?: number; visitas?: number };
export type CorretorIn = Omit<Corretor, "id" | "criado_em" | "leads_handoff" | "visitas">;

export type AvisoReativacao = { lead_id: string; nome?: string | null; temperatura?: string | null; em: string;
  imovel_id?: string | null; bairro?: string | null; tipo?: string | null; preco?: number | null; motivos: string[]; respondeu: boolean; visitou: boolean };
export type ResumoReativacao = { dias: number; janela_resposta_h: number; avisos: number; leads: number; imoveis: number;
  responderam: number; visitas: number; saidas: number;
  taxa_resposta: number | null; taxa_visita: number | null; taxa_saida: number | null;
  selecao: { avaliados: number; avisados: number; sem_canal: number; anuncios: number };
  ultimos: AvisoReativacao[] };
export type Kpi = { atual: number; anterior: number };
export type Metricas = {
  periodo_dias: number; gerado_em: string;
  kpis: { leads: Kpi; qualificados: Kpi; visitas: Kpi; handoffs: Kpi; msgs_in: Kpi; msgs_out: Kpi; resposta_seg: { atual: number | null; anterior: number | null } };
  pipeline: { por_estagio: Record<string, { n: number; valor: number }>; ticket_medio: number | null; valor_visitas: number; total_ativo: number };
  serie: { dia: string; leads: number; visitas: number; mensagens: number }[];
  por_canal: Record<string, number>; por_regiao: Record<string, number>; por_intencao: Record<string, number>; temperaturas: Record<string, number>;
  totais: { leads: number; imoveis: number; visitas_futuras: number; corretores: number };
};
export type UsoKpi = { atual: number; anterior: number };
export type LinhaUso = { chave: string; chamadas: number; tokens: number; custo: number; latencia: number };
export type ChamadaLLM = { id: number; em: string; lead_id?: string | null; no?: string | null; papel?: string | null; modelo: string;
  tokens_entrada: number; tokens_saida: number; tokens_cache_leitura: number; custo_usd: number; latencia_ms?: number | null; erro?: string | null };
export type Limites = { orcamento_mensal_usd: number; teto_tokens_dia: number; alerta_pct: number; acao_ao_estourar: "degradar" | "alertar" | "bloquear"; cotacao_brl: number };
export type EstadoOrcamento = { limites: Limites; gasto_mes_usd: number; tokens_hoje: number; pct_orcamento: number; pct_tokens: number; pct: number;
  em_alerta: boolean; estourado: boolean; acao: string; modo: "normal" | "degradado" | "bloqueado" };
export type Uso = {
  periodo_dias: number; gerado_em: string;
  kpis: { chamadas: UsoKpi; tokens: UsoKpi; entrada: UsoKpi; saida: UsoKpi; cache_leitura: UsoKpi; custo: UsoKpi; latencia: UsoKpi; erros: UsoKpi; leads: UsoKpi; custo_por_lead: UsoKpi };
  serie: { dia: string; entrada: number; saida: number; custo: number }[];
  por_modelo: LinhaUso[]; por_no: LinhaUso[]; por_papel: LinhaUso[]; recentes: ChamadaLLM[];
  consumo: { gasto_mes_usd: number; tokens_hoje: number };
  orcamento: EstadoOrcamento;
  configuracao_atual: { provider: string; modelo_conversa: string; modelo_roteamento: string; embeddings: string };
};
export type StatusCalendario = { disponivel: boolean; corretores: Record<string, boolean> };
export type Notificacao = { id: number; corretor_id?: string | null; tipo: string; titulo: string;
  detalhe?: string | null; lead_id?: string | null; lead_nome?: string | null;
  dados: Record<string, unknown>; criada_em: string; lida_em?: string | null };
export type ClienteLinha = { id: string; nome?: string | null; telefone?: string | null; email?: string | null;
  criado_em: string; atualizado_em?: string | null; oportunidades: number; abertas: number; ultima_atividade?: string | null };
export type Oportunidade = { id: string; estagio: string; temperatura: string; score: number; cartao: Cartao | null;
  corretor_id?: string | null; corretor_nome?: string | null; resumo?: string | null; criado_em: string;
  ultima_mensagem_em?: string | null; encerrado_em?: string | null; sucessora_id?: string | null;
  mensagens: number; visitas: number };
export type FichaCliente = { cliente: ClienteLinha; oportunidades: Oportunidade[]; total_oportunidades: number; intencoes: string[] };
export type RegistroAuditoria = { id: number; em: string; ator_tipo: string; ator_id?: string | null; ator_nome?: string | null;
  acao: string; entidade: string; entidade_id?: string | null; dados: Record<string, unknown>; origem?: string | null;
  resultado: string; detalhe?: string | null };
export type ResumoAuditoria = { periodo_dias: number; total: number; erros: number; sensiveis: number;
  por_acao: { acao: string; n: number }[]; por_ator: { ator_tipo: string; ator: string; n: number }[];
  acoes_conhecidas: string[]; entidades_conhecidas: string[] };
export type Auditoria = { registros: RegistroAuditoria[]; resumo: ResumoAuditoria; acoes_sensiveis: string[] };
export type PreviaFollowup = { temperatura: string; politica: Record<string, unknown>;
  previa: { tentativa: number; minutos: number; em: string }[] };
export type Precos = { precos: Record<string, number[]>; defaults: Record<string, number[]>; personalizados: string[] };

export type Saude = {
  horas: number;
  turnos: { total: number; p50_ms: number; p95_ms: number; pior_ms: number; taxa_falha: number; acima_de_30s: number;
    por_resultado: Record<string, number>;
    serie: { hora: string; turnos: number; p95_ms: number; falhas: number }[] };
  amostra: { em: string; filas: Record<string, number>; conexoes_db: number | null } | null;
  servicos: { servico: string; em: string; ha_segundos: number; vivo: boolean; detalhe: Record<string, unknown> }[];
};

/** Vínculo lead↔imóvel. `sugerido` é escrito pelo agente; o corretor move para os demais. */
export type SituacaoInteresse = "sugerido" | "interessado" | "descartado" | "visita_marcada";

export type Interesse = {
  imovel_id: string; situacao: SituacaoInteresse; origem: "agente" | "site" | "corretor";
  motivo: string | null; criado_em: string; atualizado_em: string;
  tipo: string; bairro: string; operacao: string; preco: number; quartos: number; area_m2: number;
};

export type Interessado = {
  lead_id: string; situacao: SituacaoInteresse; origem: string; atualizado_em: string;
  nome: string | null; telefone: string | null; estagio: string; temperatura: string;
  score: number; corretor_id: string | null;
};

/** Simulação (modo seco) do aviso de imóvel novo: quem seria avisado, quem não, e por quê. */
export type Reativacao = {
  imovel_id: string; avaliados: number; pontos_minimos: number;
  candidatos: { lead_id: string; nome: string | null; telefone: string | null; temperatura: string;
                score: number; estagio: string; pontos: number; motivos: string[] }[];
  excluidos: { lead_id: string; nome: string | null; motivo: string }[];
};

export type Carteira = { leads: number; visitas: number };

export type Config = { config: Record<string, Record<string, unknown>>; defaults: Record<string, Record<string, unknown>>;
  canais: { telegram: { configurado: boolean; usuario?: string | null }; whatsapp: { configurado: boolean; numero?: string | null }; web: { configurado: boolean }; llm: { provider: string; modelo_conversa: string; modelo_roteamento: string; fallback?: string | null;
    efetivo: Record<string, { modelo: string; provider: string; origem: "painel" | "ambiente" }> }; embeddings: { provider: string } } };

const qs = (o: Record<string, string | number | undefined>) => { const p = new URLSearchParams(); for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== "") p.set(k, String(v)); const s = p.toString(); return s ? `?${s}` : ""; };

export const api = {
  funil: () => req<Funil>("/dashboard/funil"),
  metricas: (dias: number) => req<Metricas>(`/dashboard/metricas${qs({ dias })}`),
  saude: (horas: number) => req<Saude>(`/dashboard/saude${qs({ horas })}`),
  visitas: () => req<Visita[]>("/dashboard/visitas"),
  atividade: () => req<Atividade[]>("/dashboard/atividade"),
  leads: (f: { estagio?: string; temperatura?: string; corretor_id?: string } = {}) => req<Lead[]>(`/leads${qs(f)}`),
  analisarLead: (id: string) => req<{ status: string }>(`/leads/${id}/analisar`, { method: "POST" }),
  atribuirCorretor: (id: string, corretor_id: string | null) => req<{ corretor_id: string | null; corretor_nome: string | null }>(`/leads/${id}/corretor`, { method: "PUT", body: JSON.stringify({ corretor_id }) }),
  definirReativacao: (id: string, aceita: boolean) =>
    req<{ lead_id: string; aceita_reativacao: boolean }>(`/leads/${id}/reativacao`, { method: "PUT", body: JSON.stringify({ aceita }) }),
  lead: (id: string) => req<Lead>(`/leads/${id}`),
  mensagens: (id: string) => req<Mensagem[]>(`/leads/${id}/mensagens`),
  assumir: (id: string, corretor_id?: string | null) => req<{ corretor_id: string | null; corretor_nome: string | null }>(`/handoff/${id}/assumir`, { method: "POST", body: JSON.stringify({ corretor_id: corretor_id ?? null }) }),
  responder: (id: string, texto: string) => req(`/handoff/${id}/responder`, { method: "POST", body: JSON.stringify({ texto }) }),
  devolver: (id: string) => req(`/handoff/${id}/devolver`, { method: "POST" }),
  crmSync: () => req<{ exportados: number }>("/leads/crm/sync", { method: "POST" }),
  imoveis: (f: { operacao?: string; regiao?: string; preco_max?: number; quartos?: number; limite?: number } = {}) => req<Imovel[]>(`/imoveis${qs({ limite: 200, ...f })}`),
  imovel: (id: string) => req<Imovel>(`/imoveis/${id}`),
  enviarFotoImovel: (id: string, imagem: string) => req<Imovel>(`/imoveis/${id}/fotos`, { method: "POST", body: JSON.stringify({ imagem }) }),
  removerFotoImovel: (id: string, url: string) => req<Imovel>(`/imoveis/${id}/fotos/${url.split("/").pop()}`, { method: "DELETE" }),
  reordenarFotosImovel: (id: string, fotos: string[]) => req<Imovel>(`/imoveis/${id}/fotos`, { method: "PUT", body: JSON.stringify({ fotos }) }),
  corretores: () => req<Corretor[]>("/corretores"),
  criarCorretor: (c: CorretorIn) => req<Corretor>("/corretores", { method: "POST", body: JSON.stringify(c) }),
  atualizarCorretor: (id: string, c: CorretorIn) => req<Corretor>(`/corretores/${id}`, { method: "PUT", body: JSON.stringify(c) }),
  simularReativacao: (imovelId: string) => req<Reativacao>(`/reativacao/imovel/${imovelId}`),
  resumoReativacao: (dias = 30) => req<ResumoReativacao>(`/dashboard/reativacao?dias=${dias}`),
  interessesDoLead: (leadId: string) => req<Interesse[]>(`/interesses/lead/${leadId}`),
  interessadosNoImovel: (imovelId: string) => req<Interessado[]>(`/interesses/imovel/${imovelId}`),
  mudarInteresse: (leadId: string, imovelId: string, situacao: SituacaoInteresse) =>
    req<Interesse>(`/interesses/${leadId}/${imovelId}`, { method: "PUT", body: JSON.stringify({ situacao }) }),
  carteiraCorretor: (id: string) => req<Carteira>(`/corretores/${id}/carteira`),
  // DELETE agora desativa e move a carteira; `remover_cadastro` só passa com a carteira vazia.
  desativarCorretor: (id: string, destino: string, removerCadastro = false) =>
    req<{ acao: string; destino: string; movido: { leads: number; visitas: number } }>(
      `/corretores/${id}${qs({ destino, remover_cadastro: removerCadastro ? "true" : undefined })}`, { method: "DELETE" }),
  config: () => req<Config>("/config"),
  uso: (dias: number) => req<Uso>(`/governanca/uso${qs({ dias })}`),
  limites: () => req<{ limites: Limites; defaults: Limites; estado: EstadoOrcamento }>("/governanca/limites"),
  salvarLimites: (l: Limites) => req<{ limites: Limites; estado: EstadoOrcamento }>("/governanca/limites", { method: "PUT", body: JSON.stringify(l) }),
  precos: () => req<Precos>("/governanca/precos"),
  salvarPreco: (modelo: string, p: { entrada: number; saida: number; cache_escrita: number; cache_leitura: number }) =>
    req(`/governanca/precos/${encodeURIComponent(modelo)}`, { method: "PUT", body: JSON.stringify(p) }),
  restaurarPreco: (modelo: string) => req<void>(`/governanca/precos/${encodeURIComponent(modelo)}`, { method: "DELETE" }),
  statusCalendario: () => req<StatusCalendario>("/calendario/status"),
  conectarCalendario: (id: string) => req<{ url: string }>(`/calendario/conectar/${id}`, { method: "POST" }),
  desconectarCalendario: (id: string) => req<void>(`/calendario/${id}`, { method: "DELETE" }),
  notificacoes: (apenas_nao_lidas = false) =>
    req<{ notificacoes: Notificacao[]; nao_lidas: number }>(`/notificacoes${qs({ apenas_nao_lidas: apenas_nao_lidas ? "true" : "" })}`),
  marcarNotificacaoLida: (id: number) => req<void>(`/notificacoes/${id}/lida`, { method: "POST" }),
  marcarNotificacoesLidas: () => req<{ marcadas: number }>("/notificacoes/lidas", { method: "POST" }),
  clientes: (busca?: string) => req<ClienteLinha[]>(`/clientes${qs({ busca })}`),
  cliente: (id: string) => req<FichaCliente>(`/clientes/${id}`),
  auditoria: (f: { dias: number; acao?: string; entidade?: string; ator?: string; so_sensiveis?: boolean; busca?: string }) =>
    req<Auditoria>(`/auditoria${qs({ ...f, so_sensiveis: f.so_sensiveis ? "true" : "" })}`),
  exportarAuditoria: async (f: { dias: number; acao?: string; entidade?: string }) => {
    // download autenticado: o Authorization não cabe num <a href>, então baixa o blob e entrega ao navegador
    const r = await fetch(`${BASE}/auditoria/exportar${qs(f)}`, { headers: { Authorization: `Bearer ${token()}` } });
    if (!r.ok) throw new Error(`falha ao exportar (${r.status})`);
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a");
    a.href = url; a.download = `auditoria-${f.dias}d.csv`; a.click();
    URL.revokeObjectURL(url);
  },
  previaFollowup: (temperatura = "morno") => req<PreviaFollowup>(`/config/followup/previa${qs({ temperatura })}`),
  salvarConfig: (chave: string, valor: Record<string, unknown>) => req<{ chave: string; valor: Record<string, unknown> }>(`/config/${chave}`, { method: "PUT", body: JSON.stringify(valor) }),
  restaurarConfig: (chave: string) => req<void>(`/config/${chave}`, { method: "DELETE" }),
  testarModelo: (modelo: string, provider?: string) => req<{ ok: boolean; latencia_ms: number; resposta?: string; erro?: string; tem_preco: boolean }>(
    "/config/modelos/testar", { method: "POST", body: JSON.stringify({ modelo, provider }) }),
};

export { brl } from "./format";
export const ESTAGIOS = ["novo", "qualificando", "qualificado", "agendado", "handoff", "inativo", "frio"];
export const ROTULO: Record<string, string> = { novo: "Novo", qualificando: "Qualificando", qualificado: "Qualificado", agendado: "Agendado", handoff: "Com corretor", inativo: "Inativo", frio: "Frio" };
export const REGIOES = ["zona_sul", "zona_oeste", "zona_norte", "zona_leste", "centro"];
