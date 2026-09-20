/** Formatação — o lugar onde o vocabulário técnico vira português. */
import type { Atendimento, Estagio, Proposito } from "./api";

/** Centavos → R$. Dividir por 100 aqui, e só aqui: espalhar essa divisão pela interface é como
 *  um valor acaba dez vezes maior numa tela e certo em todas as outras. */
export function brl(centavos: number | null | undefined, curto = false): string {
  if (centavos == null) return "—";
  const v = centavos / 100;
  if (curto && v >= 1_000_000) return `R$ ${(v / 1_000_000).toFixed(1).replace(".", ",")} mi`;
  if (curto && v >= 1000) return `R$ ${Math.round(v / 1000)} mil`;
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
}

/** UTC no banco, America/Sao_Paulo na tela (seção 1 da especificação). */
const FUSO = "America/Sao_Paulo";

export function dataHora(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", { timeZone: FUSO, dateStyle: "short", timeStyle: "short" });
}

export function relativo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 1) return "agora";
  if (min < 60) return `há ${min} min`;
  if (min < 60 * 24) return `há ${Math.round(min / 60)} h`;
  const dias = Math.round(min / 1440);
  return dias <= 30 ? `há ${dias} d` : dataHora(iso);
}

export const ESTAGIOS: { k: Estagio; r: string; ajuda: string; encerrado?: true }[] = [
  { k: "new", r: "Novo", ajuda: "Chegou e ainda ninguém falou com ele." },
  { k: "in_service", r: "Em atendimento", ajuda: "Conversa começou; o cartão ainda está incompleto." },
  { k: "qualified", r: "Qualificado", ajuda: "Já se sabe cidade, finalidade e teto de orçamento." },
  { k: "visit_scheduled", r: "Visita marcada", ajuda: "Tem visita confirmada no futuro." },
  { k: "negotiation", r: "Negociação", ajuda: "Proposta em discussão — só uma pessoa move para cá." },
  { k: "won", r: "Ganho", ajuda: "Fechou.", encerrado: true },
  { k: "lost", r: "Perdido", ajuda: "Encerrado, com motivo registrado.", encerrado: true },
];

export const ENCERRADOS = new Set(ESTAGIOS.filter((e) => e.encerrado).map((e) => e.k));

/** Dias desde a última mexida na oportunidade (`updated_at`).
 *
 *  É "parada há", e não "existe há": `created_at` responderia a pergunta errada — uma oportunidade
 *  aberta há seis meses e trabalhada ontem não está esquecida, e é a esquecida que se quer achar.
 */
export function diasParado(iso: string | null | undefined): number | null {
  if (!iso) return null;
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
}

/** A partir de quantos dias sem movimento a oportunidade vira um alerta na tela.
 *
 *  Sete e quinze, e não um número só, porque "parado" não é um estado binário: sete dias é o prazo
 *  em que ainda dá para retomar sem constrangimento, quinze é quando o cliente já procurou outro
 *  lugar. Estágio encerrado nunca acende — ganho de três meses atrás não está "esquecido", está
 *  pronto, e marcá-lo de amarelo ensinaria a ignorar a cor. */
export const PARADO_ATENCAO = 7;
export const PARADO_GRAVE = 15;

export function tomDoParado(dias: number | null, estagio: Estagio): "neutro" | "alerta" | "ruim" | null {
  if (dias === null || ENCERRADOS.has(estagio)) return null;
  if (dias >= PARADO_GRAVE) return "ruim";
  if (dias >= PARADO_ATENCAO) return "alerta";
  return "neutro";
}

export const NOME_ESTAGIO = Object.fromEntries(ESTAGIOS.map((e) => [e.k, e.r])) as Record<Estagio, string>;

export const PROPOSITO: Record<Proposito, string> = { rent: "Aluguel", buy: "Compra" };

export const ATENDIMENTO: Record<Atendimento, { r: string; tom: "neutro" | "alerta" | "info" }> = {
  agent: { r: "Mora (agente)", tom: "neutro" },
  human_pending: { r: "Aguardando corretor", tom: "alerta" },
  human: { r: "Com o corretor", tom: "info" },
};

export const POLITICA_CONTATO: Record<string, { r: string; tom: "neutro" | "bom" | "ruim" }> = {
  unknown: { r: "Sem autorização registrada", tom: "neutro" },
  allowed: { r: "Contato liberado", tom: "bom" },
  blocked: { r: "Pediu para não ser contatado", tom: "ruim" },
};

export const STATUS_VISITA: Record<string, { r: string; tom: "neutro" | "bom" | "alerta" | "ruim" }> = {
  requested: { r: "Solicitada", tom: "alerta" },
  confirmed: { r: "Confirmada", tom: "bom" },
  completed: { r: "Concluída", tom: "neutro" },
  cancelled: { r: "Cancelada", tom: "ruim" },
  no_show: { r: "Não compareceu", tom: "ruim" },
};

/** O que o corretor pode fazer com uma visita, a partir do estado atual. Espelha a tabela do
 *  servidor de propósito — mas esconder o botão NÃO é controle de acesso: quem recusa é a API. */
export const PROXIMAS_VISITA: Record<string, { alvo: string; r: string; pedeMotivo?: boolean }[]> = {
  requested: [
    { alvo: "confirmed", r: "Confirmar" },
    { alvo: "cancelled", r: "Cancelar", pedeMotivo: true },
  ],
  confirmed: [
    { alvo: "completed", r: "Concluir" },
    { alvo: "no_show", r: "Não compareceu" },
    { alvo: "cancelled", r: "Cancelar", pedeMotivo: true },
  ],
  completed: [], cancelled: [], no_show: [],
};
