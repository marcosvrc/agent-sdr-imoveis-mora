// Tempo real: mesma API WebSocket dos canais, com papel=dashboard. Recebe {evento:"mensagem", identificador, resposta}.
// O token vai junto porque esta conexão espelha as conversas de todos os leads — o servidor recusa
// (código 4403) quem chega sem credencial da equipe. Ver shared/sdr_shared/seguranca/painel.py.
import { useEffect } from "react";
import { token } from "./auth";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8001/ws";
export type EventoTempoReal = { evento: string; identificador?: string; resposta?: { lead_id: string; texto: string } };

export function useTempoReal(onEvento: (e: EventoTempoReal) => void, onStatus?: (conectado: boolean) => void) {
  useEffect(() => {
    let ws: WebSocket; let ativo = true;
    const abrir = () => {
      ws = new WebSocket(`${WS_URL}?papel=dashboard&id=painel&token=${encodeURIComponent(token() ?? "")}`);
      ws.onopen = () => onStatus?.(true);
      ws.onmessage = (e) => onEvento(JSON.parse(e.data));
      ws.onclose = () => { onStatus?.(false); if (ativo) setTimeout(abrir, 2000); };
    };
    abrir();
    return () => { ativo = false; ws?.close(); };
  }, [onEvento, onStatus]);
}
