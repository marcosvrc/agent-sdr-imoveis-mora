import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

/** Atrasa o valor até a digitação parar.
 *
 *  Sem isto, cada tecla vira uma consulta: digitar "Marcos" dispara seis requisições, a lista
 *  pisca seis vezes e a resposta que chega por último não é necessariamente a do texto que está
 *  no campo — respostas fora de ordem mostram o resultado de "Marc" com "Marcos" escrito na tela.
 */
export function useAtraso<T>(valor: T, ms = 350): T {
  const [atrasado, setAtrasado] = useState(valor);
  useEffect(() => {
    const t = setTimeout(() => setAtrasado(valor), ms);
    return () => clearTimeout(t);
  }, [valor, ms]);
  return atrasado;
}

/** Filtros guardados na barra de endereços, e não só no estado do React.
 *
 *  Três coisas que passam a funcionar sozinhas por causa disso, e que ninguém programa uma a uma:
 *  o botão voltar do navegador desfaz o filtro em vez de sair da tela; a busca vira link que dá
 *  para colar para outra pessoa; e recarregar a página não joga fora o que a pessoa montou.
 *
 *  A escrita EMPILHA no histórico, e não substitui — mas só porque o texto chega aqui já atrasado
 *  (ver `useAtraso`). Uma entrada por tecla transformaria o voltar num desfazer-letra-por-letra;
 *  substituir sempre tem o defeito oposto, e pior: o voltar deixaria de desfazer o filtro e
 *  passaria a sair da tela, que é justamente o comportamento de que se estava fugindo. Atrasado,
 *  cada entrada corresponde a uma busca que a pessoa de fato fez.
 *
 *  Escrita que não muda nada é descartada: sem essa guarda, cada re-render empilharia um endereço
 *  idêntico e seriam precisos vários cliques no voltar para sair de uma tela só.
 */
export function useFiltrosNaUrl<T extends Record<string, string>>(padrao: T) {
  const [params, setParams] = useSearchParams();
  const padraoRef = useRef(padrao);

  const valores = { ...padraoRef.current };
  for (const k of Object.keys(padraoRef.current) as (keyof T)[]) {
    const v = params.get(k as string);
    if (v !== null) valores[k] = v as T[keyof T];
  }

  const definir = (mudancas: Partial<T>) => {
    const novo = new URLSearchParams(params);
    for (const [k, v] of Object.entries(mudancas)) {
      // Valor igual ao padrão sai da URL: uma barra de endereços cheia de `arquivados=false` é
      // ruído que atrapalha justamente quem quer copiar e mandar o link.
      if (v === undefined || v === "" || v === padraoRef.current[k]) novo.delete(k);
      else novo.set(k, String(v));
    }
    if (novo.toString() === params.toString()) return;
    setParams(novo);
  };

  const limpar = () => { if (params.toString()) setParams(new URLSearchParams()); };
  const algumFiltro = Object.keys(padraoRef.current).some((k) => params.get(k) !== null);

  return { valores, definir, limpar, algumFiltro };
}

export type Ordem<K extends string> = { campo: K; desc: boolean };

/** Ordenação de uma lista já carregada.
 *
 *  ATENÇÃO ao alcance disto: a API do CRM pagina por cursor em `(created_at, id)`, então o
 *  servidor entrega sempre na ordem de criação e não aceita outro critério — mudar isso exigiria
 *  um cursor por critério de ordenação. Logo, o que esta função ordena é a PÁGINA que está na
 *  tela, não a base. Quem mostra precisa dizer isso quando ainda existe página seguinte; caso
 *  contrário, "o mais caro" vira "o mais caro entre os 50 primeiros por data" sem avisar ninguém.
 */
export function ordenar<T, K extends string>(itens: T[], ordem: Ordem<K> | null,
                                             chave: (item: T, campo: K) => string | number | null): T[] {
  if (!ordem) return itens;
  const sinal = ordem.desc ? -1 : 1;
  return [...itens].sort((a, b) => {
    const x = chave(a, ordem.campo), y = chave(b, ordem.campo);
    // Ausente vai sempre para o fim, nas duas direções: "sem data" não é nem o menor nem o maior
    // valor, e deixá-lo competir faria a primeira linha da lista ser um vazio.
    if (x === null || x === "") return 1;
    if (y === null || y === "") return -1;
    if (typeof x === "number" && typeof y === "number") return (x - y) * sinal;
    return String(x).localeCompare(String(y), "pt-BR", { numeric: true }) * sinal;
  });
}
