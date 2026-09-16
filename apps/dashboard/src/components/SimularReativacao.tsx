import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Button, Paginacao, Skeleton, Temperatura, cx, usePaginacao } from "./ui";
import { Ic } from "./Icons";

/** Simulação do aviso de imóvel novo — modo seco.
 *
 *  Mostra quem a Mora avisaria sobre este imóvel e por quê, SEM enviar nada. É onde se calibra a
 *  régua: os excluídos aparecem com o motivo, então dá para ver se ela está apertada demais (todo
 *  mundo fora) ou frouxa (gente que não pediu isso entrando na lista) antes de escrever para
 *  alguém de verdade.
 *
 *  Carrega sob demanda: varre os leads e não faz sentido rodar toda vez que a ficha abre.
 */
const POR_PAGINA = 5;

export function SimularReativacao({ imovelId }: { imovelId: string }) {
  const [ativo, setAtivo] = useState(false);
  const [verExcluidos, setVerExcluidos] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["reativacao", imovelId],
    queryFn: () => api.simularReativacao(imovelId),
    enabled: ativo,
  });
  // Candidatos a API já limita; excluídos, não — varrendo 500 leads, a maioria cai fora, e a lista
  // inteira aberta dentro do modal era pior que o problema que ela existe para mostrar.
  const pagCand = usePaginacao(data?.candidatos ?? [], POR_PAGINA);
  const pagFora = usePaginacao(data?.excluidos ?? [], POR_PAGINA);

  if (!ativo) {
    return (
      <Button variante="secundario" tamanho="sm" icone={<Ic.spark size={13} />} onClick={() => setAtivo(true)}>
        Simular aviso de imóvel novo
      </Button>
    );
  }
  if (isLoading || !data) return <Skeleton className="h-24" />;

  return (
    <div className="space-y-2">
      <p className="text-xs text-ink-muted">
        {data.candidatos.length === 0
          ? `Nenhum lead seria avisado (${data.avaliados} avaliados).`
          : `${data.candidatos.length} de ${data.avaliados} leads seriam avisados.`}{" "}
        <span className="text-ink-soft">Simulação: nada é enviado.</span>
      </p>

      <ul className="divide-y divide-line">
        {pagCand.fatia.map((c) => (
          <li key={c.lead_id} className="py-2">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Link to={`/leads/${c.lead_id}`} className="font-medium text-ink hover:text-brand-accent hover:underline">
                {c.nome || c.lead_id}
              </Link>
              <Temperatura t={c.temperatura} />
              <Badge tom={c.pontos >= 85 ? "good" : "info"}>{c.pontos} pts</Badge>
            </div>
            {/* Os motivos não são enfeite: é este texto que vira a primeira frase da mensagem. */}
            <p className="mt-0.5 text-xs text-ink-muted">{c.motivos.join(" · ")}</p>
          </li>
        ))}
      </ul>
      <Paginacao compacto {...pagCand} />

      {data.excluidos.length > 0 && (
        <div>
          <button onClick={() => setVerExcluidos((v) => !v)}
                  className={cx("text-xs font-medium text-ink-muted hover:text-ink")}
                  aria-expanded={verExcluidos}>
            {verExcluidos ? "Ocultar" : "Ver"} {data.excluidos.length} fora da lista
          </button>
          {verExcluidos && (
            <>
              <ul className="mt-1 space-y-0.5 text-xs text-ink-muted">
                {pagFora.fatia.map((e) => (
                  <li key={e.lead_id}>
                    <span className="text-ink">{e.nome || e.lead_id}</span> — {e.motivo}
                  </li>
                ))}
              </ul>
              <Paginacao compacto {...pagFora} />
            </>
          )}
        </div>
      )}
    </div>
  );
}
