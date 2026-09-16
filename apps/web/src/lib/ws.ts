// Cliente WebSocket do widget. Recebe RespostaAgente {texto, opcoes, imoveis, acao}; o ChatWidget renderiza.
// Resiliência: mensagens digitadas offline entram numa fila e são enviadas na reconexão; o servidor
// confirma o recebimento ("recebido"), para o widget distinguir "não chegou" de "chegou e está processando".
import { getSessao, sessaoAtual } from "./session";

export type ImovelCard = { id: string; titulo: string; preco: number; foto?: string | null; motivo: string };
export type RespostaAgente = { lead_id: string; texto: string; opcoes: string[]; imoveis: ImovelCard[]; acao: string; dados?: Record<string, unknown> };
export type EventoCanal = { evento: "recebido" | "falha_envio"; ref?: string; texto?: string };
export type Status = "on" | "off";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8001/ws";

export function conectar(
  onMensagem: (r: RespostaAgente) => void,
  onStatus?: (s: Status) => void,
  onEvento?: (e: EventoCanal) => void,
) {
  let ws: WebSocket | null = null;
  let fechado = false;
  let tentativas = 0;
  const fila: string[] = [];                       // o que o usuário mandou enquanto estava desconectado

  const escoar = () => {
    while (fila.length && ws?.readyState === WebSocket.OPEN) ws.send(fila.shift()!);
  };

  const abrir = async () => {
    let sessao;
    try {
      sessao = await getSessao();                  // o servidor emite o id; o navegador não escolhe o seu
    } catch {
      onStatus?.("off");
      tentativas += 1;
      if (!fechado) setTimeout(abrir, Math.min(1000 * 2 ** (tentativas - 1), 15000));
      return;
    }
    if (fechado) return;
    ws = new WebSocket(`${WS_URL}?papel=lead&id=${sessao.session_id}&token=${encodeURIComponent(sessao.token)}`);
    ws.onopen = () => { tentativas = 0; onStatus?.("on"); escoar(); };
    ws.onmessage = (e) => {
      const d = JSON.parse(e.data);
      if (d?.evento) onEvento?.(d as EventoCanal);
      else onMensagem(d as RespostaAgente);
    };
    ws.onclose = () => {
      onStatus?.("off");
      if (fechado) return;
      tentativas += 1;                             // backoff: 1s, 2s, 4s… até 15s, para não martelar o servidor
      setTimeout(abrir, Math.min(1000 * 2 ** (tentativas - 1), 15000));
    };
  };
  abrir();

  return {
    /** Devolve a referência da mensagem; o widget usa para casar com o "recebido". */
    enviar: (texto: string, meta: Record<string, unknown> = {}) => {
      const ref = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const payload = JSON.stringify({ session_id: sessaoAtual()?.session_id ?? "", texto, meta, ref });
      if (ws?.readyState === WebSocket.OPEN) ws.send(payload);
      else fila.push(payload);                     // nada é descartado em silêncio
      return ref;
    },
    conectado: () => ws?.readyState === WebSocket.OPEN,
    pendentes: () => fila.length,
    fechar: () => { fechado = true; ws?.close(); },
  };
}
