"""Maya AI voice tools — TTS, STT, and wake word.

All voice processing is LOCAL only — nothing goes to the cloud.

Per AGENTS.md: Voice TTS/STT for Tamil + English. Piper TTS +
faster-whisper STT when installed; graceful fallback otherwise.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

try:
    import piper
    HAS_PIPER = True
except ImportError:
    HAS_PIPER = False

try:
    from faster_whisper import WhisperModel
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False


# ── Voice directories ──────────────────────────────────────────────────────

from ..config import PROJECT_ROOT

VOICE_DIR = PROJECT_ROOT / "MAYA AI" / "voice"
TAMIL_VOICE_DIR = VOICE_DIR / "tamil"
ENGLISH_VOICE_DIR = VOICE_DIR / "english"


# ── TTS (Piper) ────────────────────────────────────────────────────────────

def _speak_windows_sapi(text: str) -> str:
    """Speak text with the built-in Windows SAPI voice (offline, no download)."""
    if sys.platform != "win32":
        return "[TTS] No TTS backend. Install piper-tts + a voice model."
    escaped = text.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Speak('{escaped}')"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"[TTS] SAPI error: {exc}"
    if proc.returncode != 0:
        return f"[TTS] SAPI failed: {(proc.stderr or '').strip()[:200]}"
    return f"[TTS] Spoke (Windows SAPI): {text[:60]}"

class PiperTTS:
    """Piper TTS wrapper for local text-to-speech.

    Requires ``piper-tts`` package and .onnx voice models in
    ``MAYA AI/voice/tamil`` or ``MAYA AI/voice/english``.
    """

    def __init__(self, lang: str = "english") -> None:
        self.lang = lang
        self._model = None
        self._model_path: Optional[Path] = None
        if HAS_PIPER:
            self._load_model()

    def _load_model(self) -> None:
        """Load the Piper voice model for the configured language."""
        voice_dir = TAMIL_VOICE_DIR if self.lang == "tamil" else ENGLISH_VOICE_DIR
        if not voice_dir.is_dir():
            return
        # Look for .onnx model files
        onnx_files = list(voice_dir.glob("*.onnx"))
        if not onnx_files:
            return
        self._model_path = onnx_files[0]
        try:
            self._model = piper.PiperVoice.load(str(self._model_path))
        except Exception:
            self._model = None

    def is_available(self) -> bool:
        """Return True if Piper TTS is ready to speak."""
        return HAS_PIPER and self._model is not None

    def speak(self, text: str) -> str:
        """Speak text using Piper TTS, falling back to Windows SAPI."""
        if self.lang == "tamil":
            if not self.is_available():
                return (
                    "[TTS] Tamil voice needs piper-tts + a .onnx model in "
                    f"{TAMIL_VOICE_DIR}"
                )
        elif not self.is_available():
            # No Piper voice model for English — use the built-in Windows voice.
            return _speak_windows_sapi(text)
        try:
            # Piper speaks directly to audio output
            self._model.speak(text)
            return f"[TTS] Spoke: {text[:60]}..."
        except Exception as exc:
            return f"[TTS] Error: {exc}"


# Module-level TTS instances (english default, tamil available).
tts_english = PiperTTS("english")
tts_tamil = PiperTTS("tamil")


def speak(text: str, lang: str = "english") -> str:
    """Speak text using the appropriate TTS engine."""
    tts = tts_tamil if lang == "tamil" else tts_english
    return tts.speak(text)


# ── STT (faster-whisper) ──────────────────────────────────────────────────

class WhisperSTT:
    """faster-whisper wrapper for local speech-to-text.

    Requires ``faster-whisper`` package and a Whisper model cached
    locally (HF cache).
    """

    def __init__(self, model_size: str = "base") -> None:
        self.model_size = model_size
        self._model = None
        if HAS_WHISPER:
            self._load_model()

    def _load_model(self) -> None:
        """Load the Whisper model from local HF cache."""
        try:
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
            )
        except Exception:
            self._model = None

    def is_available(self) -> bool:
        """Return True if Whisper STT is ready to transcribe."""
        return HAS_WHISPER and self._model is not None

    def transcribe(self, audio_path: str) -> str:
        """Transcribe an audio file to text. Returns the text or error."""
        if not HAS_WHISPER:
            return "[STT] faster-whisper not installed. Run: uv pip install faster-whisper"
        if not self.is_available():
            return f"[STT] Whisper model '{self.model_size}' not available."
        try:
            segments, _ = self._model.transcribe(audio_path)
            text = "".join(seg.text for seg in segments)
            return text.strip()
        except Exception as exc:
            return f"[STT] Error: {exc}"


# Module-level STT instance.
stt = WhisperSTT()


def listen(audio_path: str, lang: str = "en") -> str:
    """Transcribe an audio file to text.

    Whisper is used when installed, otherwise the offline Vosk models that
    ship inside the project (``MAYA AI/Model/models``).
    """
    if stt.is_available():
        return stt.transcribe(audio_path)

    from . import voice_stt

    if not voice_stt.available().get(lang):
        return (
            f"[STT] No '{lang}' model. Add a Vosk model or install faster-whisper."
        )
    try:
        text = voice_stt.transcribe_file(audio_path, lang)
    except Exception as exc:
        return f"[STT] Error: {exc}"
    return text or "[STT] No speech recognised."


def listen_mic(seconds: int = 6, lang: str = "en") -> str:
    """Record from the microphone and transcribe it (offline, Vosk)."""
    from . import voice_stt

    text, error = voice_stt.listen(seconds=seconds, lang=lang)
    if error:
        return f"[STT] {error}"
    return text or ""


# ── Wake word (placeholder) ────────────────────────────────────────────────

WAKE_PHRASES = ["maya maya maya", "maya, maya, maya"]


def check_wake(text: str) -> bool:
    """Check if the given text contains a wake phrase.

    Wake: "Maya, Maya, Maya" (3 times) or 3 claps (audio-based,
    handled by the OS layer / wake listener).
    """
    if not text:
        return False
    text_lower = text.lower().strip()
    for phrase in WAKE_PHRASES:
        if phrase in text_lower:
            return True
    return False


def wake_reply() -> str:
    """Return Maya's wake response."""
    from ..config import load_settings

    settings = load_settings()
    return str(settings.get("wake", {}).get("reply", "Sollu da, enna venum?"))


# ── Status ─────────────────────────────────────────────────────────────────

def voice_status() -> dict[str, Any]:
    """Return voice subsystem status (no secrets exposed)."""
    from . import voice_stt

    sapi = sys.platform == "win32"
    stt_info = voice_stt.status()
    return {
        "piper_available": HAS_PIPER,
        "sapi_available": sapi,
        "tts_english_ready": tts_english.is_available() or sapi,
        "tts_tamil_ready": tts_tamil.is_available(),
        "whisper_available": HAS_WHISPER,
        "vosk_installed": stt_info["vosk_installed"],
        "stt_models": stt_info["models"],
        "stt_ready": stt.is_available() or stt_info["any_model"],
        "input_devices": stt_info["input_devices"],
        "voice_dir": str(VOICE_DIR),
        "tamil_dir": str(TAMIL_VOICE_DIR),
        "english_dir": str(ENGLISH_VOICE_DIR),
    }
