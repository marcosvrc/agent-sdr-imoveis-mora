import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Corretor } from "../lib/api";
import { Button, Field, Modal, Select, cx } from "./ui";
import { Ic } from "./Icons";

/** Desligar um corretor é uma decisão sobre a CARTEIRA dele, não sobre a linha no cadastro.
 *
 *  A tela antiga perguntava só "tem certeza?" e mandava um DELETE — que apagava o corretor e
 *  deixava os leads apontando para um id inexistente: em handoff, atribuídos a ninguém, fora da
 *  lista de todo mundo. Aqui a pergunta certa é feita antes: para onde vão os leads abertos e as
 *  visitas futuras. O cadastro é desativado, nunca apagado, para o histórico continuar de pé.
 */
export function DesativarCorretor({ corretor, ativos, onFechar }:
  { corretor: Corretor; ativos: Corretor[]; onFechar: () => void }) {
  const qc = useQueryClient();
  const [destino, setDestino] = useState("equipe");
  const [erro, setErro] = useState("");

  const { data: carteira, isLoading } = useQuery({
    queryKey: ["carteira", corretor.id],
    queryFn: () => api.carteiraCorretor(corretor.id),
  });

  const desativar = useMutation({
    mutationFn: () => api.desativarCorretor(corretor.id, destino),
    onSuccess: () => { qc.invalidateQueries(); onFechar(); },
    onError: (e: Error) => setErro(e.message),
  });

  const apagar = useMutation({
    mutationFn: () => api.desativarCorretor(corretor.id, "equipe", true),
    onSuccess: () => { qc.invalidateQueries(); onFechar(); },
    onError: (e: Error) => setErro(e.message),
  });

  const outros = ativos.filter((c) => c.id !== corretor.id);
  const temCarteira = !!carteira && (carteira.leads > 0 || carteira.visitas > 0);

  return (
    <Modal aberto titulo={`Desativar ${corretor.nome}`} onFechar={onFechar} largura="max-w-lg"
      rodape={
        <div className="flex w-full flex-wrap items-center gap-2">
          {/* Apagar de vez só faz sentido para cadastro criado por engano — e a API recusa se
              houver carteira, então o botão nem aparece nesse caso. */}
          {carteira && !temCarteira && (
            <Button variante="fantasma" tamanho="sm" onClick={() => apagar.mutate()} disabled={apagar.isPending}>
              Apagar cadastro
            </Button>
          )}
          <span className="ml-auto flex gap-2">
            <Button variante="secundario" onClick={onFechar}>Cancelar</Button>
            <Button variante="perigo" onClick={() => desativar.mutate()}
                    disabled={isLoading || desativar.isPending}>
              {desativar.isPending ? "Desativando…" : "Desativar corretor"}
            </Button>
          </span>
        </div>
      }>
      <div className="space-y-4 text-sm">
        {isLoading && <p className="text-ink-muted">Conferindo a carteira…</p>}

        {carteira && (temCarteira ? (
          <div className="rounded-lg border border-warn-line bg-warn-soft p-3 text-warn-strong">
            <p className="flex items-center gap-2 font-medium"><Ic.info size={15} />Este corretor tem trabalho em aberto</p>
            <ul className="mt-1.5 list-inside list-disc">
              {carteira.leads > 0 && <li>{carteira.leads} {carteira.leads === 1 ? "lead em atendimento" : "leads em atendimento"}</li>}
              {carteira.visitas > 0 && <li>{carteira.visitas} {carteira.visitas === 1 ? "visita futura" : "visitas futuras"}</li>}
            </ul>
            <p className="mt-1.5">Escolha quem assume — quem receber é avisado no sino.</p>
          </div>
        ) : (
          <p className="text-ink-muted">Sem leads abertos nem visitas futuras. Nada a transferir.</p>
        ))}

        <Field label="Para onde vai a carteira">
          <Select value={destino} onChange={(e) => setDestino(e.target.value)}>
            <option value="equipe">Fila da equipe (sem dono, qualquer corretor assume)</option>
            <option value="auto">Distribuir automaticamente (por região e menor carga)</option>
            {outros.length > 0 && <option disabled>──────────</option>}
            {outros.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
          </Select>
        </Field>

        <p className="text-xs text-ink-muted">
          O cadastro fica no sistema como <strong>inativo</strong>: ele para de receber novos leads e
          visitas, e o histórico de quem atendeu quem continua íntegro. Para reativar depois, basta
          ligar o interruptor na lista.
        </p>

        {erro && <p role="alert" className={cx("rounded-md bg-bad-soft p-2 text-bad-strong")}>{erro}</p>}
      </div>
    </Modal>
  );
}
