import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Botao, CabecalhoPagina, Card, Carregando, Erro, Etiqueta, cx, entradaCls, foco } from "../componentes/ui";
import { ErroApi, api, type Oportunidade } from "../lib/api";
import { ATENDIMENTO, ESTAGIOS, NOME_ESTAGIO, PROPOSITO,
         dataHora, diasParado, tomDoParado } from "../lib/formato";

/** Busca TODAS as oportunidades, seguindo o cursor.
 *
 *  Uma página só (o máximo da API é 100) fazia o quadro mostrar 100 de 120 e contradizer as
 *  contagens da Visão geral na tela anterior — um funil que mente por omissão é pior que um funil
 *  que avisa estar truncado. O teto de 20 páginas existe para o quadro não virar um carregamento
 *  infinito no dia em que a base crescer; quando ele é atingido, a tela diz.
 */
const PAGINAS_MAX = 20;

async function todasAsOportunidades() {
  const itens: Oportunidade[] = [];
  let cursor: string | undefined;
  for (let i = 0; i < PAGINAS_MAX; i++) {
    const p = await api.oportunidades({ limit: "100", cursor });
    itens.push(...p.items);
    if (!p.next_cursor) return { itens, truncado: false };
    cursor = p.next_cursor;
  }
  return { itens, truncado: true };
}

/** Quadro do funil.
 *
 *  A mudança de estágio é por MENU, não por arrastar. Arrastar é bonito e é a pior forma de mover
 *  algo que precisa de motivo, de confirmação e de leitor de tela: a especificação pede "menu
 *  acessível ou arraste", e entre os dois o menu é o que funciona para todo mundo.
 *
 *  Quando o servidor recusa, a coluna volta ao que era e o erro aparece com o motivo. Nada de
 *  otimismo aqui — o painel não pode mostrar "negociação" e o banco dizer outra coisa.
 */
export function Funil() {
  const qc = useQueryClient();
  const [falha, setFalha] = useState<unknown>(null);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["oportunidades"], queryFn: todasAsOportunidades,
  });

  const mover = useMutation({
    mutationFn: ({ op, destino, motivo }: { op: Oportunidade; destino: string; motivo: string | null }) =>
      api.mover(op.id, destino, motivo, op.version),
    onSuccess: () => { setFalha(null); qc.invalidateQueries({ queryKey: ["oportunidades"] }); },
    onError: (e) => setFalha(e),
  });

  if (isLoading) return <Carregando linhas={5} />;
  if (error) return <Erro erro={error} aoTentar={() => refetch()} />;

  const porEstagio = Object.fromEntries(
    ESTAGIOS.map((e) => [e.k, data!.itens.filter((o) => o.stage === e.k)]),
  );

  return (
    <div className="space-y-4">
      <CabecalhoPagina titulo="Funil"
        descricao="Da esquerda para a direita. Mover pede o estágio de destino — e o motivo, quando a API exige."
        acoes={<span className="text-xs text-inkFaint">{data!.itens.length} oportunidades</span>} />
      {data!.truncado && (
        <p className="rounded-lg border border-line bg-alertaSoft px-3 py-2 text-xs text-alerta">
          Mostrando as {data!.itens.length} mais recentes — há mais no banco do que cabe neste quadro.
        </p>
      )}
      {falha ? <Erro erro={falha} /> : null}
      {falha instanceof ErroApi && falha.code === "VERSION_CONFLICT" && (
        <p className="text-xs text-inkMuted">
          Alguém alterou esta oportunidade enquanto a tela estava aberta. Recarregue para ver o
          estado atual antes de mover de novo.
        </p>
      )}

      {/* Uma faixa só, com rolagem lateral. O grid anterior quebrava em duas linhas e punha
          "Negociação" longe de "Ganho" — um funil lido de cima para baixo e de volta para a
          esquerda deixa de parecer um funil. Coluna de largura fixa: deixar sete colunas
          dividirem a tela espremeria cada card a ponto de o nome do cliente não caber. */}
      <div className="-mx-1 flex gap-3 overflow-x-auto px-1 pb-2">
        {ESTAGIOS.map((e) => {
          const itens = porEstagio[e.k];
          // Uma regra só, em `tomDoParado`: ela já sabe do limiar e já isenta estágio encerrado.
          // Repetir a condição aqui criaria a chance de o total e os cards discordarem.
          const parados = itens.filter((o) => ["alerta", "ruim"].includes(
            tomDoParado(diasParado(o.updated_at), o.stage) ?? "")).length;
          return (
            <div key={e.k} className="w-72 shrink-0">
              <Card titulo={
                <span className="flex items-center gap-2">
                  {e.r}
                  <span className="rounded bg-surface2 px-1.5 text-[11px] tabular-nums text-inkMuted">
                    {itens.length}
                  </span>
                </span>
              } acoes={
                /* No lugar da soma em dinheiro de um CRM comercial: quantas estão paradas. O CRM
                   não guarda valor de negócio, e somar orçamento do cliente e chamar de pipeline
                   seria inventar dinheiro justamente na tela onde se decide o que priorizar. */
                parados > 0
                  ? <span className="rounded bg-alertaSoft px-1.5 py-0.5 text-[11px] font-medium text-alerta">
                      {parados} parada{parados > 1 ? "s" : ""}
                    </span>
                  : undefined
              } semPadding>
                <p className="px-4 pt-2 text-[11px] text-inkFaint">{e.ajuda}</p>
                <ul className="max-h-[460px] space-y-2 overflow-y-auto p-3">
                  {itens.length === 0 && <li className="px-1 py-2 text-xs text-inkFaint">Vazio.</li>}
                  {itens.map((op) => (
                    <Ficha key={op.id} op={op} ocupado={mover.isPending}
                           aoMover={(destino, motivo) => mover.mutate({ op, destino, motivo })} />
                  ))}
                </ul>
              </Card>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Ficha({ op, aoMover, ocupado }: {
  op: Oportunidade; aoMover: (destino: string, motivo: string | null) => void; ocupado: boolean;
}) {
  const [destino, setDestino] = useState("");
  const [motivo, setMotivo] = useState("");
  const humano = op.atendimento !== "agent";
  const dias = diasParado(op.updated_at);
  const tom = tomDoParado(dias, op.stage);
  // Perder e reabrir exigem motivo — a API recusa sem ele, e pedir aqui evita um erro que a
  // pessoa só descobriria depois de clicar.
  const pedeMotivo = destino === "lost" || (destino === "in_service" && ["won", "lost"].includes(op.stage));

  return (
    /* `relative` não é estilo: é o bloco contentor do rótulo `sr-only` lá embaixo.
       `.sr-only` é `position: absolute`, e sem um ancestral posicionado o contentor dele vira a
       página inteira — aí o `overflow` da coluna não o recorta, e cada rótulo invisível do 15º
       card empurra a altura do documento. O resultado era uma página que rolava mais de mil pixels
       de nada, com o quadro inteiro cabendo em 552. */
    <li className="relative rounded-lg border border-line bg-surface p-2.5">
      <div className="flex items-start justify-between gap-2">
        <Link to={`/oportunidades/${op.id}`}
              className={cx("text-sm font-medium text-ink hover:text-acento hover:underline", foco)}>
          {PROPOSITO[op.purpose]}
        </Link>
        {humano && <Etiqueta tom={ATENDIMENTO[op.atendimento].tom}>{ATENDIMENTO[op.atendimento].r}</Etiqueta>}
      </div>
      <Link to={`/clientes/${op.lead_id}`} className="mt-0.5 block truncate text-[11px] text-inkMuted hover:underline">
        {op.lead_name ?? `cliente ${op.lead_id.slice(0, 8)}`}
      </Link>
      {tom && (
        /* Texto junto da cor, sempre: "23d" amarelo sozinho não diz nada a quem não distingue
           amarelo de cinza — e não diz nada a ninguém na primeira vez que vê a tela. */
        <p className={cx("mt-1 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium",
                         tom === "ruim" ? "bg-ruimSoft text-ruim"
                         : tom === "alerta" ? "bg-alertaSoft text-alerta" : "text-inkFaint")}
           title={`Última alteração em ${dataHora(op.updated_at)}`}>
          {dias === 0 ? "mexida hoje" : `parada há ${dias}d`}
        </p>
      )}
      {op.lost_reason && <p className="mt-1 text-[11px] text-inkFaint">Motivo: {op.lost_reason}</p>}

      <div className="mt-2 space-y-1.5">
        <label className="sr-only" htmlFor={`mover-${op.id}`}>
          Mover a oportunidade de {PROPOSITO[op.purpose]} do estágio {NOME_ESTAGIO[op.stage]}
        </label>
        <select id={`mover-${op.id}`} className={cx(entradaCls, "text-xs")} value={destino}
                onChange={(e) => setDestino(e.target.value)}>
          <option value="">Mover para…</option>
          {ESTAGIOS.filter((x) => x.k !== op.stage).map((x) => (
            <option key={x.k} value={x.k}>{x.r}</option>
          ))}
        </select>
        {pedeMotivo && (
          <input className={cx(entradaCls, "text-xs")} placeholder="Motivo (obrigatório)"
                 aria-label="Motivo" value={motivo} onChange={(e) => setMotivo(e.target.value)} />
        )}
        {destino && (
          <Botao className="w-full justify-center text-xs" ocupado={ocupado}
                 disabled={pedeMotivo && !motivo.trim()}
                 onClick={() => aoMover(destino, motivo.trim() || null)}>
            Confirmar
          </Botao>
        )}
      </div>
    </li>
  );
}
