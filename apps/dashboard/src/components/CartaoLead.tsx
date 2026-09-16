import { brl, type Cartao } from "../lib/api";
import { INTENCAO, REGIAO } from "../lib/format";
import { Badge } from "./ui";
import { Ic } from "./Icons";

const ROTULO_CAMPO: Record<string, string> = { intencao: "intenção", regiao: "região", preco_max: "orçamento", quartos: "quartos",
  urgencia: "prazo", perfil_investidor: "perfil de investidor", ticket: "ticket", retorno_esperado: "retorno esperado" };

/** Mostra o que o lead JÁ disse e, separado, o que ainda falta perguntar — o vazio vira ação, não traço. */
export function CartaoLead({ c }: { c: Cartao }) {
  const preenchidos: [string, string][] = [
    ["Intenção", INTENCAO[c.intencao] && c.intencao !== "indefinida" ? INTENCAO[c.intencao] : ""],
    ["Região", c.regiao ? REGIAO[c.regiao] ?? c.regiao : ""],
    ["Bairros", c.bairros.join(", ")],
    ["Orçamento", c.preco_max ? `até ${brl(c.preco_max)}` : ""],
    ["Quartos", c.quartos ? `${c.quartos}+` : ""],
    ["Tipo", c.tipo_imovel ?? ""],
    ["Prazo", c.urgencia?.replace(/_/g, " ") ?? ""],
    ["Perfil de investidor", c.perfil_investidor ?? ""],
    ["Ticket", c.ticket ? brl(c.ticket) : ""],
    ["Retorno esperado", c.retorno_esperado ?? ""],
  ].filter((l): l is [string, string] => Boolean(l[1]));

  const obrigatorios = c.intencao === "investimento"
    ? ["intencao", "perfil_investidor", "ticket", "retorno_esperado"]
    : ["intencao", "regiao", "preco_max", "quartos", "urgencia"];
  const faltam = obrigatorios.filter((k) => {
    const v = (c as unknown as Record<string, unknown>)[k];
    return v == null || v === "" || v === "indefinida";
  });

  return (
    <div className="space-y-3">
      {preenchidos.length === 0 ? (
        <p className="text-sm text-ink-muted">O lead ainda não informou nada — a Mora está qualificando.</p>
      ) : (
        <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-2">
          {preenchidos.map(([k, v]) => (
            <div key={k} className="min-w-0">
              <dt className="text-[11px] uppercase tracking-wide text-ink-muted">{k}</dt>
              <dd className="truncate font-medium text-ink" title={v}>{v}</dd>
            </div>))}
        </dl>
      )}
      {faltam.length > 0 && (
        <p className="flex flex-wrap items-center gap-1.5 rounded-lg bg-warn-soft px-2.5 py-2 text-xs text-warn-strong">
          <Ic.info size={13} /> Ainda falta perguntar:
          {faltam.map((k) => <span key={k} className="rounded bg-surface px-1.5 py-0.5 font-medium">{ROTULO_CAMPO[k] ?? k}</span>)}
        </p>
      )}
      {c.imoveis_visualizados.length > 0 && (
        <div><p className="mb-1 text-[11px] uppercase tracking-wide text-ink-muted">Imóveis que viu no site</p>
          <p className="flex flex-wrap gap-1">{c.imoveis_visualizados.map((i) => <Badge key={i}>{i}</Badge>)}</p></div>
      )}
      {c.pediu_visita && <p className="flex items-center gap-1.5 text-xs text-good-strong"><Ic.check size={13} /> Pediu para visitar um imóvel</p>}
    </div>
  );
}
