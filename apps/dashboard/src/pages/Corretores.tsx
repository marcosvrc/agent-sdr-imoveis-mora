import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, REGIOES, type Corretor, type CorretorIn } from "../lib/api";
import { REGIAO } from "../lib/format";
import { redimensionarFoto } from "../lib/imagem";
import { Badge, Button, Card, Drawer, EmptyState, Field, Input, PageHeader, Table, Toggle, Avatar, Paginacao, usePaginacao, cx } from "../components/ui";
import { Ic } from "../components/Icons";
import { ConexaoAgenda } from "../components/ConexaoAgenda";
import { DesativarCorretor } from "../components/DesativarCorretor";

const vazio: CorretorIn = { nome: "", email: "", telefone: "", regioes: [], ativo: true, foto: null, crm_user_id: "" };
const POR_PAGINA = 10;

export function Corretores() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["corretores"], queryFn: api.corretores });
  const { data: agendas } = useQuery({ queryKey: ["calendario"], queryFn: api.statusCalendario });
  const [busca, setBusca] = useState("");
  const [edit, setEdit] = useState<{ id?: string; form: CorretorIn } | null>(null);
  const [erro, setErro] = useState("");
  const [desativando, setDesativando] = useState<Corretor | null>(null);
  const lista = useMemo(() => { const q = busca.trim().toLowerCase(); return (data ?? []).filter((c) => !q || [c.nome, c.email, c.telefone, c.id].some((v) => v?.toLowerCase().includes(q))); }, [data, busca]);
  const pag = usePaginacao(lista, POR_PAGINA, "corretores");
  const ok = () => { qc.invalidateQueries({ queryKey: ["corretores"] }); setEdit(null); setErro(""); };
  const salvar = useMutation({ mutationFn: (e: { id?: string; form: CorretorIn }) => e.id ? api.atualizarCorretor(e.id, e.form) : api.criarCorretor(e.form), onSuccess: ok, onError: (e: Error) => setErro(e.message) });
  const alternar = useMutation({ mutationFn: (c: Corretor) => api.atualizarCorretor(c.id, { nome: c.nome, email: c.email, telefone: c.telefone, regioes: c.regioes, ativo: !c.ativo, foto: c.foto, crm_user_id: c.crm_user_id }), onSuccess: () => qc.invalidateQueries({ queryKey: ["corretores"] }) });
  const abrirEdicao = (c: Corretor) => { setErro(""); setEdit({ id: c.id, form: { nome: c.nome, email: c.email ?? "", telefone: c.telefone ?? "", regioes: c.regioes, ativo: c.ativo, foto: c.foto ?? null, crm_user_id: c.crm_user_id ?? "" } }); };

  return (
    <div>
      <PageHeader titulo="Corretores" descricao="Quem recebe os handoffs e as visitas — as regiões orientam o roteamento"
        acoes={<Button variante="primario" icone={<Ic.plus size={14} />} onClick={() => { setErro(""); setEdit({ form: vazio }); }}>Novo corretor</Button>} />
      <Card semPadding>
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
          <div className="relative min-w-[220px] flex-1"><Ic.search size={15} className="pointer-events-none absolute left-2.5 top-2.5 text-ink-faint" /><Input className="pl-8" placeholder="Buscar por nome, e-mail, telefone…" value={busca} onChange={(e) => { setBusca(e.target.value); pag.setPagina(1); }} /></div>
          <span className="text-xs text-ink-muted">{data ? `${data.filter((c) => c.ativo).length} ativos · ${data.length} no total` : ""}</span>
        </div>
        {!isLoading && !data?.length ? <EmptyState icone="badge" titulo="Nenhum corretor cadastrado" descricao="Cadastre a equipe para distribuir handoffs e visitas." acao={<Button variante="primario" onClick={() => setEdit({ form: vazio })}>Cadastrar o primeiro</Button>} /> : (<>
          <Table colunas={["Corretor", "Contato", "Regiões", { h: "Em atendimento", cls: "text-right" }, { h: "Visitas", cls: "text-right" }, { h: "Agenda", cls: "text-center" }, "Status", ""]}
            vazio={!isLoading && lista.length === 0 ? <EmptyState icone="search" titulo="Nenhum corretor encontrado" descricao="Tente outro termo de busca." /> : undefined}>
            {pag.fatia.map((c) => (
              <tr key={c.id} className={cx("hover:bg-surface-2", !c.ativo && "text-ink-muted")}>
                <td className="px-4 py-2.5"><button onClick={() => abrirEdicao(c)} className="flex items-center gap-2.5 text-left"><Avatar nome={c.nome} foto={c.foto} tamanho={32} /><span><span className="block font-medium hover:underline">{c.nome}</span><span className="block font-mono text-[11px] text-ink-muted">{c.id}</span></span></button></td>
                <td className="px-4 py-2.5 text-xs text-ink-muted">{c.email || "—"}<br />{c.telefone || ""}</td>
                <td className="px-4 py-2.5"><span className="flex flex-wrap gap-1">{c.regioes.length ? c.regioes.map((r) => <Badge key={r}>{REGIAO[r] ?? r}</Badge>) : <span className="text-xs text-ink-faint">todas</span>}</span></td>
                <td className="px-4 py-2.5 text-right tabular-nums">{c.leads_handoff ? <Link to={`/leads?corretor=${c.id}&estagio=handoff`} className="font-medium text-brand-accent hover:underline" title="Ver leads em atendimento">{c.leads_handoff}</Link> : 0}</td>
                <td className="px-4 py-2.5 text-right tabular-nums">{c.visitas ? <Link to="/agenda" className="font-medium text-brand-accent hover:underline" title="Ver na agenda">{c.visitas}</Link> : 0}</td>
                <td className="px-4 py-2.5 text-center">{agendas?.corretores?.[c.id]
                  ? <span title="Google Agenda conectada" className="inline-flex text-[var(--status-good)]"><Ic.calendar size={15} /></span>
                  : <span title="Usando a grade interna" className="inline-flex text-ink-faint"><Ic.calendar size={15} /></span>}</td>
                <td className="px-4 py-2.5"><Toggle on={c.ativo} onChange={() => alternar.mutate(c)} label={c.ativo ? "ativo" : "inativo"} /></td>
                <td className="px-4 py-2.5"><span className="flex justify-end gap-1"><Button variante="fantasma" tamanho="sm" onClick={() => abrirEdicao(c)} aria-label="Editar"><Ic.edit size={14} /></Button><Button variante="fantasma" tamanho="sm" onClick={() => setDesativando(c)} aria-label={`Desativar ${c.nome}`}><Ic.trash size={14} /></Button></span></td>
              </tr>))}
          </Table>
          <Paginacao {...pag} />
        </>)}
      </Card>

      {desativando && (
        <DesativarCorretor corretor={desativando} ativos={(data ?? []).filter((c) => c.ativo)}
                           onFechar={() => setDesativando(null)} />
      )}

      <Drawer aberto={!!edit} onFechar={() => setEdit(null)} titulo={edit?.id ? "Editar corretor" : "Novo corretor"}
        rodape={<><Button onClick={() => setEdit(null)}>Cancelar</Button><Button variante="primario" disabled={salvar.isPending || !edit?.form.nome.trim()} onClick={() => edit && salvar.mutate(edit)}>Salvar</Button></>}>
        {edit && (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); salvar.mutate(edit); }}>
            <FotoCorretor nome={edit.form.nome} foto={edit.form.foto ?? null} onChange={(f) => setEdit({ ...edit, form: { ...edit.form, foto: f } })} onErro={setErro} />
            <Field label="Nome"><Input autoFocus value={edit.form.nome} onChange={(e) => setEdit({ ...edit, form: { ...edit.form, nome: e.target.value } })} placeholder="Ana Souza" /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="E-mail"><Input type="email" value={edit.form.email ?? ""} onChange={(e) => setEdit({ ...edit, form: { ...edit.form, email: e.target.value } })} placeholder="ana@verticeimoveis.com.br" /></Field>
              <Field label="Telefone"><Input value={edit.form.telefone ?? ""} onChange={(e) => setEdit({ ...edit, form: { ...edit.form, telefone: e.target.value } })} placeholder="5511999990000" /></Field>
            </div>
            <Field label="ID no CRM" dica="users.id desta pessoa no CRM. Vazio: o encaminhamento fica na fila para quem aceitar.">
              <Input value={edit.form.crm_user_id ?? ""} onChange={(e) => setEdit({ ...edit, form: { ...edit.form, crm_user_id: e.target.value } })} placeholder="00000000-0000-0000-0000-000000000000" />
            </Field>
            <Field label="Regiões que atende" dica="Sem seleção = atende todas">
              <div className="flex flex-wrap gap-1.5">{REGIOES.map((r) => { const on = edit.form.regioes.includes(r); return <button type="button" key={r} onClick={() => setEdit({ ...edit, form: { ...edit.form, regioes: on ? edit.form.regioes.filter((x) => x !== r) : [...edit.form.regioes, r] } })} className={cx("rounded-full border px-2.5 py-1 text-xs font-medium", on ? "border-brand bg-brand text-brand-ink" : "border-line text-ink-muted hover:bg-surface-2")}>{REGIAO[r]}</button>; })}</div>
            </Field>
            <Toggle on={edit.form.ativo} onChange={(v) => setEdit({ ...edit, form: { ...edit.form, ativo: v } })} label="Ativo (recebe handoffs e visitas)" />
            {edit.id && <ConexaoAgenda corretorId={edit.id} />}
            {erro && <p className="rounded-lg bg-bad-soft px-3 py-2 text-xs text-bad-strong">{erro}</p>}
          </form>
        )}
      </Drawer>
    </div>
  );
}

/** Foto do corretor: arraste ou escolha um arquivo; é recortada e reduzida para 256 px no navegador antes de ir ao servidor. */
function FotoCorretor({ nome, foto, onChange, onErro }: { nome: string; foto: string | null; onChange: (f: string | null) => void; onErro: (m: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [arrastando, setArrastando] = useState(false);
  const [processando, setProcessando] = useState(false);
  const receber = async (arquivo?: File | null) => {
    if (!arquivo) return;
    setProcessando(true); onErro("");
    try { onChange(await redimensionarFoto(arquivo)); } catch (e) { onErro((e as Error).message); } finally { setProcessando(false); }
  };
  return (
    <div className="flex items-center gap-4">
      <div onDragOver={(e) => { e.preventDefault(); setArrastando(true); }} onDragLeave={() => setArrastando(false)} onDrop={(e) => { e.preventDefault(); setArrastando(false); receber(e.dataTransfer.files?.[0]); }}
        onClick={() => input.current?.click()} role="button" tabIndex={0} onKeyDown={(e) => e.key === "Enter" && input.current?.click()} aria-label="Enviar foto do corretor"
        className={cx("relative grid h-24 w-24 shrink-0 cursor-pointer place-items-center overflow-hidden rounded-full border-2 border-dashed transition", arrastando ? "border-brand-accent bg-info-soft" : "border-line hover:border-line")}>
        {foto ? <img src={foto} alt="" className="h-full w-full object-cover" /> : <Avatar nome={nome || "?"} tamanho={88} />}
        {processando && <span className="absolute inset-0 grid place-items-center bg-surface text-xs text-ink-muted">…</span>}
        <span className="absolute bottom-0 left-0 right-0 bg-black/50 py-0.5 text-center text-[10px] text-white">{foto ? "trocar" : "foto"}</span>
      </div>
      <div className="text-xs text-ink-muted">
        <p className="font-medium text-ink">Foto do corretor</p>
        <p>Arraste uma imagem ou clique para escolher. PNG, JPEG ou WebP; recortamos em quadrado e reduzimos para 256 px.</p>
        <div className="mt-2 flex gap-2"><Button type="button" tamanho="sm" onClick={() => input.current?.click()}>Escolher arquivo</Button>{foto && <Button type="button" tamanho="sm" variante="fantasma" onClick={() => onChange(null)}>Remover</Button>}</div>
      </div>
      <input ref={input} type="file" accept="image/*" className="hidden" onChange={(e) => { receber(e.target.files?.[0]); e.target.value = ""; }} />
    </div>
  );
}
