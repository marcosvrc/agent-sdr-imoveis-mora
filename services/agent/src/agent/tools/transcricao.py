"""Áudio (mensagem de voz) → texto.

Dois eixos independentes:

1. **De onde baixar o áudio** — roteado pelo `meta` da MensagemNormalizada:
   - `telegram_file_id`  → Bot API do Telegram (getFile + download).
   - `media_id`          → Graph API da Meta (WhatsApp).

2. **Qual motor transcreve** — escolhido por `SDR_TRANSCRICAO_PROVIDER` (padrão `auto`):
   - `auto`          → `whisper_local` no perfil local, `transcribe` no perfil aws.
   - `whisper_local` → faster-whisper in-process (sem AWS, sem custo; ideal para o perfil local).
   - `transcribe`    → Amazon Transcribe (perfil aws): sobe o áudio no S3 e consulta o job.
   - `off`           → não transcreve (levanta erro; o handler responde pedindo texto).

A saída desta função é sempre tratada como entrada NÃO confiável pelo agente
(`agent/prompts/__init__.py::NAO_CONFIAVEIS` inclui "transcricao"): entra no prompt dentro do
bloco blindado, como qualquer texto vindo do cliente.
"""
import time
import uuid

import httpx

from sdr_shared.config import get_settings

_LANG = "pt"                 # pt-BR para o Transcribe; "pt" para o Whisper


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


def _baixar_whatsapp(meta: dict) -> bytes:
    """Resolve a URL da mídia na Graph API da Meta e baixa os bytes."""
    s = get_settings()
    h = {"Authorization": f"Bearer {s.whatsapp_token}"}
    url = httpx.get(f"https://graph.facebook.com/v21.0/{meta['media_id']}", headers=h, timeout=10).json()["url"]
    return httpx.get(url, headers=h, timeout=30).content


def _baixar_audio(meta: dict) -> bytes:
    """Roteia pelo que o canal deixou no meta. Sem KeyError: valida a presença antes."""
    if meta.get("telegram_file_id"):
        return _baixar_telegram(meta)
    if meta.get("media_id"):
        return _baixar_whatsapp(meta)
    raise RuntimeError("meta sem telegram_file_id nem media_id — nada para baixar")


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


# ----------------------------------------------------------- motor AWS

def _transcrever_transcribe(audio: bytes, meta: dict) -> str:
    """Sobe o áudio no S3 e roda um job síncrono do Amazon Transcribe (pt-BR)."""
    import boto3
    s = get_settings()
    s3, key = boto3.client("s3"), f"audio/{uuid.uuid4()}.ogg"
    bucket = meta.get("bucket") or s.audio_bucket
    if not bucket:
        raise RuntimeError("SDR_AUDIO_BUCKET ausente para o Amazon Transcribe")
    s3.put_object(Bucket=bucket, Key=key, Body=audio)
    tr, job = boto3.client("transcribe"), f"sdr-{uuid.uuid4()}"
    tr.start_transcription_job(TranscriptionJobName=job, LanguageCode="pt-BR", MediaFormat="ogg",
                               Media={"MediaFileUri": f"s3://{bucket}/{key}"})
    for _ in range(40):
        st = tr.get_transcription_job(TranscriptionJobName=job)["TranscriptionJob"]
        if st["TranscriptionJobStatus"] in ("COMPLETED", "FAILED"):
            break
        time.sleep(1.5)
    if st["TranscriptionJobStatus"] != "COMPLETED":
        raise RuntimeError("transcrição falhou")
    return httpx.get(st["Transcript"]["TranscriptFileUri"], timeout=10).json()["results"]["transcripts"][0]["transcript"]


# --------------------------------------------------------------- entrada

def _motor_efetivo() -> str:
    s = get_settings()
    escolha = (s.transcricao_provider or "auto").lower()
    if escolha == "auto":
        return "whisper_local" if s.profile == "local" else "transcribe"
    return escolha


def transcrever(meta: dict) -> str:
    """Áudio (meta do canal) → texto. Levanta em falha; o handler trata e pede texto ao cliente."""
    motor = _motor_efetivo()
    if motor == "off":
        raise RuntimeError("transcrição desativada (SDR_TRANSCRICAO_PROVIDER=off)")
    audio = _baixar_audio(meta)
    if motor == "whisper_local":
        return _transcrever_whisper_local(audio)
    if motor == "transcribe":
        return _transcrever_transcribe(audio, meta)
    raise RuntimeError(f"motor de transcrição desconhecido: {motor}")
