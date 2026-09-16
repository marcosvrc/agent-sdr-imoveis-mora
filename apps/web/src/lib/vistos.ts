/** "Vistos recentemente" — o dado já era coletado e nunca voltava para o visitante.
 *
 *  O servidor registra `viewed_imovel` por sessão assinada (eventos_navegacao) para o agente
 *  qualificar o lead. Isso é para o agente. Esta lista é para a PESSOA: fica no navegador dela,
 *  não sobe para lugar nenhum e some quando ela limpa o site — o que também é a resposta honesta
 *  para "por que vocês guardam meu histórico?".
 */
const CHAVE = "mora_vistos";
const MAX = 8;

const ler = (): string[] => {
  try { return JSON.parse(localStorage.getItem(CHAVE) ?? "[]"); } catch { return []; }
};

export function registrarVisto(id: string): void {
  try {
    const atual = ler().filter((x) => x !== id);
    localStorage.setItem(CHAVE, JSON.stringify([id, ...atual].slice(0, MAX)));
  } catch { /* navegação privada ou storage cheio: seguir sem histórico é aceitável */ }
}

export const idsVistos = (excluir?: string): string[] => ler().filter((x) => x !== excluir);

export function limparVistos(): void {
  try { localStorage.removeItem(CHAVE); } catch { /* idem */ }
}
