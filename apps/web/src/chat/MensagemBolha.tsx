import { MoraAvatar } from "../components/MoraAvatar";

/** Uma mensagem. O retrato da Mora aparece só na ÚLTIMA bolha de uma sequência dela — repetido em
 *  cada uma, vira ruído; o espaço fica reservado para as bolhas continuarem alinhadas. */
export function MensagemBolha({ de, texto, avatar = true, hora, aviso, children }: {
  de: "lead" | "Mora"; texto: string; avatar?: boolean; hora?: string; aviso?: boolean; children?: React.ReactNode;
}) {
  const lead = de === "lead";
  return (
    <div className={`flex items-end gap-2 ${lead ? "justify-end" : "justify-start"}`}>
      {!lead && (avatar ? <span aria-hidden><MoraAvatar tamanho={24} /></span> : <span className="w-6 shrink-0" aria-hidden />)}
      <div className={`flex max-w-[min(85%,40rem)] flex-col ${lead ? "items-end" : "items-start"}`}>
        {/* pre-wrap + leading-relaxed: a Mora separa contexto, lista e pergunta em linhas próprias */}
        <div className={`whitespace-pre-wrap break-words rounded-2xl px-3 py-2 text-sm leading-relaxed ${
          lead ? "rounded-br-sm bg-brand text-white"
            : aviso ? "rounded-bl-sm bg-amber-50 text-amber-900 ring-1 ring-amber-200"
              : "rounded-bl-sm bg-white shadow-sm ring-1 ring-slate-200"}`}>
          {!lead && <span className="sr-only">Mora: </span>}
          {texto}
        </div>
        {children}
        {hora && <span className="mt-0.5 px-1 text-[11px] text-ink-muted">{hora}</span>}
      </div>
    </div>
  );
}

/** "Digitando": três pontos que se movem, com o texto para quem usa leitor de tela. Quem pediu
 *  menos movimento vê os pontos parados. */
export function Digitando() {
  return (
    <div className="flex items-end gap-2">
      <span aria-hidden><MoraAvatar tamanho={24} /></span>
      <div className="flex items-center gap-1 rounded-2xl rounded-bl-sm bg-white px-3 py-3 shadow-sm ring-1 ring-slate-200">
        <span className="sr-only">A Mora está escrevendo</span>
        {[0, 1, 2].map((i) => (
          <span key={i} aria-hidden className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400 motion-reduce:animate-none"
                style={{ animationDelay: `${i * 160}ms` }} />
        ))}
      </div>
    </div>
  );
}
