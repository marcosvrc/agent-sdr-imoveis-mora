"""Consome outbound-telegram e envia pela Bot API. Sem janela de 24h nem template aprovado — a
única regra do Telegram é o cliente ter dado /start no bot antes (senão a API recusa o envio)."""
import json
import logging
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from sdr_shared.config import get_settings
from sdr_shared.messaging import RespostaAgente
from .adapter import render

log = logging.getLogger("canal_telegram.outbound")

# Foto servida pela própria API: os mesmos padrões que `api/main.py` aceita em /fotos e /acervo.
_FOTO_PAINEL = re.compile(r"^/fotos/([A-Za-z0-9_-]+)/([a-f0-9]{32}\.(?:jpg|png|webp))$")
_FOTO_ACERVO = re.compile(r"^/acervo/([a-z-]{3,24})/([a-z-]{3,24}-\d{2}\.jpg)$")


class TelegramRecusou(Exception):
    """A Bot API recusou a chamada. A mensagem traz o método e o motivo que o Telegram deu — nunca a
    URL: ela carrega o token do bot, e o `HTTPStatusError` do httpx a punha inteira no log."""

    def __init__(self, metodo: str, resposta: httpx.Response):
        try:
            motivo = resposta.json().get("description") or ""
        except ValueError:
            motivo = ""
        self.status = resposta.status_code
        super().__init__(f"Telegram recusou {metodo} ({resposta.status_code}): {motivo or 'sem descrição'}")


def _chamar(http: httpx.Client, base: str, metodo: str, *, json_: dict | None = None,
            data: dict | None = None, files: dict | None = None) -> None:
    r = http.post(f"{base}/{metodo}", json=json_, data=data, files=files)
    if r.is_error:
        raise TelegramRecusou(metodo, r)


def foto_local(url: str) -> Path | None:
    """O arquivo em disco de uma foto que a própria API serve, ou None.

    O Telegram baixa a foto pela URL — e `http://localhost:8000/acervo/...` não existe para ele: o
    sendPhoto voltava 400 e, como as fotos vão antes do texto, o cliente não recebia nada. Quando a
    foto é nossa, ela vai como arquivo (upload); o worker tem a pasta `data/` montada.
    """
    s = get_settings()
    partes = urlsplit(url)
    if f"{partes.scheme}://{partes.netloc}" != s.public_api_url.rstrip("/"):
        return None
    if m := _FOTO_ACERVO.match(partes.path):
        arquivo = Path(s.fotos_acervo_dir) / m[1] / m[2]
    elif m := _FOTO_PAINEL.match(partes.path):
        arquivo = Path(s.fotos_dir) / m[1] / m[2]
    else:
        return None
    return arquivo if arquivo.is_file() else None


def _enviar_foto(http: httpx.Client, base: str, p: dict) -> None:
    """sendPhoto que nunca derruba a resposta: foto nossa vai como arquivo; se o Telegram recusar
    mesmo assim, o card segue como texto — melhor sem foto do que sem resposta."""
    try:
        if arquivo := foto_local(p["photo"]):
            with arquivo.open("rb") as f:
                _chamar(http, base, "sendPhoto", data={"chat_id": p["chat_id"], "caption": p["caption"]},
                        files={"photo": (arquivo.name, f)})
        else:
            _chamar(http, base, "sendPhoto", json_=p)
    except TelegramRecusou as e:
        log.warning("%s — mandando o card como texto", e)
        _chamar(http, base, "sendMessage", json_={"chat_id": p["chat_id"], "text": p["caption"]})


def enviar(body_json: str) -> None:
    s = get_settings()
    base = f"https://api.telegram.org/bot{s.telegram_bot_token}"
    body = json.loads(body_json)
    r = RespostaAgente.model_validate(body["resposta"])
    with httpx.Client(timeout=20) as http:
        for p in render(body["identificador"], r):
            metodo = p.pop("_method")
            if metodo == "sendPhoto":
                _enviar_foto(http, base, p)
            else:
                _chamar(http, base, metodo, json_=p)


def local_worker():
    from sdr_shared.db import iniciar_batimento
    from sdr_shared.log import configurar as configurar_log
    from sdr_shared.ports import get_broker
    configurar_log("telegram-out")         # log estruturado e as checagens de subida, como os outros
    iniciar_batimento("telegram-out")
    get_broker().consume("outbound-telegram", enviar)
