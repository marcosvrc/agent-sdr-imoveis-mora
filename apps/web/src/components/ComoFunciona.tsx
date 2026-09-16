import { Ic } from "./Icones";

const PASSOS = [
  { i: <Ic.chat size={20} />, t: "Conte o que você procura", d: "Bairro, quantos quartos, se é para morar ou investir — do jeito que você fala, sem formulário." },
  { i: <Ic.casa size={20} />, t: "Receba sugestões na hora", d: "A Mora cruza o que você disse com o catálogo e mostra os imóveis que combinam, com o motivo de cada um." },
  { i: <Ic.calendario size={20} />, t: "Agende a visita sem espera", d: "Escolha um horário livre na própria conversa; a confirmação e o convite de calendário chegam na hora." },
];

export function ComoFunciona() {
  return (
    <section aria-labelledby="como-funciona" className="border-y border-line bg-surface">
      <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6">
        <h2 id="como-funciona" className="text-center font-display text-2xl font-semibold text-brand sm:text-3xl">Como funciona</h2>
        <p className="mx-auto mt-2 max-w-md text-center text-sm text-ink-muted">
          Sem fila e sem formulário: a Mora conversa com você como um corretor faria — e chama um humano quando você pedir.
        </p>
        <ol className="mt-10 grid gap-8 sm:grid-cols-3">
          {PASSOS.map((p, i) => (
            <li key={p.t} className="flex gap-4">
              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-brand-suave text-brand-accentDark" aria-hidden>{p.i}</span>
              <span>
                <span className="block text-xs font-semibold uppercase tracking-wide text-ink-soft">Passo {i + 1}</span>
                <h3 className="mt-0.5 font-semibold text-ink">{p.t}</h3>
                <p className="mt-1 text-sm text-ink-muted">{p.d}</p>
              </span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
