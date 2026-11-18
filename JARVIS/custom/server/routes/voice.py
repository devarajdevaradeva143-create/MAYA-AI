"""Voice endpoints: STT upload, TTS WAV download, engine status."""

from __future__ import annotations

import io
import tempfile
import uuid
import wave
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from custom.server.auth import DeviceDep
from custom.server.errors import ApiError
from custom.server.models import VoiceTtsRequest

router = APIRouter(prefix="/voice", tags=["voice"])

MAX_AUDIO_BYTES = 5 * 1024 * 1024
MAX_AUDIO_SECONDS = 30.0
LANGUAGES = {"en", "en-in", "ta"}


def _validate_wav(data: bytes) -> None:
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ApiError(2001, "Invalid WAV file")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            rate = wav.getframerate()
            frames = wav.getnframes()
    except (wave.Error, EOFError) as exc:
        raise ApiError(2001, "Invalid WAV file") from exc
    if rate <= 0:
        raise ApiError(2001, "Invalid WAV file")
    if frames / float(rate) > MAX_AUDIO_SECONDS + 0.5:
        raise ApiError(2001, "Audio too long (max 30 s)")


def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


@router.post("/stt")
def speech_to_text(
    request: Request,
    device: DeviceDep,
    audio: Annotated[UploadFile, File()],
    lang: Annotated[str, Form()] = "en",
    duration_ms: Annotated[str | None, Form()] = None,
) -> dict:
    del duration_ms  # optional hint; WAV header is authoritative
    state = request.app.state
    state.limiter.hit(f"stt:{device.device_id}", 10, 60)
    if lang not in LANGUAGES:
        raise ApiError(2001, "Unsupported language")

    data = audio.file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise ApiError(2003, "Audio file too large")
    _validate_wav(data)

    temp_dir = Path(tempfile.gettempdir()) / "maya"
    temp_dir.mkdir(parents=True, exist_ok=True)
    wav_path = temp_dir / f"stt-{uuid.uuid4().hex}.wav"
    wav_path.write_bytes(data)
    try:
        try:
            result = state.services.voice.transcribe(wav_path, lang)
        except ApiError:
            raise
        except Exception as exc:  # noqa: BLE001 - mapped to contract error
            raise ApiError(3003, "Speech recognition unavailable") from exc
    finally:
        _remove(wav_path)

    if isinstance(result, dict):
        text = str(result.get("text", ""))
        engine = str(result.get("engine") or "vosk")
    else:
        text = str(result or "")
        engine = "vosk"
    return {"text": text, "lang": lang, "engine": engine}


@router.post("/tts")
def text_to_speech(
    body: VoiceTtsRequest,
    request: Request,
    device: DeviceDep,
):
    state = request.app.state
    try:
        wav_path = state.services.voice.synthesize_wav(
            body.text,
            engine=body.engine,
            voice=body.voice,
            lang=body.lang,
            speed=body.speed,
        )
    except ApiError:
        raise
    except Exception as exc:  # noqa: BLE001 - mapped to contract error
        raise ApiError(3004, "Text to speech unavailable") from exc

    path = Path(wav_path)
    if not path.is_file():
        raise ApiError(3004, "Text to speech unavailable")
    return FileResponse(
        path,
        media_type="audio/wav",
        filename="maya.wav",
        background=BackgroundTask(_remove, path),
    )


@router.get("/status")
def voice_status(
    request: Request,
    device: DeviceDep,
) -> dict:
    del device
    try:
        return request.app.state.services.voice.status()
    except Exception as exc:  # noqa: BLE001 - status must stay useful
        raise ApiError(3004, "Voice status unavailable") from exc
