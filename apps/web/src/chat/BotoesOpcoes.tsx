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
          <span className="w-20 shrink-0 text-xs font-medium capitalize text-slate-600">{dia}</span>
          <div className="flex flex-wrap gap-1.5">
            {hs.map((h) => <Botao key={h.id} onClick={() => onEscolher(h.id, h.rotulo)}>{h.hora}</Botao>)}
          </div>
        </div>
      ))}
    </div>
  );
}

function Botao({ children, onClick }: { children: React.ReactNode; onClick: () => void }) {
  return <button onClick={onClick} className="rounded-full border border-brand-accent px-3 py-1 text-xs font-medium text-brand-accent hover:bg-blue-50">{children}</button>;
}
