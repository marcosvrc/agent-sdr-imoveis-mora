// Conexão da agenda do corretor com o Google. O consentimento acontece no navegador dele;
// aqui só mostramos o estado e abrimos a janela. Nenhum token passa por esta tela.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Badge, Button, ConfirmDialog } from "./ui";
import { Ic } from "./Icons";
import { useState } from "react";

export function ConexaoAgenda({ corretorId }: { corretorId: string }) {
  const qc = useQueryClient();
  const [desconectando, setDesconectando] = useState(false);
  const { data } = useQuery({ queryKey: ["calendario"], queryFn: api.statusCalendario });
  const conectado = !!data?.corretores?.[corretorId];

  const conectar = useMutation({
    mutationFn: () => api.conectarCalendario(corretorId),
    onSuccess: ({ url }) => {
      // O Google exige que o consentimento seja dado numa janela do próprio corretor.
      window.open(url, "_blank", "width=520,height=640,noopener");
    },
  });
  const desconectar = useMutation({
    mutationFn: () => api.desconectarCalendario(corretorId),
    onSuccess: () => { setDesconectando(false); qc.invalidateQueries({ queryKey: ["calendario"] }); },
  });

  if (!data?.disponivel) {
    return (
      <p className="rounded-lg border border-line bg-surface-2 px-3 py-2.5 text-xs text-ink-muted">
        Integração com o Google Agenda não configurada neste ambiente. Sem ela, a Mora usa a grade
        interna de horários — as visitas continuam sendo marcadas normalmente.
      </p>
    );
  }

  return (
    <div className="rounded-lg border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Ic.calendar size={16} className="text-ink-muted" />
        <span className="text-sm font-medium">Google Agenda</span>
        {conectado
          ? <Badge tom="good" icone={<Ic.check size={10} />}>conectada</Badge>
          : <Badge tom="neutro">não conectada</Badge>}
        <span className="ml-auto">
          {conectado
            ? <Button tamanho="sm" onClick={() => setDesconectando(true)}>Desconectar</Button>
            : <Button tamanho="sm" variante="primario" icone={<Ic.external size={13} />}
                onClick={() => conectar.mutate()} disabled={conectar.isPending}>Conectar agenda</Button>}
        </span>
      </div>
      <p className="mt-2 text-xs text-ink-muted">
        {conectado
          ? "A Mora não oferece horários em que este corretor já tem compromisso, e cada visita marcada vira um evento na agenda dele — com convite para o cliente."
          : "Conectando, a Mora passa a consultar a disponibilidade real antes de oferecer horários e cria o evento da visita automaticamente."}
      </p>
      {conectar.isSuccess && !conectado && (
        <p className="mt-2 text-xs text-ink-muted">Autorize na janela que abriu e recarregue esta tela.</p>
      )}
      {conectar.isError && (
        <p className="mt-2 text-xs text-bad-strong">{(conectar.error as Error).message}</p>
      )}

      <ConfirmDialog aberto={desconectando} titulo="Desconectar a agenda?"
        descricao="A Mora volta a usar a grade interna para este corretor. Os eventos já criados no Google continuam lá."
        confirmar="Desconectar" perigo={false} carregando={desconectar.isPending}
        onCancelar={() => setDesconectando(false)} onConfirmar={() => desconectar.mutate()} />
    </div>
  );
}
