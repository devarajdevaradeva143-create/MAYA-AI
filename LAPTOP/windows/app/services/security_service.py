"""Thin adapter over JARVIS/custom SecurityManager (PBKDF2 PIN store).

Never stores a PIN in settings.yaml. PIN lives in the security store
(MAYA AI/memory/offline/security.json) hashed with PBKDF2-SHA256 + salt.
"""

from __future__ import annotations

from typing import Any

try:
    from custom.tools.security import SecurityManager
except Exception:  # pragma: no cover - defensive
    SecurityManager = None  # type: ignore[assignment,misc]

try:
    from custom.tools import biometrics as _biometrics
except Exception:  # pragma: no cover
    _biometrics = None  # type: ignore[assignment]


def _safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - UI must not crash
        return {"error": str(exc), "ok": False}


class SecurityService:
    """UI-facing wrapper. Keeps the manager injectable for tests."""

    def __init__(self, manager: Any = None) -> None:
        self._manager = manager if manager is not None else (
            SecurityManager() if SecurityManager is not None else None
        )

    # -- PIN -----------------------------------------------------------
    def pin_is_set(self) -> bool:
        if self._manager is None:
            return False
        return bool(self._manager.is_locked())

    def session_locked(self) -> bool:
        if self._manager is None:
            return False
        return bool(self._manager.is_session_locked())

    def set_pin(self, pin: str, old_pin: str | None = None) -> str:
        if self._manager is None:
            return "Security manager unavailable."
        return str(self._manager.set_pin(pin, old_pin))

    def verify_pin(self, pin: str) -> str:
        if self._manager is None:
            return "Security manager unavailable."
        return str(self._manager.verify_pin(pin))

    def lock(self) -> str:
        if self._manager is None:
            return "Security manager unavailable."
        return str(self._manager.lock())

    def unlock(self, method: str = "pin") -> str:
        if self._manager is None:
            return "Security manager unavailable."
        return str(self._manager.unlock(method))

    def status(self) -> dict[str, Any]:
        if self._manager is None:
            return {}
        try:
            return self._manager.status()
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def alerts(self) -> list[dict[str, Any]]:
        if self._manager is None:
            return []
        try:
            return list(self._manager.get_unauthorized_alerts() or [])
        except Exception:  # noqa: BLE001
            return []

    # -- biometrics (fail-soft) ---------------------------------------
    def face_available(self) -> bool:
        st = self.face_status()
        return bool(st.get("available")) if isinstance(st, dict) else False

    def face_status(self) -> dict[str, Any]:
        if _biometrics is None:
            return {}
        res = _safe_call(_biometrics.face_status)
        return res if isinstance(res, dict) else {}

    def face_verify(self) -> dict[str, Any]:
        if _biometrics is None:
            return {"ok": False, "error": "biometrics unavailable"}
        res = _safe_call(_biometrics.face_verify)
        return res if isinstance(res, dict) else {"ok": False, "error": str(res)}

    def open_face_settings(self) -> dict[str, Any]:
        if _biometrics is None:
            return {"ok": False, "error": "biometrics unavailable"}
        res = _safe_call(_biometrics.open_face_settings)
        return res if isinstance(res, dict) else {"ok": False, "error": str(res)}

    def voice_status(self) -> dict[str, Any]:
        if _biometrics is None:
            return {}
        res = _safe_call(_biometrics.voice_status)
        return res if isinstance(res, dict) else {}

    def voice_reset(self) -> dict[str, Any]:
        if _biometrics is None:
            return {"ok": False, "error": "biometrics unavailable"}
        res = _safe_call(_biometrics.voice_reset)
        return res if isinstance(res, dict) else {"ok": False, "error": str(res)}
