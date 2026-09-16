"""Tradução Telegram Bot API ⇄ contratos neutros. Zero lógica de negócio (ADR-0003).

Por que Telegram além do WhatsApp: criar uma conta de desenvolvedor Meta para o WhatsApp Cloud API
exige verificação de negócio, que trava a demo. Um bot do Telegram é criado na hora, sem aprovação,
falando com @BotFather — e como usamos *long polling* (`getUpdates`), nem precisa de URL pública
nem do túnel cloudflared que o WhatsApp exigia. Ver ADR-0007.
"""
import re
from collections.abc import Callable
from sdr_shared.messaging import MensagemNormalizada, RespostaAgente, Canal, TipoMensagem

IMOVEL_RE = re.compile(r"IMOVEL-([A-Za-z0-9\-]+)")
CALLBACK_MAX = 64          # limite do Telegram para callback_data


def _opcao(o: str) -> tuple[str, str]:
    """`id|rótulo` → (id, rótulo); `rótulo` → (rótulo, rótulo). Mesmo contrato do site e do WhatsApp."""
    return tuple(o.split("|", 1)) if "|" in o else (o, o)


def parse_inbound(update: dict, resolver_lead: Callable[[str, str | None], str]) -> list[MensagemNormalizada]:
    """Um `update` do Telegram vira 0 ou 1 mensagem — a API já entrega um por vez (polling ou webhook)."""
    m = update.get("message")
    cq = update.get("callback_query")
    if not m and not cq:
        return []                                  # edited_message, my_chat_member etc. — ignorado

    if cq:
        chat_id = str(cq["message"]["chat"]["id"])
        de = cq.get("from", {})
        nome = de.get("first_name") or de.get("username")
        lead_id = resolver_lead(chat_id, nome)
        return [MensagemNormalizada(lead_id=lead_id, canal=Canal.TELEGRAM, identificador_canal=chat_id,
                                    tipo=TipoMensagem.BOTAO, conteudo=cq["data"], meta={"nome": nome, "telegram_chat_id": chat_id})]

    chat_id = str(m["chat"]["id"])
    de = m.get("from", {})
    nome = de.get("first_name") or de.get("username")
    lead_id = resolver_lead(chat_id, nome)
    meta = {"nome": nome, "telegram_chat_id": chat_id}

    if "text" in m:
        texto = m["text"]
        if texto.startswith("/start"):             # deep link t.me/<bot>?start=IMOVEL-SP-0001
            partes = texto.split(maxsplit=1)
            texto = partes[1] if len(partes) > 1 else "Olá!"
        if im := IMOVEL_RE.search(texto):
            meta["imovel_origem"] = im.group(1)
        tipo = TipoMensagem.TEXTO
        conteudo = texto
    elif "voice" in m:
        tipo, conteudo, meta["telegram_file_id"] = TipoMensagem.AUDIO, "", m["voice"]["file_id"]
    elif "location" in m:
        tipo = TipoMensagem.LOCALIZACAO
        meta |= {"lat": m["location"]["latitude"], "lng": m["location"]["longitude"]}
        conteudo = "(cliente enviou a localização)"
    else:
        return []                                  # sticker, foto solta etc. — fora do escopo da POC

    return [MensagemNormalizada(lead_id=lead_id, canal=Canal.TELEGRAM, identificador_canal=chat_id,
                                tipo=tipo, conteudo=conteudo, meta=meta)]


def render(chat_id: str, r: RespostaAgente) -> list[dict]:
    """RespostaAgente → chamadas da Bot API: um `sendPhoto` por card de imóvel, depois o texto
    (com teclado inline se houver opções)."""
    msgs = []
    for card in r.imoveis:
        legenda = f"{card.titulo}\nR$ {card.preco:,.0f}".replace(",", ".") + f"\n{card.motivo}"
        if card.foto:
            msgs.append({"_method": "sendPhoto", "chat_id": chat_id, "photo": card.foto, "caption": legenda[:1024]})
        else:
            msgs.append({"_method": "sendMessage", "chat_id": chat_id, "text": legenda})

    corpo = {"_method": "sendMessage", "chat_id": chat_id, "text": r.texto}
    opcoes = [_opcao(o) for o in r.opcoes]
    if opcoes:
        corpo["reply_markup"] = {"inline_keyboard": [[{"text": t[:64], "callback_data": i[:CALLBACK_MAX]}] for i, t in opcoes]}
    msgs.append(corpo)
    return msgs
