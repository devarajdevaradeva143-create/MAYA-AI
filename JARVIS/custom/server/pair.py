"""PIN and QR pairing sessions.

PINs and QR tokens live in memory only. QR tokens are stored as hashes and
are single-use. Wrong PINs are counted per client/device with a lockout.
"""

from __future__ import annotations

import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

from custom.server.auth import DeviceRecord, TokenStore, hash_token, new_token
from custom.server.contracts import ServerSettings
from custom.server.errors import ApiError

PIN_LENGTH = 6


@dataclass
class _PinSession:
    pin: str
    expires_at: float
    attempts: int = 0


@dataclass
class _QrSession:
    token_hash: str
    expires_at: float


@dataclass
class IssuedPair:
    token: str
    expires_at: int
    record: DeviceRecord


class PairingManager:
    def __init__(
        self,
        settings: ServerSettings,
        tokens: TokenStore,
        clock=time.time,
    ) -> None:
        self.settings = settings
        self.tokens = tokens
        self._clock = clock
        self._lock = threading.RLock()
        self._pin: _PinSession | None = None
        self._qr: _QrSession | None = None
        self._lockouts: dict[str, float] = {}

    # -- creation -----------------------------------------------------

    def generate_pin(self) -> tuple[str, int]:
        """Create a fresh 6-digit PIN; returns (pin, expires_at epoch s)."""
        with self._lock:
            now = self._clock()
            pin = f"{secrets.randbelow(10 ** PIN_LENGTH):0{PIN_LENGTH}d}"
            expires = now + self.settings.pin_ttl_seconds
            self._pin = _PinSession(pin=pin, expires_at=expires)
            return pin, int(expires)

    def generate_qr(self, host: str, port: int, laptop_name: str) -> dict[str, Any]:
        """Create a QR payload; the token is stored hashed (single use)."""
        with self._lock:
            now = self._clock()
            token = secrets.token_hex(32)
            self._qr = _QrSession(
                token_hash=hash_token(token),
                expires_at=now + self.settings.qr_ttl_seconds,
            )
            return {
                "v": 1,
                "h": host,
                "p": port,
                "t": token,
                "n": laptop_name,
            }

    def pin_expires_at(self) -> int | None:
        with self._lock:
            if self._pin is None:
                return None
            return int(self._pin.expires_at)

    def qr_expires_at(self) -> int | None:
        with self._lock:
            if self._qr is None:
                return None
            return int(self._qr.expires_at)

    # -- claims -------------------------------------------------------

    def claim_pin(
        self,
        pin: str,
        *,
        device_id: str,
        device_name: str,
        app_version: str,
        client_key: str,
    ) -> IssuedPair:
        with self._lock:
            now = self._clock()
            locked_until = self._lockouts.get(client_key, 0.0)
            if now < locked_until:
                raise ApiError(1005, "Too many attempts. Try again later.")

            session = self._pin
            if session is None or now >= session.expires_at:
                self._pin = None
                raise ApiError(1004, "Pairing code expired")

            if not hmac.compare_digest(session.pin, pin):
                session.attempts += 1
                if session.attempts >= self.settings.max_pair_attempts:
                    self._lockouts[client_key] = (
                        now + self.settings.lockout_minutes * 60
                    )
                    self._pin = None
                    raise ApiError(1005, "Too many attempts. Try again later.")
                raise ApiError(1003, "Invalid PIN")

            self._pin = None
            return self._issue(
                device_id=device_id,
                device_name=device_name,
                app_version=app_version,
                now=now,
            )

    def claim_qr(
        self,
        qr_token: str,
        *,
        device_id: str,
        device_name: str,
        app_version: str,
    ) -> IssuedPair:
        with self._lock:
            now = self._clock()
            session = self._qr
            if session is None or now >= session.expires_at:
                self._qr = None
                raise ApiError(1004, "QR code expired or already used")
            if not hmac.compare_digest(session.token_hash, hash_token(qr_token)):
                raise ApiError(1004, "QR code expired or already used")

            self._qr = None
            return self._issue(
                device_id=device_id,
                device_name=device_name,
                app_version=app_version,
                now=now,
            )

    # -- internals ----------------------------------------------------

    def _issue(
        self,
        *,
        device_id: str,
        device_name: str,
        app_version: str,
        now: float,
    ) -> IssuedPair:
        existing = self.tokens.get(device_id)
        if (existing is None or existing.revoked) and (
            self.tokens.count_active() >= self.settings.max_devices
        ):
            raise ApiError(4002, "Device limit reached")

        token = new_token()
        expires_at = int(now) + self.settings.token_ttl_hours * 3600
        record = self.tokens.add(
            device_id=device_id,
            name=device_name,
            token_hash=hash_token(token),
            expires_at=expires_at,
            app_version=app_version,
            now=now,
        )
        return IssuedPair(token=token, expires_at=expires_at, record=record)

    def refresh(self, record: DeviceRecord, now: float | None = None) -> IssuedPair:
        """Issue a fresh token for an already authenticated device."""
        stamp = now if now is not None else self._clock()
        token = new_token()
        expires_at = int(stamp) + self.settings.token_ttl_hours * 3600
        updated = self.tokens.update_token(
            record.device_id,
            hash_token(token),
            expires_at,
            now=stamp,
        )
        return IssuedPair(token=token, expires_at=expires_at, record=updated)
