// Cliente WebSocket do widget. Recebe RespostaAgente {texto, opcoes, imoveis, acao}; o ChatWidget renderiza.
// Resiliência: mensagens digitadas offline entram numa fila e são enviadas na reconexão; o servidor
// confirma o recebimento ("recebido"), para o widget distinguir "não chegou" de "chegou e está processando".
//
// Protocolo: abre `?papel=lead` SEM credencial na URL (URL vai para log de proxy e de acesso) e manda
// `{session_id, token}` no primeiro quadro; o servidor responde `{"evento": "pronto"}` e só então a
// conexão está autenticada. Sessão recusada (inventada ou expirada) fecha com 4401.
import { descartarSessao, getSessao, type Sessao } from "./session";

export type ImovelCard = { id: string; titulo: string; preco: number; foto?: string | null; motivo: string };
export type RespostaAgente = { lead_id: string; texto: string; opcoes: string[]; imoveis: ImovelCard[]; acao: string; dados?: Record<string, unknown> };
export type EventoCanal = { evento: "recebido" | "falha_envio" | "pronto"; ref?: string; texto?: string };
export type Status = "on" | "off";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8001/ws";

/** O que fica na fila: o session_id NÃO entra aqui. Mensagem digitada antes de existir sessão
 *  ficava gravada com `session_id: ""`, e na reconexão o servidor a descartava sem aviso. Ele só é
 *  preenchido no envio real, com a sessão que a conexão aberta autenticou. */
type Pendente = { texto: string; meta: Record<string, unknown>; ref: string };

export function conectar(
  onMensagem: (r: RespostaAgente) => void,
  onStatus?: (s: Status) => void,
  onEvento?: (e: EventoCanal) => void,
) {
  let ws: WebSocket | null = null;
  let sessao: Sessao | null = null;                // a sessão que ESTA conexão autenticou
  let pronto = false;                              // credencial aceita: já dá para escrever
  let fechado = false;
  let tentativas = 0;
  let espera: number | undefined;
  const fila: Pendente[] = [];                     // o que o usuário mandou enquanto estava desconectado

  const enviarAgora = (m: Pendente) => ws!.send(JSON.stringify({ session_id: sessao!.session_id, ...m }));
  const podeEnviar = () => pronto && sessao !== null && ws?.readyState === WebSocket.OPEN;
  const escoar = () => { while (fila.length && podeEnviar()) enviarAgora(fila.shift()!); };

  const reagendar = () => {
    if (fechado) return;
    tentativas += 1;                               // backoff: 1s, 2s, 4s… até 15s, para não martelar o servidor
    espera = window.setTimeout(abrir, Math.min(1000 * 2 ** (tentativas - 1), 15000));
  };

  const abrir = async () => {
    let atual: Sessao;
    try {
      atual = await getSessao();                   // o servidor emite o id; o navegador não escolhe o seu
    } catch {
      onStatus?.("off");
      reagendar();
      return;
    }
    if (fechado) return;
    const sock = new WebSocket(`${WS_URL}?papel=lead`);
    ws = sock;
    pronto = false;
    sock.onopen = () => sock.send(JSON.stringify({ session_id: atual.session_id, token: atual.token }));
    sock.onmessage = (e) => {
      // Um quadro ilegível (proxy no meio, servidor em versão nova) não pode derrubar o handler:
      // sem o try, a exceção parava aqui e as mensagens seguintes também se perdiam.
      let d: unknown;
      try { d = JSON.parse(e.data); } catch { return; }
      if (!d || typeof d !== "object") return;
      const ev = d as EventoCanal;
      if (ev.evento === "pronto") {
        sessao = atual;
        pronto = true;
        tentativas = 0;
        onStatus?.("on");
        escoar();                                  // só agora: antes do `pronto`, um 4401 levaria a fila junto
        return;
      }
      if (ev.evento) onEvento?.(ev);
      else onMensagem(d as RespostaAgente);
    };
    sock.onclose = (e) => {
      if (ws !== sock) return;                     // conexão antiga, já substituída
      pronto = false;
      onStatus?.("off");
      // 4401: a sessão venceu (12 h) ou o servidor trocou o segredo. Reconectar com o mesmo token
      // era "reconectando…" para sempre; descarta e a próxima tentativa pede uma sessão nova.
      if (e.code === 4401) descartarSessao(atual.session_id);
      reagendar();
    };
  };
  abrir();

  return {
    /** Devolve a referência da mensagem; o widget usa para casar com o "recebido". */
    enviar: (texto: string, meta: Record<string, unknown> = {}) => {
      const m: Pendente = { texto, meta, ref: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}` };
      if (podeEnviar()) enviarAgora(m);
      else fila.push(m);                           // nada é descartado em silêncio
      return m.ref;
    },
    conectado: () => podeEnviar(),
    pendentes: () => fila.length,
    fechar: () => { fechado = true; clearTimeout(espera); ws?.close(); },
  };
}
