"""Entrada do Telegram, por long polling (`getUpdates`).

Havia aqui também um `handler()` de webhook, para a Bot API chamar uma URL pública. Saiu com a AWS:
sem função hospedada não há URL pública, e o long polling não precisa de uma — basta um
`SDR_TELEGRAM_BOT_TOKEN` no `.env` (ver ADR-0007), o que é justamente o que torna a entrega
reproduzível na máquina local.

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


# Modo de teste, o equivalente do botão "Nova conversa" do site: o chat do Telegram passa a apontar
# para um lead NOVO, e a conversa recomeça do zero (cartão, memória do grafo, follow-ups). O lead
# antigo continua no painel com o histórico — nada é apagado. Só no perfil local: em produção, um
# cliente que digitasse /novo jogaria fora o próprio atendimento sem o corretor saber.
NOVA_CONVERSA = frozenset({"/novo", "/nova", "/reset"})


def _pede_nova_conversa(u: dict) -> bool:
    texto = ((u.get("message") or {}).get("text") or "").strip().lower()
    comando = texto.split("@", 1)[0].split(maxsplit=1)[0] if texto else ""     # "/novo@mora_bot" em grupo
    return comando in NOVA_CONVERSA and get_settings().profile == "local"


def _nova_conversa(u: dict) -> dict:
    """Desvincula o chat do lead atual e devolve o update como um "Olá!" do lead novo.

    O id ganha o instante: `tg_<chat>` já existe, e reaproveitá-lo traria de volta o mesmo lead
    (e o mesmo `thread_id` do grafo, que é o lead_id) — justamente o que se quer zerar."""
    m = u["message"]
    chat_id = str(m["chat"]["id"])
    de = m.get("from", {})
    lead = LeadRepository().upsert(Lead(id=f"tg_{chat_id}_{int(time.time())}",
                                        nome=de.get("first_name") or de.get("username")))
    CanalRepository().vincular(lead.id, "telegram", chat_id)       # ON CONFLICT: o chat muda de dono
    log.info("chat %s: nova conversa de teste no lead %s", chat_id, lead.id)
    return {**u, "message": {**m, "text": "Olá!"}}


def processar_lote(updates: list[dict], offset: int | None,
                   ao_publicar=None) -> tuple[int | None, bool]:
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
            if _pede_nova_conversa(u):
                u = _nova_conversa(u)
            msgs = parse_inbound(u, resolver_lead=_resolver_lead)
        except Exception:
            log.exception("update %s do Telegram não pôde ser traduzido — pulando", u.get("update_id"))
            offset = u["update_id"] + 1
            continue
        try:
            for msg in msgs:
                get_broker().publish("inbound", msg.model_dump_json(), key=msg.lead_id)   # ordem por lead garantida
                if ao_publicar is not None:
                    ao_publicar(msg)
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
        anunciar_bot(http, base)
        while True:
            try:
                params = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
                if offset is not None:
                    params["offset"] = offset
                r = http.get(f"{base}/getUpdates", params=params)
                if r.is_error:
                    # Sem raise_for_status: o HTTPStatusError do httpx traz a URL, e a URL traz o token.
                    log.warning("getUpdates recusado (%s): %s — tentando de novo em 5s",
                                r.status_code, _motivo(r))
                    time.sleep(5)
                    continue
                offset, completo = processar_lote(r.json().get("result", []), offset,
                                                  ao_publicar=lambda msg: _digitando(base, msg))
                if not completo:
                    time.sleep(5)              # broker fora: espera antes de pedir o mesmo update de novo
            except Exception as e:
                log.warning("getUpdates falhou (%s) — tentando de novo em 5s", type(e).__name__)
                time.sleep(5)


def _digitando(base: str, msg) -> None:
    """"digitando…" enquanto o turno roda — só quando a Mora vai mesmo responder. Em handoff quem
    responde é o corretor, sem prazo: o indicador prometeria uma resposta que não vem."""
    try:
        from .digitando import iniciar
        lead = LeadRepository().get(msg.lead_id)
        if lead is not None and str(getattr(lead.estagio, "value", lead.estagio)) == "handoff":
            return
        iniciar(base, msg.identificador_canal, msg.lead_id)
    except Exception:
        log.debug("não consegui ligar o indicador de digitação", exc_info=True)


def _motivo(r: httpx.Response) -> str:
    try:
        return r.json().get("description") or "sem descrição"
    except ValueError:
        return "sem descrição"


def anunciar_bot(http: httpx.Client, base: str) -> None:
    """Uma linha no log dizendo QUAL bot está sendo ouvido — ou por que o token não serve.

    O worker não dizia nada ao subir: com token certo ou errado, `docker compose logs telegram-in`
    vinha vazio, e não havia como saber se ele estava vivo. 409 no getUpdates (outra instância do
    mesmo bot lendo as mensagens) também ganha explicação."""
    try:
        r = http.get(f"{base}/getMe")
    except Exception as e:
        log.warning("não consegui falar com a API do Telegram (%s)", type(e).__name__)
        return
    if r.status_code == 401:
        log.error("SDR_TELEGRAM_BOT_TOKEN recusado pelo Telegram (401): token errado ou revogado. "
                  "Gere outro no @BotFather e recrie: docker compose up -d telegram-in telegram-out")
    elif r.is_error:
        log.warning("getMe recusado (%s): %s", r.status_code, _motivo(r))
    else:
        bot = (r.json().get("result") or {}).get("username", "?")
        log.info("ouvindo o bot @%s por long polling. Se aparecer 409 no getUpdates, outra instância "
                 "deste bot está lendo as mensagens — só pode haver uma.", bot)
