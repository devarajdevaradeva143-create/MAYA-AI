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


@dataclass
class ServerServices:
    """Everything the routes need; built by the desktop app (or tests)."""

    engine: EnginePort
    voice: VoicePort
    pc: PcPort
    monitor: MonitorPort
    wake: WakePort
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
