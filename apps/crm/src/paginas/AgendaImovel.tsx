import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { Botao, CabecalhoPagina, Campo, Card, Carregando, Erro, Etiqueta, Vazio, cx,
         entradaCls } from "../componentes/ui";
import { api } from "../lib/api";
import { dataHora } from "../lib/formato";

/** Agenda de um imóvel: abrir horários para visita.
 *
 *  É a última peça que fazia o `make seed` ser obrigatório — sem horário aberto, a Mora não tem o
 *  que oferecer e a visita nunca sai do papel, por mais qualificado que o cliente esteja.
 *
 *  Mostra os OCUPADOS junto com os livres (`only_free=false`). Uma agenda que só exibe o que está
 *  livre esconde justamente o que já foi combinado, e quem administra abre outro horário em cima.
 */
export function AgendaImovel() {
  const { id = "" } = useParams();
  const qc = useQueryClient();

  const corretores = useQuery({ queryKey: ["corretores"], queryFn: api.corretores });
  const slots = useQuery({
    queryKey: ["horarios", id],
    queryFn: () => api.horarios({ property_id: id, only_free: "false", limit: "100" }),
  });

  const [corretor, setCorretor] = useState("");
  const [dia, setDia] = useState("");
  const [hora, setHora] = useState("");
  const [duracao, setDuracao] = useState("60");

  // O navegador entrega "2026-09-25" e "14:00" no fuso de quem digita; `new Date(...)` monta o
  // instante local e `toISOString` o converte para UTC, que é o que o banco guarda. Montar a
  // string ISO à mão aqui seria gravar 14h UTC — 11h em São Paulo, e ninguém entenderia por quê.
  const inicio = dia && hora ? new Date(`${dia}T${hora}`) : null;
  const fim = inicio ? new Date(inicio.getTime() + Number(duracao) * 60_000) : null;
  const noPassado = !!inicio && inicio.getTime() <= Date.now();
  const pode = !!corretor && !!inicio && !noPassado;

  const abrir = useMutation({
    mutationFn: () => api.abrirHorario({
      property_id: id, broker_id: corretor,
      starts_at: inicio!.toISOString(), ends_at: fim!.toISOString(),
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["horarios", id] }); setHora(""); },
  });

  const lista = slots.data?.items ?? [];
  const futuros = lista.filter((s) => new Date(s.starts_at) > new Date());

  return (
    <div>
      <CabecalhoPagina titulo="Agenda do imóvel" voltar={{ para: "/imoveis", r: "Imóveis" }}
        descricao="Horário aberto é o que a Mora oferece ao cliente. Confirmar a visita continua sendo ato humano." />

      <div className="grid items-start gap-4 lg:grid-cols-[1fr_1.3fr]">
        <Card titulo="Abrir horário">
          {corretores.isLoading ? <Carregando linhas={3} />
            : corretores.error ? <Erro erro={corretores.error} aoTentar={() => corretores.refetch()} />
            : (
              <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (pode) abrir.mutate(); }}>
                {abrir.error ? <Erro erro={abrir.error} /> : null}
                <Campo rotulo="Corretor" dica="Só quem está ativo e pode receber visita.">
                  <select className={entradaCls} value={corretor} required
                          onChange={(e) => setCorretor(e.target.value)}>
                    <option value="">Escolha…</option>
                    {(corretores.data?.items ?? []).map((c) => (
                      <option key={c.id} value={c.id}>{c.name}{c.role === "admin" ? " (admin)" : ""}</option>
                    ))}
                  </select>
                </Campo>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Campo rotulo="Dia">
                    <input className={entradaCls} type="date" value={dia} required
                           onChange={(e) => setDia(e.target.value)} />
                  </Campo>
                  <Campo rotulo="Hora">
                    <input className={entradaCls} type="time" value={hora} required step={900}
                           onChange={(e) => setHora(e.target.value)} />
                  </Campo>
                </div>
                <Campo rotulo="Duração">
                  <select className={entradaCls} value={duracao} onChange={(e) => setDuracao(e.target.value)}>
                    {["30", "45", "60", "90"].map((m) => <option key={m} value={m}>{m} minutos</option>)}
                  </select>
                </Campo>
                {/* Dito antes de o botão falhar: o servidor recusa horário no passado, e descobrir
                    isso depois de preencher o formulário inteiro é uma ida e volta desnecessária. */}
                {noPassado && <p className="text-xs text-ruim">Esse horário já passou.</p>}
                {inicio && fim && !noPassado && (
                  <p className="text-[11px] text-inkMuted">
                    Abre {dataHora(inicio.toISOString())} até {dataHora(fim.toISOString())}.
                  </p>
                )}
                <Botao variante="primario" type="submit" ocupado={abrir.isPending} disabled={!pode}
                       className="w-full justify-center">
                  Abrir horário
                </Botao>
              </form>
            )}
        </Card>

        <Card titulo="Horários deste imóvel"
              acoes={<span className="text-xs text-inkMuted">{futuros.length} no futuro</span>}>
          {slots.isLoading ? <Carregando linhas={4} />
            : slots.error ? <Erro erro={slots.error} aoTentar={() => slots.refetch()} />
            : lista.length === 0 ? (
              <Vazio titulo="Nenhum horário aberto"
                     descricao="Sem horário, a Mora não tem o que oferecer — e a visita não acontece, por mais pronto que o cliente esteja." />
            ) : (
              <ul className="divide-y divide-line text-sm">
                {lista.map((s) => {
                  const passou = new Date(s.starts_at) <= new Date();
                  return (
                    <li key={s.id} className={cx("flex flex-wrap items-center gap-x-3 gap-y-1 py-2",
                                                 passou && "opacity-50")}>
                      <span className="font-medium tabular-nums">{dataHora(s.starts_at)}</span>
                      <span className="text-inkMuted">{s.broker_name}</span>
                      <span className="ml-auto">
                        {s.taken ? <Etiqueta tom="info">visita confirmada</Etiqueta>
                         : passou ? <Etiqueta>passou</Etiqueta>
                         : <Etiqueta tom="bom">livre</Etiqueta>}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          <p className="mt-3 border-t border-line pt-3 text-[11px] text-inkMuted">
            Horário livre pode ter <b>solicitação</b> pendente: solicitar não reserva nada. Ele só sai
            de circulação quando alguém confirma — e quem confirma é uma pessoa, na tela de Visitas.
          </p>
        </Card>
      </div>
    </div>
  );
}
