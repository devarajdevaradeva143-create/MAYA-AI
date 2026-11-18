"""Wake-listener endpoints."""

from __future__ import annotations

import time

from fastapi import APIRouter, Request

from custom.server.auth import DeviceDep
from custom.server.models import (
    WakeListenRequest,
    WakeListenResponse,
    WakeStatusResponse,
    WakeStopResponse,
)

router = APIRouter(prefix="/wake", tags=["wake"])


@router.get("/status", response_model=WakeStatusResponse)
def wake_status(
    request: Request,
    device: DeviceDep,
) -> WakeStatusResponse:
    del device
    data = request.app.state.services.wake.status()
    return WakeStatusResponse(
        listening=bool(data.get("listening", False)),
        clap=bool(data.get("clap", True)),
        name=bool(data.get("name", True)),
    )


@router.post("/listen", response_model=WakeListenResponse)
def wake_listen(
    body: WakeListenRequest,
    request: Request,
    device: DeviceDep,
) -> WakeListenResponse:
    state = request.app.state
    state.limiter.hit(f"wake:{device.device_id}", 5, 60)
    expires_at = state.services.wake.listen(body.seconds)
    return WakeListenResponse(
        listening=True,
        expires_at=int(expires_at if expires_at else time.time() + body.seconds),
    )


@router.post("/stop", response_model=WakeStopResponse)
def wake_stop(
    request: Request,
    device: DeviceDep,
) -> WakeStopResponse:
    del device
    request.app.state.services.wake.stop()
    return WakeStopResponse(listening=False)
