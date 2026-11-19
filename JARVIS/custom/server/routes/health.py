"""GET /health — unauthenticated discovery endpoint."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from custom.server.models import API_VERSION, HealthResponse

router = APIRouter(tags=["health"])

BASE_CAPABILITIES = [
    "chat",
    "chat_stream",
    "voice_stt",
    "voice_tts",
    "pc_control",
    "file_transfer",
    "wake",
    "monitor",
]


def _available(port: object) -> bool:
    check = getattr(port, "available", None)
    return True if check is None else bool(check())


def capabilities_for(services) -> list[str]:  # noqa: ANN001 - ServerServices
    caps = list(BASE_CAPABILITIES)
    if services.screen is not None and _available(services.screen):
        caps.append("screen")
    if services.input is not None and _available(services.input):
        caps.append("remote_input")
    if services.hybrid is not None:
        caps.append("hybrid")
    if services.settings.wan_enabled:
        caps.append("wan")
    return caps


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    state = request.app.state
    services = state.services
    try:
        paired = state.tokens.count_active()
    except Exception:  # noqa: BLE001 - health must never fail on the store
        paired = 0
    return HealthResponse(
        status="ok",
        app="maya-laptop",
        version=services.version,
        api=API_VERSION,
        platform=services.platform,
        model=services.model,
        engine=services.engine_name,
        capabilities=capabilities_for(services),
        paired_devices=paired,
        uptime_s=max(0, int(time.time() - services.started_at)),
        wan_host=services.settings.wan_relay_url or None,
    )
