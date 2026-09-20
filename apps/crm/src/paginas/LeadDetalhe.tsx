import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Botao, CabecalhoPagina, Card, Carregando, Erro, Etiqueta, Vazio } from "../componentes/ui";
import { api } from "../lib/api";
import { ATENDIMENTO, NOME_ESTAGIO, POLITICA_CONTATO, PROPOSITO, dataHora, relativo } from "../lib/formato";

/** Ficha do cliente: identificação, oportunidades e linha do tempo.
 *
 *  A linha do tempo é o coração da tela. É onde o corretor descobre, em trinta segundos, o que já
 *  foi dito — e é por isso que o conteúdo aparece INTEIRO e sem interpretação: o texto veio do
 *  cliente, é dado, e o painel não age sobre ele.
 */
export function LeadDetalhe() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const [falha, setFalha] = useState<unknown>(null);

  const lead = useQuery({ queryKey: ["lead", id], queryFn: () => api.lead(id) });
  const historico = useQuery({ queryKey: ["historico", id], queryFn: () => api.historico(id) });

  const alterar = useMutation({
    mutationFn: (corpo: Record<string, unknown>) => api.alterarLead(id, corpo, lead.data!.data.version),
    onSuccess: () => { setFalha(null); qc.invalidateQueries({ queryKey: ["lead", id] }); },
    onError: (e) => setFalha(e),
  });

  if (lead.isLoading) return <Carregando linhas={5} />;
  if (lead.error) return <Erro erro={lead.error} aoTentar={() => lead.refetch()} />;
  const l = lead.data!.data;

  return (
    <div className="space-y-4">
      <CabecalhoPagina titulo={l.name} voltar={{ para: "/clientes", r: "Clientes" }}
        contexto={
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {l.archived_at && <Etiqueta>arquivado em {dataHora(l.archived_at)}</Etiqueta>}
            <Etiqueta tom={POLITICA_CONTATO[l.contact_policy].tom}>{POLITICA_CONTATO[l.contact_policy].r}</Etiqueta>
          </div>
        } />

      {falha ? <Erro erro={falha} /> : null}

      <div className="grid items-start gap-4 lg:grid-cols-[1fr_1.4fr]">
        <div className="space-y-4">
          <Card titulo="Identificação">
            <dl className="space-y-2 text-sm">
              <Linha rotulo="E-mail" valor={l.email} />
              <Linha rotulo="Telefone" valor={l.phone_e164} />
              <Linha rotulo="Identificador externo" valor={l.external_contact_id} />
              <Linha rotulo="Origem" valor={l.source} />
              <Linha rotulo="Cadastrado" valor={dataHora(l.created_at)} />
            </dl>
          </Card>

          <Card titulo="Contato">
            <p className="text-xs text-inkMuted">
              A Mora pode <b>bloquear</b> o contato a pedido do cliente, mas nunca liberar — liberar
              exige uma pessoa, porque é a decisão que ninguém consegue desfazer depois de uma
              mensagem indevida ter saído.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {l.contact_policy !== "allowed" && (
                <Botao ocupado={alterar.isPending} onClick={() => alterar.mutate({ contact_policy: "allowed" })}>
                  Liberar contato
                </Botao>
              )}
              {l.contact_policy !== "blocked" && (
                <Botao variante="perigo" ocupado={alterar.isPending}
                       onClick={() => alterar.mutate({ contact_policy: "blocked" })}>
                  Bloquear contato
                </Botao>
              )}
              {!l.archived_at && (
                <Botao ocupado={alterar.isPending} onClick={() => alterar.mutate({ archived: true })}>
                  Arquivar
                </Botao>
              )}
            </div>
          </Card>

          <Card titulo="Oportunidades">
            {l.opportunities.length === 0 ? (
              <p className="text-sm text-inkMuted">Nenhuma ainda.</p>
            ) : (
              <ul className="space-y-2">
                {l.opportunities.map((o) => (
                  <li key={o.id}>
                    <Link to={`/oportunidades/${o.id}`}
                          className="flex flex-wrap items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm hover:bg-surface2">
                      <span className="font-medium text-ink">{PROPOSITO[o.purpose]}</span>
                      <Etiqueta>{NOME_ESTAGIO[o.stage]}</Etiqueta>
                      {o.atendimento !== "agent" && (
                        <Etiqueta tom={ATENDIMENTO[o.atendimento].tom}>{ATENDIMENTO[o.atendimento].r}</Etiqueta>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            {l.opportunities.length > 1 && (
              <p className="mt-2 text-[11px] text-inkFaint">
                A mesma pessoa pode comprar e alugar ao mesmo tempo — cada intenção tem preferências
                próprias.
              </p>
            )}
          </Card>
        </div>

        <Card titulo="Linha do tempo" semPadding>
          {historico.isLoading ? <div className="p-4"><Carregando /></div>
            : historico.error ? <div className="p-4"><Erro erro={historico.error} /></div>
            : historico.data!.items.length === 0 ? (
              <div className="p-4">
                <Vazio titulo="Nenhuma interação registrada"
                       descricao="Assim que a Mora ou um corretor registrar uma conversa, ela aparece aqui." />
              </div>
            ) : (
              /* Caixa com rolagem PRÓPRIA precisa de tabIndex: sem ele, quem navega por teclado não
                 consegue percorrer o histórico — foi um defeito real encontrado por varredura de
                 acessibilidade no outro painel do projeto. */
              <ul tabIndex={0} aria-label="Histórico de interações"
                  className="max-h-[70vh] divide-y divide-line overflow-y-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--anel-foco)]">
                {historico.data!.items.map((i) => (
                  <li key={i.id} className="px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-inkFaint">
                      <Etiqueta tom={i.direction === "inbound" ? "info" : i.direction === "outbound" ? "neutro" : "alerta"}>
                        {i.direction === "inbound" ? "cliente" : i.direction === "outbound" ? "nós" : "interno"}
                      </Etiqueta>
                      <span>{i.channel}</span>
                      <span className="ml-auto">{relativo(i.occurred_at)} · {dataHora(i.occurred_at)}</span>
                    </div>
                    {/* Texto do cliente: exibido como está, sem interpretar nada. */}
                    <p className="mt-1 whitespace-pre-wrap text-sm text-inkSoft">{i.summary}</p>
                  </li>
                ))}
              </ul>
            )}
        </Card>
      </div>
    </div>
  );
}

function Linha({ rotulo, valor }: { rotulo: string; valor: string | null }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="shrink-0 text-inkMuted">{rotulo}</dt>
      <dd className="truncate text-right text-ink">{valor ?? "—"}</dd>
    </div>
  );
}
