import { useState } from "react";
import { Botao } from "../lib/ui";
import { Ic } from "./Icones";

/** Compartilhar a ficha. Usa a folha nativa do sistema quando existe (é o caminho esperado no
 *  celular, onde a maior parte do compartilhamento acontece) e cai para copiar o link no desktop.
 *
 *  O estado de sucesso é anunciado por aria-live: sem isso, quem não vê a tela não recebe confirmação
 *  nenhuma de que o link foi copiado. */
export function Compartilhar({ titulo, texto }: { titulo: string; texto?: string }) {
  const [copiado, setCopiado] = useState(false);

  const compartilhar = async () => {
    const url = window.location.href;
    if (navigator.share) {
      try { await navigator.share({ title: titulo, text: texto, url }); return; }
      catch { /* usuário cancelou: não é erro, e não vale cair para o clipboard por cima disso */ return; }
    }
    try {
      await navigator.clipboard.writeText(url);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2500);
    } catch { /* clipboard bloqueado: o link continua na barra de endereços */ }
  };

  return (
    <>
      <Botao variante="secundario" tamanho="sm" onClick={compartilhar}
             icone={copiado ? <Ic.check size={16} /> : <Ic.compartilhar size={16} />}>
        {copiado ? "Link copiado" : "Compartilhar"}
      </Botao>
      <span aria-live="polite" className="sr-only">{copiado ? "Link copiado para a área de transferência" : ""}</span>
    </>
  );
}
