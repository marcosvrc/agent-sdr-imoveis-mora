"""Envio pela Bot API: foto local vai como arquivo, foto recusada vira texto, e o token nunca aparece
no erro."""
import json
import logging

import httpx
import pytest

import canal_telegram.outbound as outbound
from sdr_shared.config import get_settings
from sdr_shared.log import _Mascarar

TOKEN = "8387978656:AAG8" + "x" * 31          # formato de token de bot, valor inventado


@pytest.fixture
def telegram(monkeypatch, tmp_path):
    """Bot API falsa: registra cada chamada e responde com o que `respostas[metodo]` mandar."""
    chamadas, respostas = [], {}

    def tratar(req: httpx.Request) -> httpx.Response:
        metodo = req.url.path.rsplit("/", 1)[-1]
        tipo = req.headers.get("content-type", "")
        chamadas.append((metodo, "multipart" if tipo.startswith("multipart") else "json", req.content))
        status, desc = respostas.get(metodo, (200, None))
        return httpx.Response(status, json={"ok": status < 400, **({"description": desc} if desc else {})})

    real = httpx.Client
    monkeypatch.setattr(outbound.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(tratar)))
    monkeypatch.setattr(outbound, "_http", None)          # o cliente é do processo: cada teste, o seu
    s = get_settings()
    monkeypatch.setattr(s, "telegram_bot_token", TOKEN)
    monkeypatch.setattr(s, "public_api_url", "http://localhost:8000")
    monkeypatch.setattr(s, "fotos_acervo_dir", str(tmp_path))
    (tmp_path / "apartamento").mkdir()
    (tmp_path / "apartamento" / "apartamento-01.jpg").write_bytes(b"\xff\xd8jpeg")
    return chamadas, respostas


def _corpo(foto: str) -> str:
    card = {"id": "SP-1", "titulo": "Apartamento 1q · Pinheiros", "preco": 3800.0, "foto": foto, "motivo": "x"}
    return json.dumps({"identificador": "555", "resposta": {"lead_id": "tg_555", "texto": "Achei duas opções",
                                                            "imoveis": [card]}})


def test_foto_do_acervo_vai_como_arquivo_e_o_texto_chega(telegram):
    """O Telegram não alcança localhost: o sendPhoto com a URL voltava 400 e, como as fotos vão
    antes do texto, o cliente não recebia nada."""
    chamadas, _ = telegram
    outbound.enviar(_corpo("http://localhost:8000/acervo/apartamento/apartamento-01.jpg"))
    assert [(m, t) for m, t, _ in chamadas] == [("sendPhoto", "multipart"), ("sendMessage", "json")]
    assert b'name="reply_markup"' in chamadas[0][2] and b"imovel:SP-1" in chamadas[0][2], \
        "o botão Quero visitar vai junto também no upload"


def test_foto_recusada_vira_card_em_texto_e_a_resposta_segue(telegram, caplog):
    chamadas, respostas = telegram
    respostas["sendPhoto"] = (400, "Bad Request: wrong file identifier/HTTP URL specified")
    outbound.enviar(_corpo("https://exemplo.com.br/foto.jpg"))
    assert [m for m, _, _ in chamadas] == ["sendPhoto", "sendMessage", "sendMessage"]
    assert b"Apartamento 1q" in chamadas[1][2]                 # o card, como texto
    assert b"imovel:SP-1" in chamadas[1][2], "o card em texto mantém o botão Quero visitar"
    assert "wrong file identifier" in caplog.text and TOKEN not in caplog.text


def test_erro_do_telegram_nao_leva_o_token_na_mensagem(telegram):
    _, respostas = telegram
    respostas["sendMessage"] = (403, "Forbidden: bot was blocked by the user")
    with pytest.raises(outbound.TelegramRecusou) as erro:
        outbound.enviar(_corpo(None))
    assert "blocked by the user" in str(erro.value) and TOKEN not in str(erro.value)


def test_foto_fora_da_api_ou_com_nome_estranho_nao_vira_arquivo(telegram):
    assert outbound.foto_local("https://outro.com/acervo/apartamento/apartamento-01.jpg") is None
    assert outbound.foto_local("http://localhost:8000/acervo/../../etc/passwd") is None
    assert outbound.foto_local("http://localhost:8000/acervo/apartamento/apartamento-01.jpg") is not None


def test_log_mascara_token_de_bot_em_qualquer_mensagem():
    registro = logging.LogRecord("x", logging.ERROR, __file__, 1,
                                 "falhou em https://api.telegram.org/bot%s/sendPhoto", (TOKEN,), None)
    saida = _Mascarar(logging.Formatter("%(message)s")).format(registro)
    assert TOKEN not in saida and "<token-do-bot>" in saida


def test_a_conexao_e_reaproveitada_entre_respostas(telegram, monkeypatch):
    """Um cliente HTTP por resposta pagava o aperto de mão TLS a cada mensagem."""
    criados = []
    real = outbound.httpx.Client
    monkeypatch.setattr(outbound.httpx, "Client", lambda **kw: criados.append(1) or real(**kw))
    texto = json.dumps({"identificador": "555", "resposta": {"lead_id": "tg_555", "texto": "oi"}})
    outbound.enviar(texto)
    outbound.enviar(texto)
    assert len(criados) == 1
