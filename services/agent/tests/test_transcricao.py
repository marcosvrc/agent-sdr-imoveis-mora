"""Transcrição de áudio: roteia o download pelo `meta` do canal, escolhe o motor por
configuração, e degrada com uma mensagem ao cliente quando algo falha.

Sem rede: o download e o motor são substituídos por fakes (padrão monkeypatch do repo).
"""
import pytest

from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem

from agent.tools import transcricao
from agent import handler


# ------------------------------------------------------------ motor efetivo

def test_motor_auto_usa_whisper(monkeypatch):
    """`auto` tem um motor só desde que o motor hospedado saiu. Vale continuar testando:
    é o padrão, e um `auto` que caísse em "desconhecido" derrubaria todo áudio recebido."""
    s = transcricao.get_settings()
    monkeypatch.setattr(s, "transcricao_provider", "auto", raising=False)
    assert transcricao._motor_efetivo() == "whisper_local"


def test_motor_desligado_e_respeitado(monkeypatch):
    s = transcricao.get_settings()
    monkeypatch.setattr(s, "transcricao_provider", "off", raising=False)
    assert transcricao._motor_efetivo() == "off"


def test_motor_desconhecido_falha_claro(monkeypatch):
    """Errar o nome no .env não pode virar silêncio: sem motor não há transcrição, e o cliente
    precisa ouvir isso do agente em vez de esperar por uma resposta que nunca vem."""
    monkeypatch.setattr(transcricao, "_motor_efetivo", lambda: "transcribe")
    monkeypatch.setattr(transcricao, "_baixar_audio", lambda meta: b"AUDIO")
    with pytest.raises(RuntimeError, match="motor de transcrição desconhecido"):
        transcricao.transcrever({"telegram_file_id": "x"})


# --------------------------------------------------------- roteamento do download

def test_transcrever_roteia_telegram(monkeypatch):
    chamou = {}
    monkeypatch.setattr(transcricao, "_motor_efetivo", lambda: "whisper_local")
    monkeypatch.setattr(transcricao, "_baixar_telegram", lambda meta: chamou.setdefault("tg", meta) or b"AUDIO")
    monkeypatch.setattr(transcricao, "_transcrever_whisper_local", lambda audio: "quero apartamento em pinheiros")

    texto = transcricao.transcrever({"telegram_file_id": "file-1", "telegram_chat_id": "555"})
    assert texto == "quero apartamento em pinheiros"
    assert chamou["tg"]["telegram_file_id"] == "file-1"


def test_meta_sem_origem_conhecida_falha_claro(monkeypatch):
    """Antes havia dois caminhos de download (Telegram e Meta) e este teste cobria o segundo. Com o
    WhatsApp fora, o que resta a garantir é que um `meta` sem origem reconhecida falhe DIZENDO isso,
    em vez de devolver áudio vazio e virar uma transcrição em branco."""
    with pytest.raises(RuntimeError, match="telegram_file_id"):
        transcricao._baixar_audio({"media_id": "antigo"})

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


def test_falha_de_transcricao_deixa_rastro_no_log(monkeypatch, caplog):
    """A frase de desculpa é igual para quatro causas diferentes: motor ausente na imagem, download
    do modelo, token do canal e áudio ilegível. Sem log, quem opera não tem como distinguir — e a
    primeira delas (o extra `local` faltando na imagem) foi exatamente o que aconteceu aqui."""
    import logging

    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem

    def explode(meta):
        raise ModuleNotFoundError("No module named 'faster_whisper'")

    monkeypatch.setattr("agent.tools.transcricao.transcrever", explode)
    entrada = MensagemNormalizada(lead_id="l-audio", canal=Canal.TELEGRAM, tipo=TipoMensagem.AUDIO,
                                  identificador_canal="123", conteudo="",
                                  meta={"telegram_file_id": "abc"})
    with caplog.at_level(logging.ERROR):
        saida = handler._transcrever_se_audio(entrada)
    assert "áudio não compreendido" in saida.conteudo, "o cliente continua recebendo a degradação"
    assert any("transcrever" in r.message for r in caplog.records), "a causa precisa aparecer no log"


def test_audio_ganha_recibo_antes_da_transcricao(monkeypatch):
    """Transcrever leva segundos, e silêncio depois de mandar um áudio se parece com falha — o
    cliente manda de novo ou desiste. O recibo sai ANTES do trabalho, e não entra no histórico:
    é entrega, não fala da Mora sobre o assunto."""
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem

    enviados = []
    monkeypatch.setattr(handler, "despachar", lambda c, i, r: enviados.append(r.texto))
    monkeypatch.setattr("agent.tools.transcricao._motor_efetivo", lambda: "whisper_local")
    monkeypatch.setattr("agent.tools.transcricao.transcrever", lambda meta: "quero alugar em Pinheiros")

    entrada = MensagemNormalizada(lead_id="l-rec", canal=Canal.TELEGRAM, tipo=TipoMensagem.AUDIO,
                                  identificador_canal="123", conteudo="",
                                  meta={"telegram_file_id": "abc"})
    saida = handler._transcrever_se_audio(entrada)
    assert enviados and "áudio" in enviados[0].lower()
    assert saida.conteudo == "quero alugar em Pinheiros"


def test_sem_motor_nao_se_promete_resposta(monkeypatch):
    """Com a transcrição desligada o cliente vai receber um pedido para escrever. Prometer 'já te
    respondo' antes disso seria mentir com uma frase a mais."""
    from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem

    enviados = []
    monkeypatch.setattr(handler, "despachar", lambda c, i, r: enviados.append(r.texto))
    monkeypatch.setattr("agent.tools.transcricao._motor_efetivo", lambda: "off")
    entrada = MensagemNormalizada(lead_id="l-off", canal=Canal.TELEGRAM, tipo=TipoMensagem.AUDIO,
                                  identificador_canal="123", conteudo="", meta={})
    handler._transcrever_se_audio(entrada)
    assert enviados == []


def test_painel_pode_desligar_a_transcricao(monkeypatch):
    """O botão que alguém vira AO VIVO — "está demorando, tira o áudio". Num arquivo de ambiente
    isso custaria recriar container no meio do atendimento."""
    monkeypatch.setattr(transcricao, "_do_painel", lambda: "off")
    assert transcricao._motor_efetivo() == "off"


def test_sem_opiniao_do_painel_vale_o_ambiente(monkeypatch):
    monkeypatch.setattr(transcricao, "_do_painel", lambda: None)
    s = transcricao.get_settings()
    monkeypatch.setattr(s, "transcricao_provider", "auto", raising=False)
    assert transcricao._motor_efetivo() == "whisper_local"
