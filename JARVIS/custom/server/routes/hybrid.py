"""HYBRID mode control bus endpoints (contract 9B).

The laptop-side ``HybridController`` always lets the user win: takeover
cancels/pauses AI work, and AI cannot acquire control while the user holds it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from custom.server.auth import DeviceDep
from custom.server.errors import ApiError

router = APIRouter(prefix="/hybrid", tags=["hybrid"])

HYBRID_RATE_LIMIT = 120


def _adapter(request: Request) -> Any:
    adapter = request.app.state.services.hybrid
    if adapter is None:
        raise ApiError(3001, "Hybrid mode unavailable")
    return adapter


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        data = to_dict()
        return dict(data) if isinstance(data, dict) else {}
    return {}


def _snapshot(request: Request) -> dict[str, Any]:
    adapter = _adapter(request)
    try:
        data = _as_dict(adapter.status())
        tasks = [
            _as_dict(task)
            for task in list(adapter.list_tasks())[-20:]
        ]
    except Exception as exc:  # noqa: BLE001 - never leak internals
        raise ApiError(5000, "Hybrid status failed") from exc
    data["tasks"] = tasks
    return data


@router.get("/status")
def hybrid_status(request: Request, device: DeviceDep) -> dict[str, Any]:
    request.app.state.limiter.hit(f"hybrid:{device.device_id}", HYBRID_RATE_LIMIT, 60)
    return _snapshot(request)


@router.post("/takeover")
def hybrid_takeover(request: Request, device: DeviceDep) -> dict[str, Any]:
    request.app.state.limiter.hit(f"hybrid:{device.device_id}", HYBRID_RATE_LIMIT, 60)
    adapter = _adapter(request)
    try:
        adapter.takeover()
    except Exception as exc:  # noqa: BLE001 - never leak internals
        raise ApiError(5000, "Takeover failed") from exc
    return {"status": "done", **_snapshot(request)}


@router.post("/release")
def hybrid_release(request: Request, device: DeviceDep) -> dict[str, Any]:
    request.app.state.limiter.hit(f"hybrid:{device.device_id}", HYBRID_RATE_LIMIT, 60)
    adapter = _adapter(request)
    try:
        adapter.release()
    except Exception as exc:  # noqa: BLE001 - never leak internals
        raise ApiError(5000, "Release failed") from exc
    return {"status": "done", **_snapshot(request)}
