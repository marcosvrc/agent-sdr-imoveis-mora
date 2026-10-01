// Redesenha a conversa depois de recarregar a página.
//
// A sessão do chat fica na aba e sobrevive ao recarregar; as bolhas não. O cliente via só a
// saudação enquanto a Mora seguia a conversa de onde parou — falando de imóveis e horários que
// tinham sumido da tela. O servidor guarda o histórico; aqui ele volta a ser bolha.
import { nomeImovel, obterImovel } from "./api";
import { sessaoAtual } from "./session";
import type { ImovelCard, RespostaAgente } from "./ws";

const CANAL = import.meta.env.VITE_CANAL_URL ?? "http://localhost:8001";

export type MensagemSalva = {
  de: "lead" | "Mora" | "corretor";
  texto: string;
  em: string;
  opcoes: string[];
  imoveis: string[];
};

const AJUSTES: Record<string, string> = {
  preco: "Pode mostrar acima do valor",
  vizinhos: "Pode mostrar em bairros vizinhos",
  quartos: "Pode mostrar com menos quartos",
};

/** O que o cliente VIU no botão, e não o identificador que o botão mandou ao servidor. */
export function rotuloDoBotao(texto: string): string {
  if (texto.startsWith("slot:")) {
    const quando = new Date(texto.slice(5));
    if (!Number.isNaN(quando.getTime())) {
      const dia = quando.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit", timeZone: "America/Sao_Paulo" });
      const hora = quando.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" });
      return `${dia.replace(".", "")} às ${hora.replace(":00", "h")}`;
    }
  }
  if (texto.startsWith("imovel:")) return "Quero visitar este imóvel";
  if (texto.startsWith("ajuste:")) return AJUSTES[texto.slice(7).split("|")[0]] ?? "Pode ampliar a busca";
  return texto;
}

async function cartoes(ids: string[]): Promise<ImovelCard[]> {
  const lidos = await Promise.allSettled(ids.map((id) => obterImovel(id)));
  return lidos.flatMap((r) => (r.status === "fulfilled"
    ? [{ id: r.value.id, titulo: nomeImovel(r.value), preco: r.value.preco, foto: r.value.fotos?.[0] ?? null, motivo: "" }]
    : []));
}

/** Histórico da sessão atual, já no formato das bolhas. Sem sessão salva, devolve vazio — e não
 *  cria uma sessão só para perguntar (isso é trabalho da conexão). */
export async function carregarHistorico(): Promise<{ de: "lead" | "Mora"; texto: string; em: string; r?: RespostaAgente }[]> {
  const s = sessaoAtual();
  if (!s) return [];
  try {
    const resp = await fetch(`${CANAL}/historico`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: s.session_id, token: s.token }),
    });
    if (!resp.ok) return [];
    const { mensagens } = (await resp.json()) as { mensagens: MensagemSalva[] };
    return await Promise.all(mensagens.map(async (m, i) => {
      if (m.de === "lead") return { de: "lead" as const, texto: rotuloDoBotao(m.texto), em: m.em };
      const ultima = i === mensagens.length - 1;
      const imoveis = m.imoveis.length ? await cartoes(m.imoveis) : [];
      // Botões só na última mensagem: nas anteriores eles já foram respondidos.
      const r: RespostaAgente = { lead_id: "", texto: m.texto, opcoes: ultima ? m.opcoes : [], imoveis, acao: "" };
      return { de: "Mora" as const, texto: m.de === "corretor" ? `Corretor: ${m.texto}` : m.texto, em: m.em, r };
    }));
  } catch {
    return [];                                    // sem histórico, a conversa segue do ponto em que está
  }
}
