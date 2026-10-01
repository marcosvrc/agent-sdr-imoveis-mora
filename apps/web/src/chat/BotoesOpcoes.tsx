// opcoes: "rótulo" ou "id|rótulo" (ex.: "slot:2026-09-10T13:00:00|qui 10/09 às 10h") — mesmo contrato do Telegram.
// Horários (id slot:) são agrupados por dia para caber na tela do celular.
export function BotoesOpcoes({ opcoes, onEscolher }: { opcoes: string[]; onEscolher: (id: string, rotulo: string) => void }) {
  const itens = opcoes.map((o) => { const [id, rotulo] = o.includes("|") ? o.split("|", 2) : [o, o]; return { id, rotulo }; });
  const horarios = itens.every((i) => i.id.startsWith("slot:"));
  if (!horarios) {
    return (
      <div className="flex flex-wrap gap-2 border-t bg-white px-3 py-2">
        {itens.map(({ id, rotulo }) => <Botao key={id} onClick={() => onEscolher(id, rotulo)}>{rotulo}</Botao>)}
      </div>
    );
  }
  // "ter 15/09 às 14h" → dia "ter 15/09", hora "14h"
  const porDia = new Map<string, { id: string; rotulo: string; hora: string }[]>();
  for (const i of itens) {
    const [dia, hora] = i.rotulo.split(" às ");
    porDia.set(dia, [...(porDia.get(dia) ?? []), { ...i, hora: hora ?? i.rotulo }]);
  }
  return (
    <div className="space-y-1.5 border-t bg-white px-3 py-2">
      {[...porDia.entries()].map(([dia, hs]) => (
        <div key={dia} className="flex items-center gap-2">
          <span className="w-20 shrink-0 text-sm font-medium capitalize text-slate-600">{dia}</span>
          <div className="flex flex-wrap gap-1.5">
            {hs.map((h) => <Botao key={h.id} onClick={() => onEscolher(h.id, h.rotulo)}>{h.hora}</Botao>)}
          </div>
        </div>
      ))}
    </div>
  );
}

// Alvo de toque com pelo menos 36 px de altura: no celular, os botões de 24 px eram fáceis de errar
// — e errar aqui é escolher o horário errado de uma visita.
function Botao({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return <button type="button" onClick={onClick} className="min-h-9 rounded-full border border-brand-accent px-3.5 py-1.5 text-sm font-medium text-brand-accent transition hover:bg-blue-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-accent">{children}</button>;
}
