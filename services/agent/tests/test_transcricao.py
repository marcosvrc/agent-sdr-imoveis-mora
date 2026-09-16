"""Transcrição de áudio: roteia o download por canal (Telegram vs WhatsApp), escolhe o motor por
perfil/config, e degrada com uma mensagem ao cliente quando algo falha.

Sem rede e sem AWS: o download e o motor são substituídos por fakes (padrão monkeypatch do repo).
"""
import pytest

from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem

from agent.tools import transcricao
from agent import handler


# ------------------------------------------------------------ motor efetivo

def test_motor_auto_local_usa_whisper(monkeypatch):
    monkeypatch.setattr(transcricao.get_settings, "cache_clear", lambda: None, raising=False)
    s = transcricao.get_settings()
    monkeypatch.setattr(s, "transcricao_provider", "auto", raising=False)
    monkeypatch.setattr(s, "profile", "local", raising=False)
    assert transcricao._motor_efetivo() == "whisper_local"


def test_motor_auto_aws_usa_transcribe(monkeypatch):
    s = transcricao.get_settings()
    monkeypatch.setattr(s, "transcricao_provider", "auto", raising=False)
    monkeypatch.setattr(s, "profile", "aws", raising=False)
    assert transcricao._motor_efetivo() == "transcribe"


def test_motor_forcado_ignora_perfil(monkeypatch):
    s = transcricao.get_settings()
    monkeypatch.setattr(s, "transcricao_provider", "whisper_local", raising=False)
    monkeypatch.setattr(s, "profile", "aws", raising=False)
    assert transcricao._motor_efetivo() == "whisper_local"


# --------------------------------------------------------- roteamento do download

def test_transcrever_roteia_telegram(monkeypatch):
    chamou = {}
    monkeypatch.setattr(transcricao, "_motor_efetivo", lambda: "whisper_local")
    monkeypatch.setattr(transcricao, "_baixar_telegram", lambda meta: chamou.setdefault("tg", meta) or b"AUDIO")
    monkeypatch.setattr(transcricao, "_baixar_whatsapp", lambda meta: pytest.fail("não deveria baixar do WhatsApp"))
    monkeypatch.setattr(transcricao, "_transcrever_whisper_local", lambda audio: "quero apartamento em pinheiros")

    texto = transcricao.transcrever({"telegram_file_id": "file-1", "telegram_chat_id": "555"})
    assert texto == "quero apartamento em pinheiros"
    assert chamou["tg"]["telegram_file_id"] == "file-1"


def test_transcrever_roteia_whatsapp(monkeypatch):
    monkeypatch.setattr(transcricao, "_motor_efetivo", lambda: "transcribe")
    monkeypatch.setattr(transcricao, "_baixar_whatsapp", lambda meta: b"AUDIO")
    monkeypatch.setattr(transcricao, "_baixar_telegram", lambda meta: pytest.fail("não deveria baixar do Telegram"))
    monkeypatch.setattr(transcricao, "_transcrever_transcribe", lambda audio, meta: "tem casa para alugar")

    assert transcricao.transcrever({"media_id": "media-1"}) == "tem casa para alugar"


def test_meta_sem_audio_levanta(monkeypatch):
    monkeypatch.setattr(transcricao, "_motor_efetivo", lambda: "whisper_local")
    with pytest.raises(RuntimeError):
        transcricao.transcrever({"nome": "Marcos"})


def test_provider_off_nao_baixa(monkeypatch):
    monkeypatch.setattr(transcricao, "_motor_efetivo", lambda: "off")
    monkeypatch.setattr(transcricao, "_baixar_audio", lambda meta: pytest.fail("off não deve baixar"))
    with pytest.raises(RuntimeError):
        transcricao.transcrever({"telegram_file_id": "file-1"})


# ------------------------------------------------------- integração com o handler (fallback)

def test_handler_preenche_conteudo_com_transcricao(monkeypatch):
    monkeypatch.setattr(handler, "_transcrever_se_audio", handler._transcrever_se_audio)  # garante o real
    monkeypatch.setattr("agent.tools.transcricao.transcrever", lambda meta: "quero investir")
    ent = MensagemNormalizada(lead_id="tg_1", canal=Canal.TELEGRAM, identificador_canal="555",
                              tipo=TipoMensagem.AUDIO, conteudo="", meta={"telegram_file_id": "f1"})
    saida = handler._transcrever_se_audio(ent)
    assert saida.conteudo == "quero investir"


def test_handler_fallback_quando_transcricao_falha(monkeypatch):
    def _explode(meta):
        raise RuntimeError("motor indisponível")
    monkeypatch.setattr("agent.tools.transcricao.transcrever", _explode)
    ent = MensagemNormalizada(lead_id="tg_1", canal=Canal.TELEGRAM, identificador_canal="555",
                              tipo=TipoMensagem.AUDIO, conteudo="", meta={"telegram_file_id": "f1"})
    saida = handler._transcrever_se_audio(ent)
    assert "áudio não compreendido" in saida.conteudo


def test_handler_ignora_nao_audio(monkeypatch):
    monkeypatch.setattr("agent.tools.transcricao.transcrever", lambda meta: pytest.fail("não deveria transcrever texto"))
    ent = MensagemNormalizada(lead_id="web_1", canal=Canal.WEB, identificador_canal="s",
                              tipo=TipoMensagem.TEXTO, conteudo="olá")
    assert handler._transcrever_se_audio(ent).conteudo == "olá"
