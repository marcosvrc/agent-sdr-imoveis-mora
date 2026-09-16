import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, brl } from "../lib/api";
import { relativo } from "../lib/format";
import { Ajuda, Badge, Card, EmptyState, Skeleton, Temperatura } from "./ui";
import { Ic } from "./Icons";

/** Fase 4 do ADR-0013: o que o aviso de imóvel novo produziu.
 *
 *  A taxa de SAÍDA fica lado a lado com a de resposta de propósito. Reativação é a única mensagem
 *  que a Mora manda sem ninguém ter pedido, e olhar só quantas pessoas responderam esconde o custo:
 *  se a régua estiver frouxa, o número de respostas sobe junto com o de gente pedindo para nunca
 *  mais ser avisada — e a segunda coisa é irreversível.
 *
 *  Janela de 30 dias porque reativação é lenta: o lead sumiu semanas atrás e o imóvel certo aparece
 *  quando aparece. Sete dias mostrariam zero quase sempre.
 */
export function ReativacaoResumo({ dias = 30 }: { dias?: number }) {
  const { data, isLoading } = useQuery({ queryKey: ["reativacao-resumo", dias], queryFn: () => api.resumoReativacao(dias) });

  if (isLoading || !data) return <Skeleton className="h-48" />;

  const sel = data.selecao;
  return (
    <Card
      titulo={
        <span className="flex items-center gap-1.5">
          Reativação · avisos de imóvel novo
          <Ajuda titulo="Como ler estes números" alinhar="esquerda">
            Quando um imóvel <b>entra</b> na base, a Mora avisa quem procurava algo assim e sumiu — sempre
            dizendo o motivo. Aqui estão os últimos {data.dias} dias. <b>Respondeu</b> conta só quem voltou a
            falar em até {data.janela_resposta_h}h depois do aviso; mais tarde que isso é conversa nova.
            <b> Pediu para sair</b> é o custo do recurso: se subir junto com as respostas, a régua está frouxa.
          </Ajuda>
        </span>
      }
      acoes={sel.anuncios > 0 && (
        <span className="text-xs text-ink-muted">
          {sel.avisados} avisos em {sel.avaliados} leads avaliados{sel.sem_canal > 0 ? ` · ${sel.sem_canal} sem canal aberto` : ""}
        </span>
      )}
      semPadding
    >
      {data.avisos === 0 ? (
        <div className="p-4">
          <EmptyState
            icone="spark"
            titulo="Nenhum aviso enviado ainda"
            descricao={`Assim que um imóvel novo entrar no catálogo e casar com o que algum lead adormecido procurava, o aviso sai e aparece aqui. Para ver quem seria avisado antes de enviar, use "Simular aviso" na ficha do imóvel.`}
          />
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 divide-x divide-y divide-line border-b border-line sm:grid-cols-4 sm:divide-y-0">
            <Numero rotulo="Avisos enviados" valor={String(data.avisos)} nota={`${data.leads} leads · ${data.imoveis} imóveis`} />
            <Numero rotulo="Responderam" valor={data.taxa_resposta != null ? `${data.taxa_resposta}%` : "—"} nota={`${data.responderam} de ${data.avisos}`} tom="good" />
            <Numero rotulo="Viraram visita" valor={data.taxa_visita != null ? `${data.taxa_visita}%` : "—"} nota={`${data.visitas} visita(s)`} tom="good" />
            <Numero rotulo="Pediram para sair" valor={data.taxa_saida != null ? `${data.taxa_saida}%` : "—"} nota={`${data.saidas} opt-out(s)`} tom={data.saidas > 0 ? "bad" : "neutro"} />
          </div>

          <ul className="max-h-[300px] divide-y divide-line overflow-y-auto">
            {data.ultimos.map((u) => (
              <li key={`${u.lead_id}-${u.em}`} className="flex flex-wrap items-center gap-x-2 gap-y-1 px-4 py-2.5 text-sm">
                <Link to={`/leads/${u.lead_id}`} className="font-medium hover:text-brand-accent hover:underline">{u.nome ?? u.lead_id}</Link>
                {u.temperatura && <Temperatura t={u.temperatura} />}
                <span className="text-ink-muted">
                  {u.tipo ? `${u.tipo} ` : "imóvel "}
                  {u.bairro ? `em ${u.bairro}` : u.imovel_id}
                  {u.preco ? ` · ${brl(u.preco, true)}` : ""}
                </span>
                {/* Visita é o desfecho, não só "respondeu" — sem isto o funil diz que houve uma
                    visita e a lista não deixa ver de quem. */}
                {u.visitou
                  ? <Badge tom="good" icone={<Ic.calendar size={11} />}>visita marcada</Badge>
                  : u.respondeu
                    ? <Badge tom="info">respondeu</Badge>
                    : <span className="text-xs text-ink-faint">sem resposta</span>}
                <span className="ml-auto shrink-0 text-[11px] text-ink-faint">{relativo(u.em)}</span>
                {/* O motivo é o que a Mora escreveu na primeira frase — vê-lo aqui é o que permite
                    julgar se o aviso fazia sentido para aquela pessoa. */}
                {u.motivos.length > 0 && (
                  <p className="w-full truncate text-xs text-ink-muted">{u.motivos.join(" · ")}</p>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

function Numero({ rotulo, valor, nota, tom = "neutro" }: {
  rotulo: string; valor: string; nota?: string; tom?: "neutro" | "good" | "bad";
}) {
  const cor = tom === "good" ? "text-good-strong" : tom === "bad" ? "text-bad-strong" : "text-ink";
  return (
    <div className="px-4 py-3">
      <p className="text-[11px] uppercase tracking-wide text-ink-muted">{rotulo}</p>
      <p className={`mt-0.5 text-xl font-semibold tabular-nums ${cor}`}>{valor}</p>
      {nota && <p className="text-[11px] text-ink-faint">{nota}</p>}
    </div>
  );
}
