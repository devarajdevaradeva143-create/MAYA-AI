"""Local biometrics — Windows Hello face + Vosk speaker verification.

Privacy rules (AGENTS.md):
  * everything runs on this laptop; nothing is uploaded
  * no audio, no photo, no transcript is ever written to disk
  * only a salted PBKDF2 hash of the spoken phrase and an averaged speaker
    vector are stored, in ``MAYA AI/memory/offline/biometrics.json``
  * the PIN always remains the fallback

Face
----
Windows Hello is driven through the trusted ``MAYA.exe`` helper (copied from
the user's earlier PA project) at ``MAYA AI/security/bin/MAYA.exe``:

    MAYA.exe --face-check          -> AVAILABILITY=Available, exit 0
    MAYA.exe --face-auth [secs]    -> RESULT=Verified, exit 0

Exit codes: 0 verified, 2 not verified/cancelled, 3 no window, 4 timeout,
1 error. The helper only prints status lines; no images leave the process.

Voice
-----
Two independent factors, both local:

  1. **Passphrase** — Vosk transcribes what you said; only PBKDF2 hashes of
     the accepted transcripts are stored (ported from the old project).
  2. **Speaker** — Vosk's x-vector model (``vosk-spk``) turns the same audio
     into a 128-dim voice vector; verification compares it with the enrolled
     centroid by cosine similarity.

Both must pass by default. ``security.biometrics.voice.require_speaker: false``
turns the speaker factor off (passphrase only).
"""

from __future__ import annotations

import difflib
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import subprocess
import time
import unicodedata
from pathlib import Path
from typing import Any

from ..config import PROJECT_ROOT, load_settings

ENV_BIOMETRICS_STORE = "MAYA_BIOMETRICS_STORE"
ENV_MAYA_EXE = "MAYA_EXE"
STORE_FILENAME = "biometrics.json"

DEFAULT_OFFLINE_MEMORY = "memory/offline"
DEFAULT_EXE = PROJECT_ROOT / "MAYA AI" / "security" / "bin" / "MAYA.exe"

PBKDF2_ITERATIONS = 260_000
PHRASE_MATCH_RATIO = 0.82
MIN_SAMPLES = 2
DEFAULT_SAMPLES = 3
DEFAULT_THRESHOLD = 0.65
DEFAULT_MAX_ATTEMPTS = 5
FACE_CACHE_TTL = 30.0

_face_cache: dict[str, Any] = {"at": 0.0, "value": None}
_face_busy = False

_stt_model: Any = None
_stt_model_path = ""
_spk_model: Any = None
_spk_model_path = ""


# ── Settings / paths ───────────────────────────────────────────────────────

def _settings() -> dict[str, Any]:
    try:
        settings = load_settings()
    except Exception:  # pragma: no cover - config must never crash security
        return {}
    return settings if isinstance(settings, dict) else {}


def _biometrics_cfg() -> dict[str, Any]:
    security = _settings().get("security", {})
    if not isinstance(security, dict):
        return {}
    cfg = security.get("biometrics", {})
    return cfg if isinstance(cfg, dict) else {}


def _voice_cfg() -> dict[str, Any]:
    voice = _biometrics_cfg().get("voice", {})
    return voice if isinstance(voice, dict) else {}


def _store_path() -> Path:
    override = os.environ.get(ENV_BIOMETRICS_STORE, "").strip()
    if override:
        return Path(override).expanduser()
    memory = _settings().get("memory", {}) if isinstance(_settings(), dict) else {}
    offline = memory.get("offline", DEFAULT_OFFLINE_MEMORY) if isinstance(memory, dict) else DEFAULT_OFFLINE_MEMORY
    path = Path(str(offline))
    if not path.is_absolute():
        path = PROJECT_ROOT / "MAYA AI" / path
    return path / STORE_FILENAME


def model_root() -> Path:
    """Vosk model root, shared with the STT module (settings-driven)."""
    voice = _settings().get("voice", {})
    stt = voice.get("stt", {}) if isinstance(voice, dict) else {}
    root = stt.get("model_root") if isinstance(stt, dict) else None
    path = Path(str(root)).expanduser() if root else PROJECT_ROOT / "MAYA AI" / "Model" / "models"
    return path if path.is_absolute() else PROJECT_ROOT / path


def speaker_model_path() -> Path:
    name = str(_voice_cfg().get("speaker_model") or "vosk-spk")
    path = Path(name).expanduser()
    return path if path.is_absolute() else model_root() / path


def speaker_threshold() -> float:
    try:
        return float(_voice_cfg().get("speaker_threshold", DEFAULT_THRESHOLD))
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD


def require_speaker() -> bool:
    return bool(_voice_cfg().get("require_speaker", True))


def default_samples() -> int:
    try:
        return max(MIN_SAMPLES, int(_voice_cfg().get("samples", DEFAULT_SAMPLES)))
    except (TypeError, ValueError):
        return DEFAULT_SAMPLES


def _max_attempts() -> int:
    try:
        return max(1, int(_voice_cfg().get("max_attempts", DEFAULT_MAX_ATTEMPTS)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_ATTEMPTS


def _prepare_logs() -> None:
    try:
        from vosk import SetLogLevel

        SetLogLevel(-1)
    except Exception:  # pragma: no cover - vosk optional at import time
        pass


# ── Store ──────────────────────────────────────────────────────────────────

def _default_store() -> dict[str, Any]:
    return {
        "version": 1,
        "voice": None,
        "voice_fail": {"count": 0, "last": 0, "locked_until": 0},
    }


def _load_store() -> dict[str, Any]:
    path = _store_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        pass
    return _default_store()


def _save_store(data: dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# ── Face: Windows Hello ────────────────────────────────────────────────────

def maya_exe() -> Path | None:
    override = os.environ.get(ENV_MAYA_EXE, "").strip()
    candidates = [Path(override).expanduser()] if override else []
    candidates.append(DEFAULT_EXE)
    for path in candidates:
        if path.is_file():
            return path
    return None


def _run_face(mode: str, timeout: int) -> dict[str, Any]:
    exe = maya_exe()
    if exe is None:
        return {
            "ok": False,
            "code": "helper_missing",
            "error": f"Face helper not found at {DEFAULT_EXE}.",
        }

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
    args = [str(exe), mode]
    if mode == "--face-auth":
        args.append(str(max(10, min(180, int(timeout)))))

    try:
        completed = subprocess.run(
            args,
            cwd=str(exe.parent),
            capture_output=True,
            text=True,
            timeout=max(15, int(timeout)) + 20,
            creationflags=flags,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "timeout", "error": "Windows Hello did not respond in time."}
    except OSError:
        return {"ok": False, "code": "helper_blocked", "error": "Windows blocked the face helper."}

    output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).upper()
    if mode == "--face-check":
        if "AVAILABILITY=" not in output:
            return {
                "ok": False,
                "code": "helper_outdated",
                "error": "Face helper did not answer with AVAILABILITY=.",
            }
        if completed.returncode == 0 and "AVAILABILITY=AVAILABLE" in output:
            return {"ok": True, "code": "available", "error": None}
        return {
            "ok": False,
            "code": "unavailable",
            "error": "Windows Hello face is not set up for this account.",
        }

    if "RESULT=" not in output:
        if completed.returncode == 4 or "ERROR=TIMEOUT" in output:
            return {"ok": False, "code": "timeout", "error": "Windows Hello timed out."}
        if completed.returncode == 3 or "ERROR=NO-WINDOW" in output:
            return {"ok": False, "code": "no_window", "error": "No window for the Hello prompt."}
        if completed.returncode == 1 and "ERROR=" in output:
            return {"ok": False, "code": "face_error", "error": "Windows Hello failed."}
        return {
            "ok": False,
            "code": "helper_outdated",
            "error": "Face helper did not answer with RESULT=.",
        }
    if completed.returncode == 0 and "RESULT=VERIFIED" in output:
        return {"ok": True, "code": "verified", "error": None}
    if completed.returncode == 2:
        return {
            "ok": False,
            "code": "not_verified",
            "error": "Face not recognized, or Windows Hello was cancelled.",
        }
    if completed.returncode == 3:
        return {"ok": False, "code": "no_window", "error": "No window for the Hello prompt."}
    if completed.returncode == 4:
        return {"ok": False, "code": "timeout", "error": "Windows Hello timed out."}
    return {"ok": False, "code": "face_error", "error": "Windows Hello failed."}


def face_status(force: bool = False) -> dict[str, Any]:
    """Availability without showing a prompt (cached for 30 s)."""
    global _face_busy
    now = time.time()
    cached = _face_cache.get("value")
    if cached is not None and not force and now - float(_face_cache.get("at", 0)) < FACE_CACHE_TTL:
        return dict(cached)
    if _face_busy:
        return {"available": False, "code": "busy", "error": "Face check already running."}
    _face_busy = True
    try:
        result = _run_face("--face-check", 15)
    finally:
        _face_busy = False
    value = {"available": bool(result.get("ok")), "code": result.get("code"), "error": result.get("error")}
    _face_cache["at"] = time.time()
    _face_cache["value"] = dict(value)
    return value


def face_verify(timeout: int = 60) -> dict[str, Any]:
    """Show the Windows Hello prompt. Requires a real face gesture."""
    global _face_busy
    if _face_busy:
        return {"ok": False, "code": "busy", "error": "A face check is already running."}
    _face_busy = True
    try:
        return _run_face("--face-auth", timeout)
    finally:
        _face_busy = False


def open_face_settings() -> dict[str, Any]:
    """Open Windows Sign-in options so the owner can enroll a face."""
    try:
        os.startfile("ms-settings:signinoptions")  # type: ignore[attr-defined]
        return {"ok": True, "error": None}
    except Exception:
        return {"ok": False, "code": "settings_failed", "error": "Could not open Windows Settings."}


# ── Phrase helpers (ported from the old project) ───────────────────────────

def normalize_phrase(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace. Never stored raw."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", str(text)).casefold()
    chars = [ch if (ch.isalnum() or ch.isspace()) else " " for ch in normalized]
    return re.sub(r"\s+", " ", "".join(chars)).strip()


def phrase_problem(normalized: str) -> str | None:
    words = normalized.split()
    if len(words) < 2:
        return "Use at least two words, for example: maya open the door."
    if len(words) > 14:
        return "That phrase is too long. Use 2 to 14 words."
    if len(normalized) < 6:
        return "That phrase is too short. Use a few clear words."
    if len(normalized) > 80:
        return "That phrase is too long. Keep it under 80 characters."
    return None


def _hash_phrase(normalized: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", normalized.encode("utf-8"), salt, int(iterations))


def _normalise_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return []
    return [value / norm for value in vector]


def cosine(left: list[float], right: list[float]) -> float:
    """Cosine similarity; 0.0 for mismatched or empty vectors."""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if norm_left == 0 or norm_right == 0:
        return 0.0
    return dot / (norm_left * norm_right)


# ── Speaker model (Vosk x-vectors) ─────────────────────────────────────────

def speaker_available() -> bool:
    return speaker_model_path().is_dir()


def _load_models():
    """Load the STT model + speaker model once per process."""
    global _stt_model, _stt_model_path, _spk_model, _spk_model_path
    from vosk import Model, SpkModel

    _prepare_logs()
    from .voice_stt import model_path as stt_model_path

    stt_path = stt_model_path("en")
    spk_path = speaker_model_path()
    if _stt_model is None or _stt_model_path != str(stt_path):
        _stt_model = Model(str(stt_path))
        _stt_model_path = str(stt_path)
    if _spk_model is None or _spk_model_path != str(spk_path):
        _spk_model = SpkModel(str(spk_path))
        _spk_model_path = str(spk_path)
    return _stt_model, _spk_model


def read_wav_16k(path: str | Path) -> tuple[bytes, int]:
    """Return raw 16-bit PCM at 16 kHz, converting 48 kHz captures if needed."""
    import wave

    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        frames = handle.readframes(handle.getnframes())
    if width != 2:
        raise RuntimeError("Only 16-bit PCM WAV files are supported.")
    if channels != 1:
        raise RuntimeError("Mono WAV files only — record with the built-in capture.")
    if rate != 16000:
        from .voice_stt import _prepare_for_vosk

        samples, _ = _prepare_for_vosk(frames, rate)
        frames = samples.tobytes()
        rate = 16000
    return frames, rate


def speaker_vector(wav_path: str | Path) -> list[float]:
    """Extract the 128-dim x-vector for a WAV file.

    Raises ``RuntimeError`` with a clear reason when the model or audio is bad.
    """
    if not speaker_available():
        raise RuntimeError(f"Speaker model missing: {speaker_model_path()}")
    frames, rate = read_wav_16k(wav_path)
    if not frames:
        raise RuntimeError("WAV file has no audio.")
    from vosk import KaldiRecognizer

    stt, spk = _load_models()
    recognizer = KaldiRecognizer(stt, rate, spk)
    recognizer.AcceptWaveform(frames)
    result = json.loads(recognizer.FinalResult())
    vector = result.get("spk")
    if not vector:
        raise RuntimeError("No speaker vector — the audio may be too short.")
    return [float(value) for value in vector]


def transcribe_wav(wav_path: str | Path) -> str:
    """Transcribe a WAV with the project's English Vosk model (cached)."""
    frames, rate = read_wav_16k(wav_path)
    if not frames:
        return ""
    from vosk import KaldiRecognizer

    stt, _ = _load_models()
    recognizer = KaldiRecognizer(stt, rate)
    recognizer.AcceptWaveform(frames)
    return str(json.loads(recognizer.FinalResult()).get("text", "")).strip()


# ── Voice enrollment / verification ────────────────────────────────────────

def _public_voice(data: dict[str, Any]) -> dict[str, Any]:
    voice = data.get("voice")
    enrolled = bool(voice and voice.get("hashes"))
    fail = data.get("voice_fail") or {}
    now = time.time()
    locked_until = float(fail.get("locked_until", 0) or 0)
    remaining = max(0, int(round(locked_until - now))) if locked_until > now else 0
    count = max(0, int(fail.get("count", 0) or 0))
    max_attempts = _max_attempts()
    attempts_left = max(0, max_attempts - (count % max_attempts)) if enrolled else 0
    if remaining:
        attempts_left = 0
    speaker = (voice or {}).get("speaker") or {}
    return {
        "enrolled": enrolled,
        "variants": len(voice.get("hashes") or []) if enrolled else 0,
        "speaker": bool(speaker.get("centroid")),
        "threshold": float(speaker.get("threshold", speaker_threshold())) if speaker else speaker_threshold(),
        "locked": remaining > 0,
        "remaining": remaining,
        "attempts_left": attempts_left,
    }


def voice_status() -> dict[str, Any]:
    return _public_voice(_load_store())


def voice_enroll(transcripts: list[str], vectors: list[list[float]] | None = None) -> dict[str, Any]:
    """Store hashes of the accepted transcripts and the speaker centroid.

    ``transcripts`` are the Vosk results of repeating the same phrase.
    ``vectors`` are the matching speaker x-vectors (required when the speaker
    factor is enabled). Nothing raw is stored.
    """
    cleaned: list[str] = []
    for text in transcripts:
        normalized = normalize_phrase(text)
        problem = phrase_problem(normalized)
        if problem:
            return {"ok": False, "code": "weak_phrase", "error": problem}
        cleaned.append(normalized)

    if len(cleaned) < MIN_SAMPLES:
        return {
            "ok": False,
            "code": "few_samples",
            "error": f"At least {MIN_SAMPLES} samples are needed.",
        }

    first = cleaned[0]
    for index, value in enumerate(cleaned[1:], start=2):
        ratio = difflib.SequenceMatcher(None, first, value).ratio()
        if ratio < PHRASE_MATCH_RATIO:
            return {
                "ok": False,
                "code": "mismatch",
                "error": f"Sample {index} did not match the first one. Say the same phrase.",
            }

    vectors = vectors or []
    if require_speaker():
        if not speaker_available():
            return {
                "ok": False,
                "code": "speaker_missing",
                "error": f"Speaker model missing: {speaker_model_path()}",
            }
        if len(vectors) != len(cleaned) or not vectors:
            return {
                "ok": False,
                "code": "speaker_missing",
                "error": "Speaker vectors are required (record the samples with --wav or the mic).",
            }

    variants: list[str] = []
    for value in cleaned:
        if value not in variants:
            variants.append(value)

    salt = secrets.token_bytes(16)
    record: dict[str, Any] = {
        "algo": "pbkdf2_sha256",
        "iterations": PBKDF2_ITERATIONS,
        "salt": salt.hex(),
        "hashes": [
            _hash_phrase(value, salt, PBKDF2_ITERATIONS).hex() for value in variants
        ],
        "created": int(time.time()),
    }

    if vectors:
        dims = {len(vector) for vector in vectors}
        if len(dims) != 1:
            return {"ok": False, "code": "bad_vector", "error": "Speaker vectors differ in size."}
        count = len(vectors)
        centroid = [
            sum(vector[i] for vector in vectors) / count
            for i in range(next(iter(dims)))
        ]
        centroid = _normalise_vector(centroid)
        record["speaker"] = {
            "model": speaker_model_path().name,
            "dim": len(centroid),
            "threshold": speaker_threshold(),
            "samples": count,
            "centroid": [round(value, 6) for value in centroid],
        }

    data = _load_store()
    data["voice"] = record
    data["voice_fail"] = {"count": 0, "last": 0, "locked_until": 0}
    try:
        _save_store(data)
    except OSError:
        return {"ok": False, "code": "save_failed", "error": "Biometric data could not be saved."}

    return {
        "ok": True,
        "enrolled": True,
        "variants": len(variants),
        "speaker": bool(record.get("speaker")),
        "dim": len(record.get("speaker", {}).get("centroid", [])),
    }


def voice_verify(
    text: str,
    vector: list[float] | None = None,
    enforce_speaker: bool | None = None,
) -> dict[str, Any]:
    """Verify a transcript (passphrase) and optionally a speaker vector.

    ``enforce_speaker=False`` is a diagnostic path for the local CLI: it checks
    the passphrase only. Normal use (``None``) follows settings.yaml.
    """
    normalized = normalize_phrase(text)
    if not normalized:
        return {"ok": False, "code": "no_speech", "error": "No speech recognized."}

    data = _load_store()
    voice = data.get("voice")
    if not voice or not voice.get("hashes"):
        return {"ok": False, "code": "not_enrolled", "error": "No voice password is set up yet."}

    now = time.time()
    fail = data.get("voice_fail") or {}
    count = max(0, int(fail.get("count", 0) or 0))
    locked_until = float(fail.get("locked_until", 0) or 0)
    if locked_until > now:
        remaining = max(1, int(round(locked_until - now)))
        return {
            "ok": False,
            "code": "locked",
            "error": f"Too many attempts. Wait {remaining} seconds.",
            "remaining": remaining,
            "attempts_left": 0,
        }
    if locked_until and locked_until <= now and count >= _max_attempts():
        count, locked_until = 0, 0.0

    try:
        salt = bytes.fromhex(voice.get("salt", ""))
        iterations = int(voice.get("iterations", PBKDF2_ITERATIONS))
        stored = [bytes.fromhex(value) for value in voice.get("hashes", [])]
    except (ValueError, TypeError):
        return {"ok": False, "code": "corrupt", "error": "Voice data is damaged. Set it up again."}

    candidate = _hash_phrase(normalized, salt, iterations)
    passphrase_ok = any(hmac.compare_digest(candidate, value) for value in stored)

    speaker = voice.get("speaker") or {}
    enforce = require_speaker() if enforce_speaker is None else bool(enforce_speaker)
    speaker_score: float | None = None
    speaker_ok = True
    if speaker.get("centroid") and vector:
        speaker_score = round(cosine(vector, speaker["centroid"]), 4)
        if enforce:
            threshold = float(speaker.get("threshold", speaker_threshold()))
            speaker_ok = speaker_score >= threshold
    elif speaker.get("centroid") and enforce:
        # The enrolled record has a voiceprint but this attempt brought none.
        speaker_ok = False

    ok = bool(passphrase_ok and speaker_ok)

    if ok:
        if count or locked_until:
            data["voice_fail"] = {"count": 0, "last": 0, "locked_until": 0}
            try:
                _save_store(data)
            except OSError:
                pass
        return {
            "ok": True,
            "code": "verified",
            "error": None,
            "passphrase_ok": True,
            "speaker_score": speaker_score,
        }

    count += 1
    locked_until = 0.0
    max_attempts = _max_attempts()
    if count >= max_attempts:
        multiplier = min(10, max(1, count // max_attempts))
        locked_until = now + min(300, 30 * multiplier)
    data["voice_fail"] = {"count": count, "last": int(now), "locked_until": locked_until}
    try:
        _save_store(data)
    except OSError:
        pass

    remaining = max(0, int(round(locked_until - now))) if locked_until else 0
    attempts_left = max(0, max_attempts - (count % max_attempts))
    if remaining:
        error = f"Too many attempts. Wait {remaining} seconds."
    else:
        error = f"Voice check failed. {attempts_left} attempt(s) left."
    return {
        "ok": False,
        "code": "locked" if remaining else "mismatch",
        "error": error,
        "remaining": remaining,
        "attempts_left": attempts_left,
        "passphrase_ok": passphrase_ok,
        "speaker_score": speaker_score,
    }


def voice_reset() -> dict[str, Any]:
    """Remove the voice password, speaker centroid and failure state."""
    data = _load_store()
    data["voice"] = None
    data["voice_fail"] = {"count": 0, "last": 0, "locked_until": 0}
    try:
        _save_store(data)
    except OSError:
        return {"ok": False, "code": "save_failed", "error": "Voice data could not be reset."}
    return {"ok": True, "enrolled": False}


# ── Overall status ─────────────────────────────────────────────────────────

def status(face: bool = True) -> dict[str, Any]:
    """Public status. Never returns hashes, vectors or transcripts."""
    voice = voice_status()
    return {
        "face": face_status() if face else {"available": None, "code": "skipped"},
        "voice": voice,
        "speaker_model": speaker_available(),
        "speaker_threshold": speaker_threshold(),
        "require_speaker": require_speaker(),
        "store": str(_store_path()),
        "exe": str(maya_exe() or DEFAULT_EXE),
    }
