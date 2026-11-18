"""Single-use confirm tokens for dangerous phone-requested actions."""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from custom.server.errors import ApiError

DEFAULT_TTL_SECONDS = 60


@dataclass
class PendingAction:
    device_id: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    expires_at: float = 0.0


class ConfirmStore:
    """Memory-only store. Server restart drops every pending action."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS, clock=time.time) -> None:
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._pending: dict[str, PendingAction] = {}
        self._lock = threading.RLock()

    def create(
        self,
        *,
        device_id: str,
        action: str,
        params: dict[str, Any],
        description: str,
    ) -> tuple[str, int]:
        token = "cf_" + secrets.token_urlsafe(24)
        pending = PendingAction(
            device_id=device_id,
            action=action,
            params=dict(params),
            description=description,
            expires_at=self._clock() + self.ttl_seconds,
        )
        with self._lock:
            self._pending[token] = pending
        return token, self.ttl_seconds

    def pop(self, token: str, device_id: str) -> PendingAction:
        with self._lock:
            pending = self._pending.pop(token, None)
        if pending is None:
            raise ApiError(4002, "Confirmation expired or already used")
        if pending.device_id != device_id:
            raise ApiError(4002, "Confirmation does not belong to this device")
        if pending.expires_at <= self._clock():
            raise ApiError(4002, "Confirmation expired")
        return pending

    def cancel(self, token: str, device_id: str) -> bool:
        with self._lock:
            pending = self._pending.pop(token, None)
        if pending is None:
            return False
        return pending.device_id == device_id
