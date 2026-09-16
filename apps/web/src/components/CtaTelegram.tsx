import { track } from "../lib/tracking";
import { TELEGRAM_USUARIO } from "../lib/imobiliaria";
import { BotaoLink } from "../lib/ui";
import { Ic } from "./Icones";

// Porta de entrada com contexto: o bot lê "/start IMOVEL-<id>" e a Mora já abre falando daquele
// imóvel, em vez de o cliente ter que repetir o que já deixou claro ao clicar aqui.
export function CtaTelegram({ imovelId, largo, tamanho = "md" }: { imovelId?: string; largo?: boolean; tamanho?: "sm" | "md" | "lg" }) {
  const start = imovelId ? `?start=IMOVEL-${imovelId}` : "";
  return (
    <BotaoLink externo para={`https://t.me/${TELEGRAM_USUARIO}${start}`} variante="secundario"
               tamanho={tamanho} largo={largo} icone={<Ic.telegram size={17} />}
               onClick={() => track("clicked_telegram", { imovel_id: imovelId })}>
      Continuar no Telegram
    </BotaoLink>
  );
}
