export function MensagemBolha({ de, texto }: { de: "lead" | "Mora"; texto: string }) {
  const lead = de === "lead";
  return (
    <div className={`flex ${lead ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${lead ? "rounded-br-sm bg-brand text-white" : "rounded-bl-sm bg-white shadow-sm ring-1 ring-slate-200"}`}>{texto}</div>
    </div>
  );
}
