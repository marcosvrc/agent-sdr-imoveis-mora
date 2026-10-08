"""Entrada do Telegram, por long polling (`getUpdates`).

Havia aqui também um `handler()` de webhook, para a Bot API chamar uma URL pública. Saiu com a AWS:
sem função hospedada não há URL pública, e o long polling não precisa de uma — basta um
`SDR_TELEGRAM_BOT_TOKEN` no `.env` (ver ADR-0007), o que é justamente o que torna a entrega
reproduzível na máquina de quem avalia.

A tradução do update é do `adapter.parse_inbound`, compartilhada com o resto do canal."""
import logging
import time

import httpx
from sdr_shared.config import get_settings
from sdr_shared.db import LeadRepository, CanalRepository
from sdr_shared.models import Lead
from sdr_shared.ports import get_broker
from .adapter import parse_inbound

log = logging.getLogger("canal_telegram")


def _resolver_lead(chat_id: str, nome: str | None) -> str:
    """chat_id → lead existente ou novo (o mesmo lead pode ter vindo do site antes, por telefone)."""
    repo = LeadRepository()
    if lead := repo.get_por_canal("telegram", chat_id):
        return lead.id
    lead = repo.upsert(Lead(id=f"tg_{chat_id}", nome=nome))
    CanalRepository().vincular(lead.id, "telegram", chat_id)
    return lead.id


def processar_lote(updates: list[dict], offset: int | None) -> tuple[int | None, bool]:
    """Publica os updates em ordem e devolve (próximo offset, lote inteiro publicado?).

    O offset só anda DEPOIS que o update foi publicado. Antes ele andava primeiro: com o Redis fora,
    a publicação falhava, o próximo getUpdates confirmava o update ao Telegram e a mensagem do
    cliente sumia sem rastro. Agora o lote para no primeiro que não publicou; o próximo getUpdates
    pede de novo a partir dele (o Telegram guarda o que não foi confirmado por até 24h).

    Update que nem se traduz (formato inesperado) é pulado, como antes: repeti-lo para sempre
    travaria a fila inteira do bot por causa de uma mensagem. A falha de publicação é a do broker,
    passageira, e essa vale esperar.
    """
    for u in updates:
        try:
            msgs = parse_inbound(u, resolver_lead=_resolver_lead)
        except Exception:
            log.exception("update %s do Telegram não pôde ser traduzido — pulando", u.get("update_id"))
            offset = u["update_id"] + 1
            continue
        try:
            for msg in msgs:
                get_broker().publish("inbound", msg.model_dump_json(), key=msg.lead_id)   # ordem por lead garantida
        except Exception:
            log.exception("não consegui publicar o update %s — fica para o próximo getUpdates", u.get("update_id"))
            return offset, False
        offset = u["update_id"] + 1
    return offset, True


def local_worker():
    """Um processo dedicado (ver `telegram-in` no compose). Sem fila própria — o `offset` só avança
    depois que o update foi publicado no broker (`processar_lote`), então nada se perde se o broker
    cair, e nada é confirmado ao Telegram antes de estar na fila."""
    # Log estruturado e as checagens de subida (segredo de exemplo recusado) — como os outros
    # workers. Sem isto, o telegram-in subia aceitando mensagens que ninguém consumiria.
    from sdr_shared.log import configurar as configurar_log
    configurar_log("telegram-in")
    s = get_settings()
    if not s.telegram_bot_token:
        log.warning("SDR_TELEGRAM_BOT_TOKEN não configurado — worker do Telegram não vai subir")
        # Sem token este serviço não existe nesta instalação: o carimbo de uma execução antiga,
        # com token, deixaria o /health acusando "telegram-in parado" até o carimbo envelhecer.
        from sdr_shared.db import encerrar_batimento
        encerrar_batimento("telegram-in")
        return
    from sdr_shared.db import iniciar_batimento
    iniciar_batimento("telegram-in")
    base = f"https://api.telegram.org/bot{s.telegram_bot_token}"
    offset = None
    with httpx.Client(timeout=35) as http:
        while True:
            try:
                params = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
                if offset is not None:
                    params["offset"] = offset
                r = http.get(f"{base}/getUpdates", params=params)
                r.raise_for_status()
                offset, completo = processar_lote(r.json().get("result", []), offset)
                if not completo:
                    time.sleep(5)              # broker fora: espera antes de pedir o mesmo update de novo
            except Exception:
                log.exception("getUpdates falhou — tentando de novo em 5s")
                time.sleep(5)
