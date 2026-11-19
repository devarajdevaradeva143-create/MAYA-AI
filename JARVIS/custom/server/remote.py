"""Short-lived remote-control sessions (screen + input + files).

A session is created only after the phone owner confirms ``remote.start`` and
is bound to one paired device. It expires after ``ttl_seconds`` of inactivity.
Memory-only by design: a server restart always drops control.
"""

from __future__ import annotations

import secrets
import threading
import time

DEFAULT_TTL_SECONDS = 300


class RemoteSessionStore:
    """One active remote session overall, sliding expiry."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS, clock=time.time) -> None:
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._sessions: dict[str, tuple[str, float]] = {}  # token -> (device_id, expires)
        self._lock = threading.RLock()

    def create(self, device_id: str) -> tuple[str, int]:
        """New session token; any older session (any device) is dropped."""
        token = "s_" + secrets.token_urlsafe(32)
        expires = self._clock() + self.ttl_seconds
        with self._lock:
            self._sessions.clear()
            self._sessions[token] = (device_id, expires)
        return token, self.ttl_seconds

    def status(self, token: str, device_id: str) -> int | None:
        """Remaining seconds, or None. Touching extends the sliding TTL."""
        if not token:
            return None
        now = self._clock()
        with self._lock:
            entry = self._sessions.get(token)
            if entry is None:
                return None
            owner, expires = entry
            if owner != device_id or expires <= now:
                self._sessions.pop(token, None)
                return None
            new_expires = now + self.ttl_seconds
            self._sessions[token] = (owner, new_expires)
            return max(1, int(new_expires - now))

    def stop(self, token: str, device_id: str) -> bool:
        with self._lock:
            entry = self._sessions.get(token)
            if entry is None or entry[0] != device_id:
                return False
            self._sessions.pop(token, None)
            return True

    def clear_device(self, device_id: str) -> int:
        with self._lock:
            return self._drop_device(device_id)

    def _drop_device(self, device_id: str) -> int:
        stale = [token for token, (owner, _) in self._sessions.items() if owner == device_id]
        for token in stale:
            self._sessions.pop(token, None)
        return len(stale)
