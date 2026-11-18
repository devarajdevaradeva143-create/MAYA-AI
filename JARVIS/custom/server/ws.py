"""Helpers shared by the HTTP and WebSocket chat endpoints."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

from custom.server.contracts import ServerServices
from custom.server.errors import ApiError
from custom.server.models import ChatRequest


def build_engine_messages(services: ServerServices, body: ChatRequest) -> list[dict[str, str]]:
    """Prepend the server-side persona prompt; client never sends system role."""
    messages: list[dict[str, str]] = []
    prompt = (services.persona_prompts or {}).get(body.persona, "")
    if prompt:
        messages.append({"role": "system", "content": prompt})
    messages.extend(
        {"role": message.role, "content": message.content}
        for message in body.messages
    )
    return messages


def pull_chunk(generator: Iterator[str]) -> str | None:
    """`next()` wrapper so StopIteration never crosses the thread boundary."""
    try:
        return next(generator)
    except StopIteration:
        return None


def engine_error(exc: Exception) -> ApiError:
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, TimeoutError):
        return ApiError(3002, "Engine timeout")
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return ApiError(3002, "Engine timeout")
    return ApiError(3001, "Engine unavailable")


def error_frame(code: int, message: str) -> dict[str, Any]:
    return {"type": "error", "code": code, "message": message}


def now_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))
