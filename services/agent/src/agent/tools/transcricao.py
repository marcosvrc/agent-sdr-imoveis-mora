"""Áudio (mensagem de voz) → texto.

Dois eixos independentes:

1. **De onde baixar o áudio** — roteado pelo `meta` da MensagemNormalizada:
   - `telegram_file_id`  → Bot API do Telegram (getFile + download).

2. **Qual motor transcreve** — escolhido por `SDR_TRANSCRICAO_PROVIDER` (padrão `auto`):
   - `auto`          → `whisper_local`.
   - `whisper_local` → faster-whisper in-process, sem serviço externo e sem custo por minuto.
   - `off`           → não transcreve (levanta erro; o handler responde pedindo texto).

A saída desta função é sempre tratada como entrada NÃO confiável pelo agente
(`agent/prompts/__init__.py::NAO_CONFIAVEIS` inclui "transcricao"): entra no prompt dentro do
bloco blindado, como qualquer texto vindo do cliente.
"""

import httpx

from sdr_shared.config import get_settings

_LANG = "pt"                 # código de idioma que o Whisper espera


# ---------------------------------------------------------------- download

def _baixar_telegram(meta: dict) -> bytes:
    """getFile → file_path → download. Áudio de voz do Telegram é OGG/Opus."""
    s = get_settings()
    if not s.telegram_bot_token:
        raise RuntimeError("SDR_TELEGRAM_BOT_TOKEN ausente para baixar o áudio")
    base = f"https://api.telegram.org/bot{s.telegram_bot_token}"
    with httpx.Client(timeout=30) as http:
        info = http.get(f"{base}/getFile", params={"file_id": meta["telegram_file_id"]})
        info.raise_for_status()
        file_path = info.json()["result"]["file_path"]
        audio = http.get(f"https://api.telegram.org/file/bot{s.telegram_bot_token}/{file_path}")
        audio.raise_for_status()
        return audio.content


def _baixar_audio(meta: dict) -> bytes:
    """Roteia pelo que o canal deixou no meta. Sem KeyError: valida a presença antes."""
    if meta.get("telegram_file_id"):
        return _baixar_telegram(meta)
    raise RuntimeError("meta sem telegram_file_id — nada para baixar")


# ------------------------------------------------------------ motor local

_whisper = None


def _modelo_whisper():
    """Carrega o faster-whisper uma vez por processo (o load é caro)."""
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel     # dependência opcional do extra `local`
        # compute_type int8: leve em CPU, suficiente para voz curta de qualificação de lead.
        _whisper = WhisperModel(get_settings().whisper_model, device="cpu", compute_type="int8")
    return _whisper


def _transcrever_whisper_local(audio: bytes) -> str:
    import io
    segmentos, _ = _modelo_whisper().transcribe(io.BytesIO(audio), language=_LANG)
    return " ".join(seg.text.strip() for seg in segmentos).strip()


def _motor_efetivo() -> str:
    """O painel manda; o `.env` é o piso.

    Desligar a transcrição é o botão que alguém quer virar AO VIVO — "está demorando, tira o áudio"
    — e num arquivo de ambiente isso custa recriar container no meio do atendimento.
    """
    s = get_settings()
    escolha = _do_painel() or (s.transcricao_provider or "auto")
    escolha = escolha.lower()
    if escolha == "auto":
        return "whisper_local"
    return escolha


def _do_painel() -> str | None:
    try:
        from sdr_shared.db import operacao_texto
        return operacao_texto("transcricao")
    except Exception:                       # sem banco (testes, boot): o ambiente decide sozinho
        return None


def transcrever(meta: dict) -> str:
    """Áudio (meta do canal) → texto. Levanta em falha; o handler trata e pede texto ao cliente."""
    motor = _motor_efetivo()
    if motor == "off":
        raise RuntimeError("transcrição desativada (SDR_TRANSCRICAO_PROVIDER=off)")
    audio = _baixar_audio(meta)
    if motor == "whisper_local":
        return _transcrever_whisper_local(audio)
    raise RuntimeError(f"motor de transcrição desconhecido: {motor}")
