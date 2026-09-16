import { create } from "zustand";

// Resumo mínimo do imóvel que o cliente estava vendo — só o que cabe numa frase de saudação.
// O backend já recebe o imóvel completo via meta.imovel_origem (handler.py); isto aqui é só
// para a bolha inicial do chat já nascer falando daquele imóvel, sem esperar o cliente digitar.
export type ImovelResumo = { id: string; tipo: string; bairro: string; operacao: string; preco: number };

// Estado do painel de chat, fora do <Outlet>: sobrevive à navegação entre páginas — o visitante não
// perde a conversa com a Mora ao clicar de "Imóveis" para a home, por exemplo.
type EstadoChat = {
  aberto: boolean;
  jaAbriu: boolean;             // o widget só monta (e conecta o WebSocket) na primeira abertura
  imovelOrigem?: string;
  imovelResumo?: ImovelResumo;
  abrir: (imovelOrigem?: string, imovelResumo?: ImovelResumo) => void;
  fechar: () => void;
  alternar: () => void;
};

export const useChat = create<EstadoChat>((set) => ({
  aberto: false,
  jaAbriu: false,
  imovelOrigem: undefined,
  imovelResumo: undefined,
  abrir: (imovelOrigem, imovelResumo) => set((s) => ({
    aberto: true, jaAbriu: true,
    imovelOrigem: imovelOrigem ?? s.imovelOrigem,
    imovelResumo: imovelResumo ?? s.imovelResumo,
  })),
  fechar: () => set({ aberto: false }),
  alternar: () => set((s) => ({ aberto: !s.aberto, jaAbriu: true })),
}));
