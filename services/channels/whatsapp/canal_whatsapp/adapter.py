"""Tradução Meta Cloud API ⇄ contratos neutros. Zero lógica de negócio."""
import re
from collections.abc import Callable
from sdr_shared.messaging import MensagemNormalizada, RespostaAgente, Canal, TipoMensagem

IMOVEL_RE = re.compile(r"IMOVEL-([A-Za-z0-9\-]+)")


def _opcao(o: str) -> tuple[str, str]:
    """`id|rótulo` → (id, rótulo); `rótulo` → (rótulo, rótulo)."""
    return tuple(o.split("|", 1)) if "|" in o else (o, o)


def parse_inbound(payload: dict, resolver_lead: Callable[[str, str | None], str]) -> list[MensagemNormalizada]:
    out = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            v = change.get("value", {})
            nomes = {c["wa_id"]: c.get("profile", {}).get("name") for c in v.get("contacts", [])}
            for m in v.get("messages", []):
                tel = m["from"]
                lead_id = resolver_lead(tel, nomes.get(tel))
                tipo, conteudo, meta = TipoMensagem.TEXTO, "", {"nome": nomes.get(tel), "telefone": tel, "wa_message_id": m.get("id")}
                match m["type"]:
                    case "text":
                        conteudo = m["text"]["body"]
                        if im := IMOVEL_RE.search(conteudo):          # veio do botão do site
                            meta["imovel_origem"] = im.group(1)
                    case "interactive":
                        tipo = TipoMensagem.BOTAO
                        i = m["interactive"]
                        conteudo = (i.get("button_reply") or i.get("list_reply"))["id"]
                    case "audio":
                        tipo, meta["media_id"] = TipoMensagem.AUDIO, m["audio"]["id"]
                    case "location":
                        tipo = TipoMensagem.LOCALIZACAO
                        meta |= {"lat": m["location"]["latitude"], "lng": m["location"]["longitude"]}
                        conteudo = "(cliente enviou a localização)"
                    case _:
                        continue
                out.append(MensagemNormalizada(lead_id=lead_id, canal=Canal.WHATSAPP, identificador_canal=tel,
                                               tipo=tipo, conteudo=conteudo, meta=meta))
    return out


def render(telefone: str, r: RespostaAgente) -> list[dict]:
    """RespostaAgente → mensagens da Cloud API: cards de imóveis (imagem+legenda), depois texto com botões/lista."""
    base = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": telefone}
    msgs = []
    for card in r.imoveis:
        legenda = f"{card.titulo}\nR$ {card.preco:,.0f}".replace(",", ".") + f"\n{card.motivo}"
        if card.foto:
            msgs.append(base | {"type": "image", "image": {"link": card.foto, "caption": legenda[:1024]}})
        else:
            msgs.append(base | {"type": "text", "text": {"body": legenda}})
    opcoes = [_opcao(o) for o in r.opcoes]
    if not opcoes:
        msgs.append(base | {"type": "text", "text": {"body": r.texto}})
    elif len(opcoes) <= 3:
        msgs.append(base | {"type": "interactive", "interactive": {
            "type": "button", "body": {"text": r.texto},
            "action": {"buttons": [{"type": "reply", "reply": {"id": i[:256], "title": t[:20]}} for i, t in opcoes]}}})
    else:
        msgs.append(base | {"type": "interactive", "interactive": {
            "type": "list", "body": {"text": r.texto},
            "action": {"button": "Escolher", "sections": [{"title": "Opções",
                       "rows": [{"id": i[:200], "title": t[:24]} for i, t in opcoes[:10]]}]}}})
    return msgs
