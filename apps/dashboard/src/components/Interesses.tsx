import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Interesse, type SituacaoInteresse } from "../lib/api";
import { brl, relativo } from "../lib/format";
import { Badge, EmptyState, Paginacao, Select, Skeleton, Temperatura, cx, usePaginacao } from "./ui";
import { Ic } from "./Icons";

/** Interesse: o vínculo lead↔imóvel que antes não sobrevivia à conversa.
 *
 *  Duas leituras, o mesmo dado. Na ficha do lead: por quais imóveis ele passou e em que pé cada um
 *  está. Na ficha do imóvel: com quem falar sobre ele. A escrita é a mesma dos dois lados — mudar a
 *  situação para `descartado` é o que impede a Mora de reoferecer o imóvel na próxima conversa.
 */

const ROTULO: Record<SituacaoInteresse, string> = {
  sugerido: "Mora mostrou",
  interessado: "Interessado",   // curto de propósito: cabe no seletor de 176 px da aba lateral
  descartado: "Descartado",
  visita_marcada: "Visita marcada",
};

const TOM: Record<SituacaoInteresse, "neutro" | "info" | "good" | "bad"> = {
  sugerido: "neutro", interessado: "info", descartado: "bad", visita_marcada: "good",
};

const ORIGEM: Record<string, string> = { agente: "pela Mora", site: "pelo site", corretor: "pelo corretor" };

/** `sugerido` fica de fora: quem escreve isso é o agente, e rebaixar um interesse declarado para
 *  "só mostrei" apagaria informação. Para desfazer um descarte, marque "Demonstrou interesse". */
const ESCOLHAS: SituacaoInteresse[] = ["interessado", "descartado", "visita_marcada"];

function SeletorSituacao({ atual, onMudar, ocupado }:
  { atual: SituacaoInteresse; onMudar: (s: SituacaoInteresse) => void; ocupado: boolean }) {
  return (
    <Select className="w-44" value={ESCOLHAS.includes(atual) ? atual : ""} disabled={ocupado}
            aria-label="Situação do interesse"
            onChange={(e) => e.target.value && onMudar(e.target.value as SituacaoInteresse)}>
      {!ESCOLHAS.includes(atual) && <option value="">{ROTULO[atual]}</option>}
      {ESCOLHAS.map((s) => <option key={s} value={s}>{ROTULO[s]}</option>)}
    </Select>
  );
}

export function InteressesDoLead({ leadId }: { leadId: string }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["interesses", leadId], queryFn: () => api.interessesDoLead(leadId) });
  const mudar = useMutation({
    mutationFn: ({ imovelId, situacao }: { imovelId: string; situacao: SituacaoInteresse }) =>
      api.mudarInteresse(leadId, imovelId, situacao),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["interesses", leadId] }),
  });

  if (isLoading) return <Skeleton className="h-24" />;
  if (!data?.length) {
    return <EmptyState icone="building" titulo="Nenhum imóvel ainda"
                       descricao="Assim que a Mora sugerir um imóvel — ou o cliente abrir uma ficha no site — ele aparece aqui." />;
  }

  // Lista, não tabela: este bloco vive numa aba lateral de ~430 px, e quatro colunas ali viram
  // texto quebrado e seletor cortado — visto na captura antes de trocar.
  return (
    <ul className="divide-y divide-line">
      {data.map((i: Interesse) => (
        <li key={i.imovel_id} className="space-y-1.5 py-3 first:pt-0">
          <div className="flex items-start justify-between gap-3">
            <p className="font-medium capitalize text-ink">{i.tipo} · {i.bairro}</p>
            <p className="shrink-0 tabular-nums font-medium text-ink">
              {brl(i.preco)}{i.operacao === "aluguel" && <span className="text-xs font-normal text-ink-muted">/mês</span>}
            </p>
          </div>
          <p className="text-xs text-ink-muted">
            {i.quartos} quarto{i.quartos === 1 ? "" : "s"} · {i.area_m2} m² · <span className="font-mono">{i.imovel_id}</span>
          </p>
          {i.motivo && <p className="text-xs italic text-ink-muted">“{i.motivo}”</p>}
          <div className="flex flex-wrap items-center gap-2 pt-0.5">
            <SeletorSituacao atual={i.situacao} ocupado={mudar.isPending}
                             onMudar={(situacao) => mudar.mutate({ imovelId: i.imovel_id, situacao })} />
            <span className="text-[11px] text-ink-muted">
              {ORIGEM[i.origem] ?? i.origem} · {relativo(i.atualizado_em)}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Imóvel disputado tem dezenas de interessados, e a lista inteira transformava o modal num
 *  rolamento sem fim. Cinco por página: a coluna é estreita e a pergunta é "quem chamo primeiro",
 *  que a ordenação por temperatura já responde nas primeiras linhas. */
const POR_PAGINA = 5;

export function InteressadosNoImovel({ imovelId }: { imovelId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["interessados", imovelId], queryFn: () => api.interessadosNoImovel(imovelId),
  });
  // O hook precisa rodar antes de qualquer return condicional (regra dos hooks do React).
  const pag = usePaginacao(data ?? [], POR_PAGINA);

  if (isLoading) return <Skeleton className="h-20" />;
  if (!data?.length) {
    return <p className="text-sm text-ink-muted">Ninguém demonstrou interesse neste imóvel ainda.</p>;
  }

  return (
    <>
    <ul className="divide-y divide-line">
      {pag.fatia.map((p) => (
        <li key={p.lead_id} className="py-2 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Link to={`/leads/${p.lead_id}`} className="font-medium text-ink hover:text-brand-accent hover:underline">
              {p.nome || p.lead_id}
            </Link>
            <Temperatura t={p.temperatura} />
            <Badge tom={TOM[p.situacao]}>{ROTULO[p.situacao]}</Badge>
          </div>
          {/* Contato e data na segunda linha: na primeira, o telefone empurrava a data para baixo
              sozinha, e a lista ficava com buraco entre os nomes. */}
          <p className={cx("mt-0.5 flex flex-wrap gap-x-2 text-xs text-ink-muted")}>
            {p.telefone && <span className="tabular-nums">{p.telefone}</span>}
            <span>{relativo(p.atualizado_em)}</span>
          </p>
        </li>
      ))}
    </ul>
    <Paginacao compacto {...pag} />
    </>
  );
}

/** Contador para o cabeçalho da ficha do imóvel — some quando ninguém demonstrou interesse. */
export function SeloInteressados({ imovelId }: { imovelId: string }) {
  const { data } = useQuery({ queryKey: ["interessados", imovelId], queryFn: () => api.interessadosNoImovel(imovelId) });
  if (!data?.length) return null;
  return (
    <Badge tom="info" icone={<Ic.contato size={12} />}>
      {data.length} {data.length === 1 ? "interessado" : "interessados"}
    </Badge>
  );
}
