"""Qt workers: streaming chat + engine health (never block the UI thread)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QThread, Signal

from app.services.chat_service import ChatService


class ChatStreamWorker(QThread):
    """Runs `ChatService.stream` off the UI thread; one worker at a time."""

    chunk = Signal(str)
    completed = Signal(str)
    cancelled = Signal()
    failed = Signal(str, str)  # error type, message

    def __init__(self, chat: ChatService, text: str, parent: Any = None) -> None:
        super().__init__(parent)
        self._chat = chat
        self._text = text

    def run(self) -> None:
        parts: list[str] = []
        try:
            for piece in self._chat.stream(self._text):
                parts.append(piece)
                self.chunk.emit(piece)
        except Exception as exc:  # noqa: BLE001 - surfaced to the page
            self.failed.emit(type(exc).__name__, str(exc))
            return

        if self._chat.was_cancelled:
            self.cancelled.emit()
        else:
            self.completed.emit("".join(parts).strip())

    def stop(self) -> None:
        self._chat.cancel()


class HealthWorker(QThread):
    """Checks the engine without freezing the chat page."""

    result = Signal(bool, str, str)  # ok, detail, model

    def __init__(self, engine: Any, parent: Any = None) -> None:
        super().__init__(parent)
        self._engine = engine

    def run(self) -> None:
        try:
            health = self._engine.health()
        except Exception as exc:  # noqa: BLE001 - health must never crash
            self.result.emit(False, str(exc), "")
            return

        if not isinstance(health, dict):
            self.result.emit(False, "Engine returned an unexpected reply", "")
            return

        ok = bool(health.get("ok", health.get("status") in {"ok", "healthy", "ready"}))
        models = [str(item) for item in health.get("models") or [] if str(item)]
        model = models[0] if models else str(getattr(self._engine, "model", "") or "")
        detail = "Engine ready" if ok else str(health.get("error") or "Engine unreachable")
        self.result.emit(ok, detail, model)
