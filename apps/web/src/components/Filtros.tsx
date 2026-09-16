import { useEffect, useId, useState } from "react";
import { REGIOES, TIPOS, brl, type Filtros as F } from "../lib/api";
import { Botao, Campo, Chip, Entrada, Escolha, cx } from "../lib/ui";
import { Ic } from "./Icones";

/** Barra de filtros do catálogo.
 *
 *  Antes eram quatro selects: operação, região, quartos e preço máximo. A base tem 18 bairros,
 *  três tipos, suítes, vagas e área — e nada disso era pesquisável; quem quisesse "dois quartos com
 *  suíte em Perdizes" tinha que rolar a lista inteira da Zona Oeste.
 *
 *  Layout em dois níveis de propósito: a linha de cima resolve a busca da maioria (o que, onde,
 *  quanto) e o resto fica atrás de "Mais filtros", para a tela não abrir com onze controles.
 */
export function Filtros({ value, bairros, onChange, total }: {
  value: F;
  bairros: { bairro: string; n: number }[];
  onChange: (f: F) => void;
  total?: number;
}) {
  const id = useId();
  const [abertos, setAbertos] = useState(false);
  const [texto, setTexto] = useState(value.texto ?? "");

  // A busca por texto espera a digitação parar: sem isso é uma requisição por tecla.
  useEffect(() => {
    if ((value.texto ?? "") === texto) return;
    const t = setTimeout(() => onChange({ ...value, texto: texto || undefined }), 350);
    return () => clearTimeout(t);
  }, [texto]);                                   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setTexto(value.texto ?? ""); }, [value.texto]);

  const set = (k: keyof F, v: string) =>
    onChange({ ...value, [k]: v === "" ? undefined : NUMERICOS.has(k) ? Number(v) : v });

  const chips = descreverFiltros(value);
  const avancadosAtivos = chips.filter((c) => AVANCADOS.has(c.k)).length;

  return (
    <section aria-label="Filtros de busca" className="rounded-lg bg-surface p-3 shadow-card ring-1 ring-line sm:p-4">
      <div className="grid gap-3 md:grid-cols-[1.4fr_1fr_1fr_auto]">
        <Campo rotulo="Bairro, tipo ou palavra-chave" id={`${id}-texto`}>
          <div className="relative">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft"><Ic.busca size={17} /></span>
            <Entrada id={`${id}-texto`} className="pl-9" type="search" list={`${id}-bairros`}
                     placeholder="Ex.: Perdizes, varanda, studio"
                     value={texto} onChange={(e) => setTexto(e.target.value)} />
            {/* datalist em vez de combobox: dá autocompletar nativo, acessível e sem JS extra */}
            <datalist id={`${id}-bairros`}>
              {bairros.map((b) => <option key={b.bairro} value={b.bairro}>{`${b.n} imóveis`}</option>)}
            </datalist>
          </div>
        </Campo>

        <Campo rotulo="Operação" id={`${id}-op`}>
          <Escolha id={`${id}-op`} value={value.operacao ?? ""} onChange={(e) => set("operacao", e.target.value)}>
            <option value="">Comprar ou alugar</option>
            <option value="venda">Comprar</option>
            <option value="aluguel">Alugar</option>
          </Escolha>
        </Campo>

        <Campo rotulo="Tipo" id={`${id}-tipo`}>
          <Escolha id={`${id}-tipo`} value={value.tipo ?? ""} onChange={(e) => set("tipo", e.target.value)}>
            <option value="">Qualquer tipo</option>
            {Object.entries(TIPOS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Escolha>
        </Campo>

        <div className="flex items-end">
          <Botao variante="secundario" largo icone={<Ic.filtro size={16} />}
                 aria-expanded={abertos} aria-controls={`${id}-mais`}
                 onClick={() => setAbertos((v) => !v)}>
            Mais filtros{avancadosAtivos > 0 && <span className="ml-1 rounded-full bg-brand-accent px-1.5 text-[11px] text-white">{avancadosAtivos}</span>}
          </Botao>
        </div>
      </div>

      {/* Renderização condicional, e não `hidden`: a utilitária `grid` define display e vence o
          atributo [hidden] na cascata — o painel nascia aberto com onze controles na cara de quem
          chegava. Erro clássico de Tailwind, invisível no código e óbvio na tela. */}
      {abertos && (
      <div id={`${id}-mais`} className="mt-3 grid gap-3 border-t border-line pt-3 sm:grid-cols-2 lg:grid-cols-4">
        <Campo rotulo="Região" id={`${id}-reg`}>
          <Escolha id={`${id}-reg`} value={value.regiao ?? ""} onChange={(e) => set("regiao", e.target.value)}>
            <option value="">Toda a cidade</option>
            {Object.entries(REGIOES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Escolha>
        </Campo>
        <Campo rotulo="Quartos (mínimo)" id={`${id}-q`}>
          <Escolha id={`${id}-q`} value={value.quartos ?? ""} onChange={(e) => set("quartos", e.target.value)}>
            <option value="">Qualquer</option>
            {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}+</option>)}
          </Escolha>
        </Campo>
        <Campo rotulo="Suítes (mínimo)" id={`${id}-s`}>
          <Escolha id={`${id}-s`} value={value.suites ?? ""} onChange={(e) => set("suites", e.target.value)}>
            <option value="">Qualquer</option>
            {[1, 2, 3].map((n) => <option key={n} value={n}>{n}+</option>)}
          </Escolha>
        </Campo>
        <Campo rotulo="Vagas (mínimo)" id={`${id}-v`}>
          <Escolha id={`${id}-v`} value={value.vagas ?? ""} onChange={(e) => set("vagas", e.target.value)}>
            <option value="">Qualquer</option>
            {[1, 2, 3].map((n) => <option key={n} value={n}>{n}+</option>)}
          </Escolha>
        </Campo>
        <Campo rotulo="Preço mínimo" id={`${id}-pmin`}>
          <Entrada id={`${id}-pmin`} type="number" min={0} step={50000} inputMode="numeric" placeholder="R$ 0"
                   value={value.preco_min ?? ""} onChange={(e) => set("preco_min", e.target.value)} />
        </Campo>
        <Campo rotulo="Preço máximo" id={`${id}-pmax`}>
          <Entrada id={`${id}-pmax`} type="number" min={0} step={50000} inputMode="numeric" placeholder="Sem limite"
                   value={value.preco_max ?? ""} onChange={(e) => set("preco_max", e.target.value)} />
        </Campo>
        <Campo rotulo="Área mínima (m²)" id={`${id}-area`}>
          <Entrada id={`${id}-area`} type="number" min={0} step={10} inputMode="numeric" placeholder="Qualquer"
                   value={value.area_min ?? ""} onChange={(e) => set("area_min", e.target.value)} />
        </Campo>
        <Campo rotulo="Bairro exato" id={`${id}-bairro`}>
          <Escolha id={`${id}-bairro`} value={value.bairro ?? ""} onChange={(e) => set("bairro", e.target.value)}>
            <option value="">Todos os bairros</option>
            {bairros.map((b) => <option key={b.bairro} value={b.bairro}>{b.bairro} ({b.n})</option>)}
          </Escolha>
        </Campo>
      </div>
      )}

      {chips.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3">
          <span className="text-xs font-medium text-ink-muted">
            {total != null ? `${total} ${total === 1 ? "imóvel" : "imóveis"} com` : "Filtros:"}
          </span>
          {chips.map((c) => (
            <Chip key={c.k} aoRemover={() => set(c.k, "")} rotuloRemover={`Remover filtro ${c.rotulo}: ${c.valor}`}>
              {/* hierarquia por peso, não por cor: ink-soft sobre o fundo do chip fica em 4,3:1 */}
              <span className="font-normal">{c.rotulo}:</span>&nbsp;<span className="font-semibold text-ink">{c.valor}</span>
            </Chip>
          ))}
          <button onClick={() => onChange({})} className={cx("text-xs font-semibold text-brand-accentDark underline-offset-2 hover:underline")}>
            Limpar todos
          </button>
        </div>
      )}
    </section>
  );
}

const NUMERICOS = new Set<keyof F>(["preco_min", "preco_max", "quartos", "suites", "vagas", "area_min"]);
const AVANCADOS = new Set<keyof F>(["regiao", "quartos", "suites", "vagas", "preco_min", "preco_max", "area_min", "bairro"]);

/** Chip legível. "operacao: venda" não é português; "Operação: Comprar" é. */
function descreverFiltros(f: F): { k: keyof F; rotulo: string; valor: string }[] {
  const out: { k: keyof F; rotulo: string; valor: string }[] = [];
  const add = (k: keyof F, rotulo: string, valor?: string | number | null) => {
    if (valor !== undefined && valor !== null && valor !== "") out.push({ k, rotulo, valor: String(valor) });
  };
  add("texto", "Busca", f.texto);
  add("operacao", "Operação", f.operacao === "venda" ? "Comprar" : f.operacao === "aluguel" ? "Alugar" : undefined);
  add("tipo", "Tipo", f.tipo ? TIPOS[f.tipo] ?? f.tipo : undefined);
  add("bairro", "Bairro", f.bairro);
  add("regiao", "Região", f.regiao ? REGIOES[f.regiao] ?? f.regiao : undefined);
  add("quartos", "Quartos", f.quartos ? `${f.quartos}+` : undefined);
  add("suites", "Suítes", f.suites ? `${f.suites}+` : undefined);
  add("vagas", "Vagas", f.vagas ? `${f.vagas}+` : undefined);
  add("area_min", "Área", f.area_min ? `${f.area_min} m²+` : undefined);
  add("preco_min", "A partir de", f.preco_min ? brl(f.preco_min) : undefined);
  add("preco_max", "Até", f.preco_max ? brl(f.preco_max) : undefined);
  return out;
}
