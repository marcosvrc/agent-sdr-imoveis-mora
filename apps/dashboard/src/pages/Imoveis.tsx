import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, REGIOES, type Imovel } from "../lib/api";
import { brl, num, REGIAO } from "../lib/format";
import { Badge, Button, Card, ConfirmDialog, EmptyState, Input, Modal, PageHeader, Paginacao, Select, Skeleton, StatTile, Table, usePaginacao, cx } from "../components/ui";
import { InteressadosNoImovel, SeloInteressados } from "../components/Interesses";
import { SimularReativacao } from "../components/SimularReativacao";
import { Ic } from "../components/Icons";
import { Carrossel } from "../components/Carrossel";
import { redimensionarImagem } from "../lib/imagem";

const POR_PAGINA = 10;
const C = "px-3 py-2.5 text-center";   // todas as colunas centralizadas

export function Imoveis() {
  const [f, setF] = useState<{ operacao?: string; regiao?: string; quartos?: number; tipo?: string }>({});
  const [busca, setBusca] = useState("");
  const [sel, setSel] = useState<Imovel | null>(null);
  const [visao, setVisao] = useState<"tabela" | "cards">("tabela");
  const { data, isLoading } = useQuery({ queryKey: ["imoveis", f.operacao, f.regiao, f.quartos], queryFn: () => api.imoveis({ operacao: f.operacao, regiao: f.regiao, quartos: f.quartos }) });

  const lista = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return (data ?? []).filter((i) => (!f.tipo || i.tipo === f.tipo) && (!q || [i.id, i.bairro, i.descricao, i.tipo].some((v) => v.toLowerCase().includes(q))));
  }, [data, busca, f.tipo]);
  const pag = usePaginacao(lista, POR_PAGINA, "imoveis");
  const resumo = useMemo(() => {
    const venda = lista.filter((i) => i.operacao === "venda"), aluguel = lista.filter((i) => i.operacao === "aluguel");
    const med = (xs: number[]) => xs.length ? [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)] : null;
    return { total: lista.length, venda: venda.length, aluguel: aluguel.length, medVenda: med(venda.map((i) => i.preco)), medAluguel: med(aluguel.map((i) => i.preco)) };
  }, [lista]);
  const limpar = () => { setBusca(""); setF({}); pag.setPagina(1); };

  return (
    <div className="space-y-4">
      <PageHeader titulo="Imóveis" descricao="Catálogo indexado para o RAG da Mora — o que o agente pode oferecer aos leads"
        acoes={<div className="inline-flex rounded-lg border border-line bg-surface p-0.5 text-xs">{(["tabela", "cards"] as const).map((v) => <button key={v} onClick={() => setVisao(v)} className={cx("rounded-md px-2.5 py-1.5 font-medium capitalize", visao === v ? "bg-brand text-brand-ink" : "text-ink-muted")}>{v}</button>)}</div>} />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StatTile label="Imóveis no filtro" valor={num(resumo.total)} icone="building"
          ajuda={<>Quantos imóveis atendem aos filtros e à busca aplicados agora. É o mesmo conjunto que a Mora tem para oferecer ao cliente com esses critérios. A base carrega até 200 imóveis por vez.</>} />
        <StatTile label="À venda" valor={num(resumo.venda)}
          ajuda={<>Dos imóveis no filtro, quantos são de venda. Útil para conferir se o catálogo cobre a demanda: muitos leads de compra e poucos imóveis à venda na região explicam o agente não achar opções.</>} />
        <StatTile label="Para alugar" valor={num(resumo.aluguel)}
          ajuda={<>Dos imóveis no filtro, quantos são de locação. Mesma leitura do indicador ao lado, do outro lado da operação.</>} />
        <StatTile label="Mediana venda" valor={brl(resumo.medVenda, true)}
          ajuda={<>O preço do meio entre os imóveis à venda no filtro — metade custa menos, metade custa mais. Usamos mediana e não média porque uma cobertura cara distorceria a média e daria a impressão errada do catálogo.</>} />
        <StatTile label="Mediana aluguel" valor={brl(resumo.medAluguel, true)} sufixo="/mês"
          ajuda={<>O aluguel do meio entre os imóveis de locação no filtro. Bom para conferir de relance se o orçamento que o cliente declarou cabe na região que ele pediu.</>} />
      </div>
      <Card semPadding>
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
          <div className="relative min-w-[200px] flex-1"><Ic.search size={15} className="pointer-events-none absolute left-2.5 top-2.5 text-ink-faint" /><Input className="pl-8" placeholder="Buscar por código, bairro, descrição…" value={busca} onChange={(e) => { setBusca(e.target.value); pag.setPagina(1); }} /></div>
          <Select aria-label="Filtrar por operação" className="w-40" value={f.operacao ?? ""} onChange={(e) => { setF({ ...f, operacao: e.target.value || undefined }); pag.setPagina(1); }}><option value="">Venda e aluguel</option><option value="venda">Venda</option><option value="aluguel">Aluguel</option></Select>
          <Select aria-label="Filtrar por região" className="w-44" value={f.regiao ?? ""} onChange={(e) => { setF({ ...f, regiao: e.target.value || undefined }); pag.setPagina(1); }}><option value="">Todas as regiões</option>{REGIOES.map((r) => <option key={r} value={r}>{REGIAO[r]}</option>)}</Select>
          <Select aria-label="Filtrar por tipo de imóvel" className="w-40" value={f.tipo ?? ""} onChange={(e) => { setF({ ...f, tipo: e.target.value || undefined }); pag.setPagina(1); }}><option value="">Todos os tipos</option><option value="apartamento">Apartamento</option><option value="casa">Casa</option><option value="studio">Studio</option></Select>
          <Select aria-label="Filtrar por número de quartos" className="w-36" value={f.quartos ?? ""} onChange={(e) => { setF({ ...f, quartos: e.target.value ? Number(e.target.value) : undefined }); pag.setPagina(1); }}><option value="">Quartos</option>{[1, 2, 3, 4].map((q) => <option key={q} value={q}>{q}+ quartos</option>)}</Select>
          {(busca || Object.values(f).some(Boolean)) && <Button variante="fantasma" tamanho="sm" onClick={limpar}>Limpar</Button>}
        </div>
        {isLoading ? <div className="p-4"><Skeleton className="h-64" /></div> : lista.length === 0 ? <EmptyState icone="building" titulo="Nenhum imóvel nesse recorte" descricao="Rode `make seed` para carregar a base simulada ou ajuste os filtros." /> :
          visao === "tabela" ? (<>
            <Table colunas={[{ h: "Código", cls: "text-center" }, { h: "Imóvel", cls: "text-center" }, { h: "Operação", cls: "text-center" }, { h: "Região", cls: "text-center" }, { h: "Quartos", cls: "text-center" }, { h: "Área", cls: "text-center" }, { h: "Preço", cls: "text-center" }, { h: "Cond.", cls: "text-center" }, { h: "Detalhes", cls: "text-center" }]}>
              {pag.fatia.map((i) => (
                <tr key={i.id} className="hover:bg-surface-2">
                  <td className={cx(C, "font-mono text-xs text-ink-muted")}>{i.id}</td>
                  <td className={C}><span className="inline-flex items-center gap-1.5"><span className="font-medium capitalize">{i.tipo} · {i.bairro}</span>{i.destaque_investimento && <Ic.spark size={13} className="text-warn" aria-label="destaque para investidor" />}{i.fotos.length > 0 && <span className="text-[10px] text-ink-muted" title={`${i.fotos.length} foto(s)`}>· {i.fotos.length} 📷</span>}</span></td>
                  <td className={C}>{i.operacao === "aluguel" ? <Badge tom="info">aluguel</Badge> : <Badge>venda</Badge>}</td>
                  <td className={cx(C, "text-ink-muted")}>{REGIAO[i.regiao] ?? i.regiao}</td>
                  <td className={cx(C, "tabular-nums")}>{i.quartos}q · {i.suites}s · {i.vagas}v</td>
                  <td className={cx(C, "tabular-nums")}>{num(i.area_m2)} m²</td>
                  <td className={cx(C, "font-medium tabular-nums")}>{brl(i.preco)}{i.operacao === "aluguel" && <span className="text-xs font-normal text-ink-muted">/mês</span>}</td>
                  <td className={cx(C, "tabular-nums text-ink-muted")}>{i.condominio ? brl(i.condominio) : "—"}</td>
                  <td className={C}><Button variante="fantasma" tamanho="sm" onClick={() => setSel(i)} aria-label={`Detalhes do imóvel ${i.id}`} title="Ver detalhes"><Ic.eye size={16} /></Button></td>
                </tr>))}
            </Table>
            <Paginacao {...pag} />
          </>) : (<>
            <div className="grid gap-3 p-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {pag.fatia.map((i) => (
                <button key={i.id} onClick={() => setSel(i)} className="overflow-hidden rounded-xl border border-line bg-surface text-left transition hover:shadow-md">
                  {i.fotos[0] ? <img src={i.fotos[0]} alt="" className="h-36 w-full object-cover" loading="lazy" /> : <div className="grid h-36 w-full place-items-center bg-canvas text-ink-muted"><Ic.building size={22} /></div>}
                  <div className="p-3"><div className="flex items-start justify-between gap-2"><p className="font-medium capitalize">{i.tipo} · {i.bairro}</p><span className="font-mono text-[10px] text-ink-muted">{i.id}</span></div>
                    <p className="text-xs text-ink-muted">{i.quartos} quartos · {num(i.area_m2)} m² · {REGIAO[i.regiao]}</p>
                    <p className="mt-1.5 text-sm font-semibold tabular-nums">{brl(i.preco)}{i.operacao === "aluguel" && <span className="text-xs font-normal text-ink-muted">/mês</span>}</p></div>
                </button>))}
            </div>
            <Paginacao {...pag} />
          </>)}
      </Card>

      <DetalheImovel imovel={sel} onFechar={() => setSel(null)} onAtualizar={(im) => setSel(im)} />
    </div>
  );
}


/** Popup de detalhes: carrossel + gestão de fotos (enviar, remover, definir capa). */
function DetalheImovel({ imovel, onFechar, onAtualizar }: { imovel: Imovel | null; onFechar: () => void; onAtualizar: (im: Imovel) => void }) {
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(0);
  const [arrastando, setArrastando] = useState(false);
  const [remover_, setRemover] = useState<string | null>(null);   // URL da foto aguardando confirmação
  const atualizar = (im: Imovel) => { onAtualizar(im); qc.invalidateQueries({ queryKey: ["imoveis"] }); };
  const remover = useMutation({ mutationFn: (url: string) => api.removerFotoImovel(imovel!.id, url), onSuccess: (im) => { atualizar(im); setRemover(null); }, onError: (e: Error) => { setErro(e.message); setRemover(null); } });
  const capa = useMutation({ mutationFn: (url: string) => api.reordenarFotosImovel(imovel!.id, [url, ...imovel!.fotos.filter((f) => f !== url)]), onSuccess: atualizar, onError: (e: Error) => setErro(e.message) });
  const receber = async (arquivos: FileList | File[] | null | undefined) => {
    if (!imovel || !arquivos?.length) return;
    setErro(""); const lista = Array.from(arquivos).slice(0, 12 - imovel.fotos.length);
    if (lista.length < arquivos.length) setErro("Limite de 12 fotos por imóvel — as excedentes foram ignoradas.");
    let atual = imovel;
    for (const [k, arq] of lista.entries()) {
      setEnviando(k + 1);
      try { atual = await api.enviarFotoImovel(atual.id, await redimensionarImagem(arq)); onAtualizar(atual); }
      catch (e) { setErro((e as Error).message); break; }
    }
    setEnviando(0); qc.invalidateQueries({ queryKey: ["imoveis"] });
  };
  if (!imovel) return null;
  const sel = imovel;
  return (
    <Modal aberto onFechar={onFechar} largura="max-w-3xl"
      titulo={<span className="flex flex-wrap items-center gap-2"><span className="font-mono text-sm text-ink-muted">{sel.id}</span><span className="capitalize">{sel.tipo} · {sel.bairro}</span><SeloInteressados imovelId={sel.id} /></span>}
      rodape={<Button onClick={onFechar}>Fechar</Button>}>
      <ConfirmDialog aberto={!!remover_} titulo="Remover esta foto?" descricao={<>A foto será apagada do imóvel <b>{sel.id}</b> e do servidor. Essa ação não pode ser desfeita.</>}
        confirmar="Remover foto" carregando={remover.isPending} onCancelar={() => setRemover(null)} onConfirmar={() => remover_ && remover.mutate(remover_)}
        previa={remover_ && <img src={remover_} alt="" className="h-28 w-full rounded-lg object-cover ring-1 ring-line" />} />
      <div className="grid gap-5 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <div className="space-y-3">
          <Carrossel fotos={sel.fotos} altura="h-64 md:h-72" aoRemover={(u) => setRemover(u)} capa={(u) => capa.mutate(u)} />
          <div onDragOver={(e) => { e.preventDefault(); setArrastando(true); }} onDragLeave={() => setArrastando(false)} onDrop={(e) => { e.preventDefault(); setArrastando(false); receber(e.dataTransfer.files); }}
            className={cx("flex flex-wrap items-center justify-between gap-2 rounded-lg border-2 border-dashed px-3 py-2.5 text-xs transition", arrastando ? "border-brand-accent bg-info-soft" : "border-line")}>
            <span className="text-ink-muted">{enviando ? `Enviando foto ${enviando}…` : `Arraste fotos aqui ou escolha arquivos (JPEG, PNG, WebP; reduzimos para 1280 px). ${sel.fotos.length}/12`}</span>
            <Button type="button" tamanho="sm" icone={<Ic.plus size={13} />} onClick={() => input.current?.click()} disabled={!!enviando || sel.fotos.length >= 12}>Adicionar fotos</Button>
            <input ref={input} type="file" accept="image/*" multiple className="hidden" onChange={(e) => { receber(e.target.files); e.target.value = ""; }} />
          </div>
          {erro && <p className="rounded-lg bg-bad-soft px-3 py-2 text-xs text-bad-strong">{erro}</p>}
        </div>
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2"><Badge tom={sel.operacao === "aluguel" ? "info" : "neutro"}>{sel.operacao}</Badge><Badge>{sel.tipo}</Badge><Badge>{REGIAO[sel.regiao]}</Badge>{sel.destaque_investimento && <Badge tom="warn" icone={<Ic.spark size={10} />}>destaque para investidor</Badge>}</div>
          <p className="text-2xl font-semibold tabular-nums">{brl(sel.preco)}{sel.operacao === "aluguel" && <span className="text-sm font-normal text-ink-muted">/mês</span>}{sel.condominio ? <span className="ml-2 text-sm font-normal text-ink-muted">+ {brl(sel.condominio)} cond.</span> : null}</p>
          <dl className="grid grid-cols-3 gap-x-4 gap-y-2 text-sm">
            {[["Quartos", String(sel.quartos)], ["Suítes", String(sel.suites)], ["Vagas", String(sel.vagas)], ["Área", `${num(sel.area_m2)} m²`], ["R$/m²", brl(sel.preco / sel.area_m2)], ["Cidade", sel.cidade]].map(([k, v]) => <div key={k}><dt className="text-xs text-ink-muted">{k}</dt><dd className="font-medium">{v}</dd></div>)}
          </dl>
          <div><p className="mb-1 text-xs font-medium text-ink-muted">Descrição (texto que alimenta o embedding)</p><p className="rounded-lg bg-canvas p-3 text-sm">{sel.descricao}</p></div>
          {/* A pergunta que o corretor faz olhando um imóvel é "com quem eu falo sobre ele". */}
          <div>
            <p className="mb-1 text-xs font-medium text-ink-muted">Quem está de olho</p>
            <InteressadosNoImovel imovelId={sel.id} />
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-ink-muted">Quem a Mora avisaria</p>
            <SimularReativacao imovelId={sel.id} />
          </div>
        </div>
      </div>
    </Modal>
  );
}
