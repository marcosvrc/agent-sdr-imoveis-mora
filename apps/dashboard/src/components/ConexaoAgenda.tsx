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
  // Endereço do consentimento, guardado só quando o navegador barrou a janela: vira link na tela.
  const [linkManual, setLinkManual] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: ["calendario"], queryFn: api.statusCalendario });
  const conectado = !!data?.corretores?.[corretorId];

  // O Google exige que o consentimento seja dado numa janela do próprio corretor. A janela abre
  // NO CLIQUE, vazia, e recebe o endereço quando a API responde: o Safari (e o Firefox, com
  // bloqueio estrito) só permite `window.open` no gesto do usuário — depois de um `await` ele
  // devolvia null em silêncio e nada acontecia. Sem `noopener` na abertura (com ele o retorno é
  // sempre null e não daria para pôr o endereço depois); o vínculo é cortado à mão logo abaixo.
  const conectar = useMutation({
    mutationFn: async (janela: Window | null) => ({ janela, ...(await api.conectarCalendario(corretorId)) }),
    onSuccess: ({ janela, url }) => {
      if (janela && !janela.closed) {
        janela.opener = null;
        janela.location.href = url;
        setLinkManual(null);
      } else {
        setLinkManual(url);                       // bloqueada: o corretor abre pelo link
      }
    },
    onError: (_e, janela) => { janela?.close(); },
  });
  const iniciarConexao = () => conectar.mutate(window.open("about:blank", "_blank", "width=520,height=640"));
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
                onClick={iniciarConexao} disabled={conectar.isPending}>Conectar agenda</Button>}
        </span>
      </div>
      <p className="mt-2 text-xs text-ink-muted">
        {conectado
          ? "A Mora não oferece horários em que este corretor já tem compromisso, e cada visita marcada vira um evento na agenda dele — com convite para o cliente."
          : "Conectando, a Mora passa a consultar a disponibilidade real antes de oferecer horários e cria o evento da visita automaticamente."}
      </p>
      {conectar.isSuccess && !conectado && !linkManual && (
        <p className="mt-2 text-xs text-ink-muted">Autorize na janela que abriu e recarregue esta tela.</p>
      )}
      {linkManual && !conectado && (
        <p className="mt-2 text-xs text-warn-strong" role="status">
          O navegador bloqueou a janela de autorização.{" "}
          <a href={linkManual} target="_blank" rel="noopener noreferrer" className="font-medium underline">Abrir a autorização do Google</a>
          {" "}e, depois de autorizar, recarregue esta tela.
        </p>
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
