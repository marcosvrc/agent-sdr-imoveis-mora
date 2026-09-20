import { useCallback, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, brl, type Lead } from "../lib/api";
import { CANAL, INTENCAO, REGIAO, canalDoLead, dataHora, nomeDoLead, relativo, rotulo } from "../lib/format";
import { Transcricao } from "../components/Transcricao";
import { CartaoLead } from "../components/CartaoLead";
import { AnaliseLeadCard } from "../components/AnaliseLead";
import { Avatar, Badge, Button, Estagio, IdCopiavel, Input, NomeLead, Select, Skeleton, Tabs, Temperatura, Toggle, cx } from "../components/ui";
import { InteressesDoLead } from "../components/Interesses";
import { Ic } from "../components/Icons";
import { useTempoReal } from "../lib/ws";

type Aba = "perfil" | "imoveis" | "analise" | "atendimento";

export function LeadDetalhe() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const [aba, setAba] = useState<Aba>("perfil");
  const [texto, setTexto] = useState("");
  const [pedidoEm, setPedidoEm] = useState<string | null>(null);

  const { data: lead } = useQuery({ queryKey: ["lead", id], queryFn: () => api.lead(id) });
  const { data: msgs } = useQuery({ queryKey: ["mensagens", id], queryFn: () => api.mensagens(id) });
  const { data: corretores } = useQuery({ queryKey: ["corretores"], queryFn: api.corretores });
  const refresh = useCallback(() => { qc.invalidateQueries({ queryKey: ["lead", id] }); qc.invalidateQueries({ queryKey: ["mensagens", id] }); }, [qc, id]);
  useTempoReal(useCallback((e) => { if (e.resposta?.lead_id === id) refresh(); }, [id, refresh]));

  const assumir = useMutation({ mutationFn: () => api.assumir(id, lead?.corretor_id ?? null), onSuccess: refresh });
  const devolver = useMutation({ mutationFn: () => api.devolver(id), onSuccess: refresh });
  const responder = useMutation({ mutationFn: (t: string) => api.responder(id, t), onSuccess: () => { setTexto(""); refresh(); } });
  const atribuir = useMutation({ mutationFn: (cid: string | null) => api.atribuirCorretor(id, cid), onSuccess: refresh });
  const reativacao = useMutation({ mutationFn: (aceita: boolean) => api.definirReativacao(id, aceita), onSuccess: refresh });
  const analisar = useMutation({ mutationFn: () => api.analisarLead(id), onSuccess: () => { setPedidoEm(lead?.analisado_em ?? "nenhuma"); const t = setInterval(() => qc.invalidateQueries({ queryKey: ["lead", id] }), 3000); setTimeout(() => clearInterval(t), 45000); } });

  const busca = useMemo(() => resumoBusca(lead), [lead]);
  const briefing = useMemo(() => estadoDoBriefing(lead), [lead]);
  if (!lead) return <Carregando />;
  const emHandoff = lead.estagio === "handoff";
  const ativos = (corretores ?? []).filter((c) => c.ativo);
  const analisando = analisar.isPending || (pedidoEm !== null && pedidoEm === (lead.analisado_em ?? "nenhuma"));

  return (
    <div className="space-y-4">
      <Link to="/leads" className="inline-flex items-center gap-1 text-xs text-ink-muted hover:text-ink"><Ic.chevronLeft size={14} /> Leads</Link>

      {/* Já falamos com esta pessoa antes: o corretor precisa saber disso antes de abrir a boca */}
      {(lead.outras_oportunidades?.length ?? 0) > 0 && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-info-line bg-info-soft px-4 py-2.5 text-sm text-info-strong">
          <span className="inline-flex items-center gap-2 font-medium"><Ic.refresh size={15} />
            Cliente recorrente — {lead.outras_oportunidades!.length + 1} oportunidades no total
          </span>
          <span className="text-xs">
            antes: {lead.outras_oportunidades!.map((o) => `${INTENCAO[o.cartao?.intencao ?? ""] ?? "indefinida"} (${dataHora(o.criado_em).slice(0, 5)})`).join(" · ")}
          </span>
          {lead.cliente_id && <Link to="/clientes" className="ml-auto text-xs font-medium text-info-strong underline">ver a ficha do cliente</Link>}
        </div>
      )}

      {/* Identidade + o que o lead busca + ação primária: tudo que o corretor precisa antes de falar */}
      <header className="rounded-xl border border-line bg-surface shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-3 p-4">
          <div className="flex min-w-0 items-center gap-3">
            <Avatar nome={nomeDoLead(lead).avatar} tamanho={44} />
            <div className="min-w-0">
              <h1 className="flex flex-wrap items-center gap-2 text-lg font-semibold leading-tight">
                <NomeLead lead={lead} /><Estagio e={lead.estagio} /><Temperatura t={lead.temperatura} />
              </h1>
              <p className="mt-0.5 truncate text-xs text-ink-muted">
                {lead.canais?.map((c) => `${CANAL[c.canal] ?? c.canal}: ${c.identificador}`).join(" · ") || rotulo(CANAL, canalDoLead(lead))} · entrou {relativo(lead.criado_em)} atrás
              </p>
              {/* O id fica AQUI e em nenhum outro lugar: é a tela onde alguém já sabe de quem está
                  falando e pode precisar do identificador para cruzar com o log ou com o CRM. Nas
                  listas ele ocupava a linha do nome, que foi como virou nome. */}
              <div className="mt-1.5"><IdCopiavel id={lead.id} /></div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {emHandoff
              ? <Button onClick={() => devolver.mutate()} disabled={devolver.isPending} icone={<Ic.refresh size={14} />}>Devolver à Mora</Button>
              : <Button variante="primario" onClick={() => assumir.mutate()} disabled={assumir.isPending} icone={<Ic.handoff size={14} />}>
                  {lead.corretor_nome ? `Assumir como ${lead.corretor_nome.split(" ")[0]}` : "Assumir conversa"}
                </Button>}
          </div>
        </div>
        {/* Faixa de leitura em 5 segundos */}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-line px-4 py-2.5 text-sm">
          {busca.length > 0
            ? busca.map((b, i) => <span key={b.r} className="flex items-center gap-1.5 text-ink">
                {i > 0 && <span className="mr-3 h-3 w-px bg-line" aria-hidden />}
                <span className="text-[11px] uppercase tracking-wide text-ink-muted">{b.r}</span><b className="font-medium">{b.v}</b></span>)
            : <span className="text-sm text-ink-muted">Qualificação em andamento — a Mora ainda está descobrindo o que o lead busca.</span>}
          <span className="ml-auto flex items-center gap-3 text-xs text-ink-muted">
            <span title="Score de prioridade">score <b className="tabular-nums text-ink">{lead.score}</b></span>
            <span>follow-ups <b className="tabular-nums text-ink">{lead.followups_enviados}</b></span>
            <span>último contato <b className="text-ink">{relativo(lead.ultima_mensagem_em)}</b></span>
          </span>
        </div>
      </header>

      <div className="grid gap-4 lg:h-[calc(100vh-17rem)] lg:min-h-[520px] lg:grid-cols-5">
        {/* Conversa: coluna dominante, scroll próprio, composer sempre visível */}
        <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-card lg:col-span-3">
          <header className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5">
            <h2 className="text-sm font-semibold">Conversa</h2>
            <span className={cx("flex items-center gap-1.5 text-xs", emHandoff ? "text-violeta-strong" : "text-ink-muted")}>
              <span className={cx("h-1.5 w-1.5 rounded-full", emHandoff ? "bg-violeta" : "bg-good")} />
              {emHandoff ? `${lead.corretor_nome ?? "Corretor"} no comando · Mora em silêncio` : "Mora respondendo automaticamente"}
            </span>
          </header>
          <div className="min-h-0 flex-1 p-3"><Transcricao msgs={msgs ?? []} altura="h-full min-h-[320px]" /></div>
          <footer className="border-t border-line p-3">
            {emHandoff ? (
              <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (texto.trim()) responder.mutate(texto); }}>
                <Input autoFocus placeholder="Responder como corretor…" value={texto} onChange={(e) => setTexto(e.target.value)} />
                <Button variante="primario" type="submit" disabled={responder.isPending || !texto.trim()}>Enviar</Button>
              </form>
            ) : (
              <p className="flex items-center justify-center gap-1.5 text-xs text-ink-muted"><Ic.info size={13} /> Assuma a conversa para responder ao lead por aqui.</p>
            )}
          </footer>
        </section>

        {/* Painel do lead: abas em vez de cinco cards empilhados */}
        <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-card lg:col-span-2">
          <Tabs<Aba> atual={aba} onMudar={setAba} abas={[
            { k: "perfil", r: "Perfil" },
            { k: "imoveis", r: "Imóveis" },
            { k: "analise", r: "Análise", badge: lead.analise ? <span className="h-1.5 w-1.5 rounded-full bg-[var(--series-3)]" /> : undefined },
            { k: "atendimento", r: "Atendimento", badge: emHandoff && !lead.corretor_nome ? <span className="h-1.5 w-1.5 rounded-full bg-[var(--status-warn)]" /> : undefined },
          ]} />
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
            {aba === "perfil" && <>
              <Bloco titulo="Qualificação"><CartaoLead c={lead.cartao} /></Bloco>
              <Bloco titulo="Briefing da Mora" acao={<Button tamanho="sm" variante="fantasma" onClick={() => analisar.mutate()} disabled={analisando || briefing === "processando"} icone={<Ic.refresh size={13} />}>{analisando || briefing === "processando" ? "Gerando…" : lead.resumo ? "Atualizar" : "Gerar"}</Button>}>
                {lead.resumo && <p className="whitespace-pre-wrap text-sm text-ink">{lead.resumo}</p>}
                {briefing === "processando" && <p className="mt-1 text-xs text-ink-muted">Gerando o briefing… (o worker `resumidor` está processando)</p>}
                {briefing === "sem_resposta" && (
                  <p className="mt-1 flex items-start gap-1.5 rounded-lg bg-warn-soft px-2.5 py-2 text-xs text-warn-strong">
                    <Ic.info size={13} className="mt-0.5 shrink-0" />
                    <span>O pedido foi enviado há {relativo(lead.analise_solicitada_em)} e não houve resposta. O serviço que gera o briefing (worker <b>resumidor</b>) provavelmente está parado — reinicie-o e peça de novo.</span>
                  </p>)}
                {briefing === "vazio" && <p className="text-sm text-ink-muted">Gerado quando o lead fica qualificado, agenda visita ou é encaminhado ao corretor — ou ao pedir aqui.</p>}
              </Bloco>
            </>}
            {aba === "imoveis" && (
              <Bloco titulo="Imóveis desta conversa">
                <p className="mb-3 text-[11px] text-ink-muted">
                  O que a Mora mostrou e o que o cliente demonstrou querer. Marcar
                  <b> Descartado</b> tira o imóvel das próximas sugestões dela.
                </p>
                <InteressesDoLead leadId={id} />
              </Bloco>
            )}
            {aba === "analise" && <>
              {briefing === "sem_resposta" && (
                <p className="mb-3 flex items-start gap-1.5 rounded-lg bg-warn-soft px-2.5 py-2 text-xs text-warn-strong">
                  <Ic.info size={13} className="mt-0.5 shrink-0" />
                  <span>Pedido enviado há {relativo(lead.analise_solicitada_em)} sem resposta — o worker <b>resumidor</b> parece estar parado.</span>
                </p>)}
              <AnaliseLeadCard analise={lead.analise} analisadoEm={lead.analisado_em} onAtualizar={() => analisar.mutate()} atualizando={analisando || briefing === "processando"} semMoldura />
            </>}
            {aba === "atendimento" && <>
              <Bloco titulo="Corretor responsável" acao={lead.corretor_nome ? <Badge tom="violet">{lead.corretor_nome}</Badge> : <Badge tom="warn">sem corretor</Badge>}>
                <Select value={lead.corretor_id && ativos.some((c) => c.id === lead.corretor_id) ? lead.corretor_id : ""} onChange={(e) => atribuir.mutate(e.target.value || null)} disabled={atribuir.isPending}>
                  <option value="">{ativos.length ? "Sem corretor atribuído" : "Nenhum corretor ativo cadastrado"}</option>
                  {ativos.map((c) => <option key={c.id} value={c.id}>{c.nome}{c.regioes.length ? ` · ${c.regioes.map((r) => r.replace("zona_", "z. ")).join(", ")}` : ""}</option>)}
                </Select>
                <p className="mt-2 text-[11px] text-ink-muted">A Mora escolhe pela região e carga no handoff e no agendamento; aqui você troca. Visitas futuras acompanham.</p>
              </Bloco>
              {/* O aviso de imóvel novo é a única mensagem que a Mora manda sem ser chamada. Quem
                  pede para não receber costuma pedir ao corretor, por telefone ou numa visita —
                  então o interruptor tem de estar aqui, e não só na conversa. */}
              <Bloco titulo="Avisos de imóvel novo"
                     acao={lead.reativado_em ? <span className="text-[11px] text-ink-muted">último aviso há {relativo(lead.reativado_em)}</span> : undefined}>
                <Toggle on={lead.aceita_reativacao !== false} onChange={(v) => reativacao.mutate(v)}
                        label={lead.aceita_reativacao !== false ? "A Mora pode avisar sobre imóveis novos" : "Não avisar — pedido do cliente"} />
                <p className="mt-2 text-[11px] text-ink-muted">
                  Vale só para o aviso proativo quando entra um imóvel que casa com a busca dele. Não afeta
                  follow-up nem resposta a mensagem do cliente.
                </p>
              </Bloco>
              <Bloco titulo="Acompanhamento">
                <dl className="space-y-2 text-sm">
                  {[["Estágio", <Estagio key="e" e={lead.estagio} />], ["Temperatura", <Temperatura key="t" t={lead.temperatura} />],
                    ["Score", <b key="s" className="tabular-nums">{lead.score}</b>], ["Follow-ups enviados", String(lead.followups_enviados)],
                    ["Primeiro contato", dataHora(lead.criado_em)], ["Último contato", dataHora(lead.ultima_mensagem_em)]].map(([k, v], i) => (
                    <div key={i} className="flex items-center justify-between gap-3 border-b border-line pb-1.5 last:border-0">
                      <dt className="text-xs text-ink-muted">{k as string}</dt><dd className="text-right">{v}</dd>
                    </div>))}
                </dl>
              </Bloco>
            </>}
          </div>
        </section>
      </div>
    </div>
  );
}

/** O briefing é gerado por um worker separado: distinguimos "processando" de "worker não respondeu". */
function estadoDoBriefing(lead?: Lead): "vazio" | "pronto" | "processando" | "sem_resposta" {
  if (!lead) return "vazio";
  const pedido = lead.analise_solicitada_em ? Date.parse(lead.analise_solicitada_em) : 0;
  const feito = lead.analisado_em ? Date.parse(lead.analisado_em) : 0;
  if (pedido && pedido > feito) return Date.now() - pedido > 90_000 ? "sem_resposta" : "processando";
  return lead.resumo ? "pronto" : "vazio";
}

/** Resumo do que o lead procura, para a faixa do cabeçalho — só o que ele já informou. */
function resumoBusca(lead?: Lead): { r: string; v: string }[] {
  if (!lead) return [];
  const c = lead.cartao;
  const linhas: { r: string; v: string | undefined }[] = c.intencao === "investimento"
    ? [{ r: "Busca", v: INTENCAO[c.intencao] }, { r: "Perfil", v: c.perfil_investidor }, { r: "Ticket", v: c.ticket ? brl(c.ticket, true) : undefined }, { r: "Retorno", v: c.retorno_esperado }]
    : [{ r: "Busca", v: c.intencao !== "indefinida" ? INTENCAO[c.intencao] : undefined },
       { r: "Onde", v: c.bairros[0] ?? (c.regiao ? REGIAO[c.regiao] ?? c.regiao : undefined) },
       { r: "Até", v: c.preco_max ? brl(c.preco_max, true) : undefined },
       { r: "Quartos", v: c.quartos ? `${c.quartos}+` : undefined },
       { r: "Prazo", v: c.urgencia?.replace(/_/g, " ") }];
  return linhas.filter((l): l is { r: string; v: string } => Boolean(l.v));
}

function Bloco({ titulo, acao, children }: { titulo: string; acao?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs font-semibold text-ink-muted">{titulo}</h3>{acao}
      </div>
      {children}
    </div>
  );
}

function Carregando() {
  return <div className="space-y-4"><Skeleton className="h-24" /><div className="grid gap-4 lg:grid-cols-5"><Skeleton className="h-[420px] lg:col-span-3" /><Skeleton className="h-[420px] lg:col-span-2" /></div></div>;
}
