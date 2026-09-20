// Tempo real: mesma API WebSocket dos canais, com papel=dashboard. Recebe {evento:"mensagem", identificador, resposta}.
// A credencial da equipe vai no PRIMEIRO quadro depois de abrir, nunca na URL: query string fica em
// log de proxy, no histórico do navegador e no Referer — e este token é o de todo mundo, de longa
// duração. O servidor responde {evento:"pronto"} quando aceita e fecha com 4403 quando não;
// só depois do "pronto" a tela se considera conectada. Ver services/channels/local/app.py.
import { useEffect } from "react";
import { token } from "./auth";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8001/ws";
const RECUSADO = 4403;
export type EventoTempoReal = { evento: string; identificador?: string; resposta?: { lead_id: string; texto: string } };

export function useTempoReal(onEvento: (e: EventoTempoReal) => void, onStatus?: (conectado: boolean) => void) {
  useEffect(() => {
    let ws: WebSocket; let ativo = true;
    const abrir = () => {
      ws = new WebSocket(`${WS_URL}?papel=dashboard&id=painel`);
      ws.onopen = () => ws.send(JSON.stringify({ token: token() ?? "" }));
      ws.onmessage = (e) => {
        const ev: EventoTempoReal = JSON.parse(e.data);
        if (ev.evento === "pronto") { onStatus?.(true); return; }
        onEvento(ev);
      };
      // Queda de rede reconecta em 2s. Credencial recusada espera mais: insistir a cada 2s só
      // repetiria a recusa — e o log do servidor encheria de 4403 de uma única aba.
      ws.onclose = (e) => {
        onStatus?.(false);
        if (ativo) setTimeout(abrir, e.code === RECUSADO ? 30_000 : 2000);
      };
    };
    abrir();
    return () => { ativo = false; ws?.close(); };
  }, [onEvento, onStatus]);
}
