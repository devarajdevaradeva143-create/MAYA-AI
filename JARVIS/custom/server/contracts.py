"""Port interfaces between the headless server and the desktop app.

`custom.server` must never import PySide6. The Windows app supplies adapters
that wrap the existing `custom.tools` functions.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EnginePort(Protocol):
    """Existing `custom.engine.bridge.EngineBridge` fits this shape."""

    def health(self) -> dict[str, Any]: ...

    def chat(self, messages: list[dict[str, str]]) -> str: ...

    def chat_stream(self, messages: list[dict[str, str]]) -> Iterator[str]: ...


@runtime_checkable
class VoicePort(Protocol):
    def status(self) -> dict[str, Any]: ...

    def transcribe(self, wav_path: Path, lang: str) -> dict[str, Any]: ...

    def synthesize_wav(
        self,
        text: str,
        *,
        engine: str = "auto",
        voice: str | None = None,
        lang: str = "en",
        speed: float = 1.0,
    ) -> Path: ...


@runtime_checkable
class PcPort(Protocol):
    def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]: ...


@runtime_checkable
class MonitorPort(Protocol):
    def snapshot(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ScreenFrame:
    """One captured frame plus its real pixel size (for phone-side mapping)."""

    data: bytes
    media_type: str
    width: int
    height: int


@runtime_checkable
class ScreenPort(Protocol):
    def capture(self, *, max_width: int = 1280, quality: int = 60) -> ScreenFrame: ...


@runtime_checkable
class InputPort(Protocol):
    def apply(self, events: list[dict[str, Any]]) -> int: ...


@runtime_checkable
class HybridPort(Protocol):
    def status(self) -> Any: ...

    def takeover(self) -> bool: ...

    def release(self) -> bool: ...

    def list_tasks(self) -> list[Any]: ...


@runtime_checkable
class TeacherPort(Protocol):
    """Port for AI English Teacher service.

    Implementations provide AI-generated lessons and persistent progress tracking.
    """

    def generate_lesson(self, topic: str, level: str, lesson_type: str = "mixed") -> dict[str, Any]:
        """Generate an AI lesson for the given topic, level, and type.

        Args:
            topic: One of "Vocabulary", "Grammar", "Pronunciation", "Idioms", "Conversation"
            level: One of "Beginner", "Intermediate", "Advanced"
            lesson_type: Type of lesson - "grammar", "vocab", "conversation", "mixed"

        Returns:
            Dict with keys: id, topic, level, type, prompt, answer, explanation, source, created
        """
        ...

    def check_answer(self, lesson_id: str, user_answer: str) -> dict[str, Any]:
        """Check a user's answer against the lesson's correct answer.

        Args:
            lesson_id: The ID of the lesson (from generate_lesson)
            user_answer: The user's submitted answer

        Returns:
            Dict with keys: correct (bool|None), feedback (str), score (int 0-100)
        """
        ...

    def get_progress(self, lesson_id: str | None = None) -> dict[str, Any]:
        """Get progress for a specific lesson or all lessons.

        Args:
            lesson_id: Optional specific lesson ID. If None, returns aggregate progress.

        Returns:
            If lesson_id: Dict with keys: lesson_id, completed, score, attempts, last_attempt_ts
            If None: Dict with aggregate stats (totals, streak, topics, recent, lessons list)
        """
        ...

    def mark_complete(self, lesson_id: str, score: int) -> dict[str, Any]:
        """Mark a lesson as completed with the given score.

        Args:
            lesson_id: The ID of the lesson
            score: Score 0-100

        Returns:
            Updated progress record for the lesson
        """
        ...

    def reset_progress(self) -> None:
        """Reset all progress data."""
        ...


@runtime_checkable
class WanPort(Protocol):
    """Internet/WAN remote transport (relay + TLS).

    Implementations connect to a relay, exchange framed messages, and provide
    an optional upgrade path from LAN to WAN. This is a skeleton contract.
    """

    def connect(self, relay_url: str, token: str) -> bool: ...

    def send(self, message: bytes) -> bool: ...

    def receive(self) -> bytes | None: ...

    def disconnect(self) -> None: ...

    def is_connected(self) -> bool: ...


@runtime_checkable
class WakePort(Protocol):
    def status(self) -> dict[str, Any]: ...

    def listen(self, seconds: int) -> float: ...

    def stop(self) -> None: ...

    def drain_events(self) -> list[dict[str, Any]]: ...


@dataclass(slots=True)
class ServerSettings:
    """Server-related values from `MAYA AI\\config\\settings.yaml`."""

    host: str = "0.0.0.0"
    port: int = 8420
    lan_only: bool = True
    token_ttl_hours: int = 720
    pin_ttl_seconds: int = 120
    qr_ttl_seconds: int = 120
    max_pair_attempts: int = 5
    lockout_minutes: int = 10
    max_devices: int = 8
    allowed_roots: list[str] = field(default_factory=list)
    enabled: bool = True
    wan_enabled: bool = False
    wan_relay_url: str = ""
    wan_cert_path: str = ""
    wan_key_path: str = ""
    wan_mode: str = "lan"
    # Stable host advertised in /health (e.g. a Tailscale IP). Falls back to
    # wan_relay_url when empty so older configs keep working.
    wan_host: str = ""


@dataclass
class ServerServices:
    """Everything the routes need; built by the desktop app (or tests)."""

    engine: EnginePort
    voice: VoicePort
    pc: PcPort
    monitor: MonitorPort
    wake: WakePort
    teacher: TeacherPort | None = None
    settings: ServerSettings = field(default_factory=ServerSettings)
    laptop_name: str = "Maya-Laptop"
    host: str = ""
    version: str = "0.1.0"
    platform: str = field(default_factory=lambda: sys.platform)
    model: str = "qwen3-3b"
    engine_name: str = "lemonade"
    persona_prompts: dict[str, str] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)
    screen: ScreenPort | None = None
    input: InputPort | None = None
    hybrid: HybridPort | None = None
    wan: WanPort | None = None
