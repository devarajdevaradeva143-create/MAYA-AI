"""Maya AI security tools — PIN lock, local only.

Provides PIN-based lock/unlock with a locally salted hash.
Nothing is transmitted — all data stays on the laptop.

Per AGENTS.md: biometrics local only, personal details safe.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any

from ..config import PROJECT_ROOT, load_settings


ENV_SECURITY_STORE = "MAYA_SECURITY_STORE"
DEFAULT_OFFLINE_MEMORY = "memory/offline"
SECURITY_STORE_FILENAME = "security.json"


# ── Security store path ─────────────────────────────────────────────────────

def _security_store_path() -> Path:
    """Resolve the security JSON path from settings.yaml (offline only)."""
    override = os.environ.get(ENV_SECURITY_STORE, "").strip()
    if override:
        return Path(override).expanduser()

    settings = load_settings()
    memory = settings.get("memory", {}) if isinstance(settings, dict) else {}
    offline = memory.get("offline", DEFAULT_OFFLINE_MEMORY)
    dir_path = Path(offline)
    if not dir_path.is_absolute():
        dir_path = PROJECT_ROOT / "MAYA AI" / dir_path
    return dir_path / SECURITY_STORE_FILENAME


# ── PIN hashing ─────────────────────────────────────────────────────────────

def _salted_hash(pin: str, salt: str) -> str:
    """Return a PBKDF2-HMAC-SHA256 digest of PIN + salt.

    PBKDF2 (200k iterations) is used instead of a plain SHA-256 so that a
    stolen ``security.json`` cannot be brute-forced cheaply. Everything is
    local — nothing is transmitted.
    """
    return hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("utf-8"),
        salt.encode("utf-8"),
        200_000,
    ).hex()


def _generate_salt() -> str:
    """Generate a random 16-byte hex salt."""
    return os.urandom(16).hex()


# ── Security manager ────────────────────────────────────────────────────────

class SecurityManager:
    """PIN-based lock/unlock with local salted hash storage.

    All data lives in ``MAYA AI/memory/offline/security.json`` — never online,
    never the cloud.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else _security_store_path()
        self._data: dict[str, Any] = self._load()
        self._failed_attempts = int(self._data.get("failed_attempts", 0) or 0)
        self._lockout_until = float(self._data.get("lockout_until", 0) or 0)

    # ── Internal persistence ──────────────────────────────────────────
    @staticmethod
    def _defaults() -> dict[str, Any]:
        return {
            "pin_hash": None,
            "salt": None,
            "failed_attempts": 0,
            "lockout_until": 0,
            "unauthorized_alerts": [],
            "backup_unlock_code": None,
            "backup_unlock_salt": None,
        }

    def _load(self) -> dict[str, Any]:
        """Load security data from disk. Missing/corrupt -> defaults.

        A store written before session state existed is treated as locked
        when a PIN is set, so an upgrade never silently leaves Maya open.
        """
        import json

        data: dict[str, Any] = {}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        except (FileNotFoundError, OSError, ValueError, TypeError):
            data = {}

        merged = self._defaults()
        merged.update(data)
        if "session_locked" not in data:
            merged["session_locked"] = bool(merged.get("pin_hash"))
        merged.setdefault("last_unlock", None)
        return merged

    def reload(self) -> None:
        """Reload state from disk (the CLI may share one process in tests)."""
        self._data = self._load()
        self._failed_attempts = int(self._data.get("failed_attempts", 0) or 0)
        self._lockout_until = float(self._data.get("lockout_until", 0) or 0)

    def _save(self) -> None:
        """Persist security data to disk atomically."""
        import json

        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self._path)

    # ── PIN setup / verify ────────────────────────────────────────────

    def is_locked(self) -> bool:
        """Return True if a PIN has been set (security is active)."""
        return self._data.get("pin_hash") is not None

    def set_pin(self, pin: str, old_pin: str | None = None) -> str:
        """Set the PIN. Generates a new salt and stores the hash.

        If a PIN is already set, the current PIN must be supplied as
        ``old_pin`` — a stranger cannot silently replace it.
        """
        if not pin or len(pin) < 4:
            return "PIN must be at least 4 digits."

        if self.is_locked():
            if not old_pin:
                return "PIN already set. Give the current PIN to change it."
            salt = self._data.get("salt")
            pin_hash = self._data.get("pin_hash")
            if not salt or _salted_hash(old_pin, salt) != pin_hash:
                self.record_unauthorized("Wrong PIN while changing PIN")
                return "Current PIN is wrong."

        salt = _generate_salt()
        self._data["pin_hash"] = _salted_hash(pin, salt)
        self._data["salt"] = salt
        self._data["failed_attempts"] = 0
        self._data["lockout_until"] = 0
        self._data["session_locked"] = True
        self._data["last_unlock"] = None
        self._failed_attempts = 0
        self._save()
        return "PIN set. Maya is now locked — you'll need it to start."

    def verify_pin(self, pin: str) -> str:
        """Verify a PIN. Returns success or failure message.

        On success, resets failed attempts and unlocks the session.
        On failure, increments failed attempts and may trigger lockout.
        """
        if not self.is_locked():
            return "No PIN set. Use 'set-pin' first."

        # Check lockout. Once it has expired the counter starts fresh.
        lockout_until = float(self._data.get("lockout_until", 0) or 0)
        now = time.time()
        if lockout_until and now < lockout_until:
            remaining = int(lockout_until - now)
            return f"Locked out. Try again in {remaining} seconds."
        if lockout_until and now >= lockout_until:
            self._failed_attempts = 0
            self._data["failed_attempts"] = 0
            self._data["lockout_until"] = 0

        salt = self._data.get("salt")
        pin_hash = self._data.get("pin_hash")
        if not salt or not pin_hash:
            return "Security not initialized. Set a PIN first."

        if _salted_hash(pin, salt) == pin_hash:
            self._failed_attempts = 0
            self._data["failed_attempts"] = 0
            self._data["lockout_until"] = 0
            self._mark_unlocked("pin")
            self._save()
            return "Unlocked. Maya is ready."
        else:
            self._failed_attempts += 1
            self._data["failed_attempts"] = self._failed_attempts
            max_attempts = 5
            if self._failed_attempts >= max_attempts:
                self._data["lockout_until"] = time.time() + 300  # 5 min lockout
                self._save()
                return (
                    f"Wrong PIN. {max_attempts} failed attempts — "
                    f"locked out for 5 minutes."
                )
            self._save()
            remaining = max_attempts - self._failed_attempts
            return f"Wrong PIN. {remaining} attempt(s) remaining."

    # ── Session lock state ────────────────────────────────────────────

    def is_session_locked(self) -> bool:
        """True when Maya is waiting for an unlock.

        A store with no PIN set is never treated as locked — there would be
        no way to unlock it.
        """
        if not self.is_locked():
            return False
        return bool(self._data.get("session_locked", True))

    def _mark_unlocked(self, method: str) -> None:
        self._data["session_locked"] = False
        self._data["last_unlock"] = {
            "method": method,
            "time": int(time.time()),
        }

    def lock(self) -> str:
        """Lock the current session. Requires a PIN so it can be reopened."""
        if not self.is_locked():
            return "No PIN set. Use 'maya security set-pin <pin>' first."
        self._data["session_locked"] = True
        self._save()
        return "Maya is locked. Unlock with: maya security unlock <pin>"

    def unlock(self, method: str = "pin") -> str:
        """Mark the session unlocked through a verified factor.

        Only call this after the factor has actually been verified (PIN,
        Windows Hello, voice or the backup code).
        """
        if not self.is_locked():
            return "No PIN set. Use 'maya security set-pin <pin>' first."
        if self.is_session_locked() is False and self._data.get("last_unlock"):
            # Already open — keep the newest method, still refresh the time.
            self._mark_unlocked(method)
            self._save()
            return f"Maya is already unlocked ({method})."

        lockout_until = float(self._data.get("lockout_until", 0) or 0)
        if lockout_until and time.time() < lockout_until:
            remaining = int(lockout_until - time.time())
            return f"Locked out. Try again in {remaining} seconds."

        self._mark_unlocked(method)
        self._save()
        return f"Unlocked via {method}. Maya is ready."

    # ── Unauthorized access tracking ──────────────────────────────────

    def record_unauthorized(self, detail: str) -> None:
        """Record an unauthorized access attempt (local audit log)."""
        self._data.setdefault("unauthorized_alerts", []).append(
            {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "detail": detail,
            }
        )
        # Keep only the last 50 alerts
        alerts = self._data["unauthorized_alerts"]
        if len(alerts) > 50:
            self._data["unauthorized_alerts"] = alerts[-50:]
        self._save()

    def get_unauthorized_alerts(self) -> list[dict[str, Any]]:
        """Return the list of recorded unauthorized access attempts."""
        return list(self._data.get("unauthorized_alerts", []))

    # ── Backup unlock ─────────────────────────────────────────────────

    def set_backup_unlock_code(self, code: str) -> str:
        """Set a backup unlock code (emergency access if PIN forgotten)."""
        if not code or len(code) < 6:
            return "Backup code must be at least 6 characters."
        salt = _generate_salt()
        self._data["backup_unlock_code"] = _salted_hash(code, salt)
        self._data["backup_unlock_salt"] = salt
        self._save()
        return "Backup unlock code set."

    def verify_backup_unlock(self, code: str) -> str:
        """Verify the backup unlock code."""
        stored = self._data.get("backup_unlock_code")
        salt = self._data.get("backup_unlock_salt")
        if not stored or not salt:
            return "No backup unlock code set."
        if _salted_hash(code, salt) == stored:
            self._failed_attempts = 0
            self._data["failed_attempts"] = 0
            self._data["lockout_until"] = 0
            self._mark_unlocked("backup_code")
            self._save()
            return "Backup unlock successful. Maya is ready."
        return "Invalid backup unlock code."

    # ── Status ────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        """Return security status (no secrets exposed)."""
        lockout_until = self._data.get("lockout_until", 0)
        locked_out = bool(lockout_until and time.time() < lockout_until)
        last_unlock = self._data.get("last_unlock")
        return {
            "pin_set": self.is_locked(),
            "locked": self.is_session_locked(),
            "session_locked": self.is_session_locked(),
            "last_unlock": dict(last_unlock) if isinstance(last_unlock, dict) else None,
            "failed_attempts": self._data.get("failed_attempts", 0),
            "locked_out": locked_out,
            "backup_code_set": bool(self._data.get("backup_unlock_code")),
            "unauthorized_alerts": len(self._data.get("unauthorized_alerts", [])),
        }


# Module-level default security instance (offline JSON only, no cloud).
security = SecurityManager()
