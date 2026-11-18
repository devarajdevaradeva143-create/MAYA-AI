"""Pairing endpoints: PIN claim, QR claim, refresh, device list, revoke."""

from __future__ import annotations

from fastapi import APIRouter, Request

from custom.server.auth import DeviceDep, client_ip
from custom.server.errors import ApiError
from custom.server.models import (
    API_VERSION,
    DeviceInfo,
    DevicesResponse,
    PairClaimRequest,
    PairResponse,
    QrClaimRequest,
    RefreshRequest,
    RefreshResponse,
    RevokeResponse,
)

router = APIRouter(prefix="/pair", tags=["pair"])


def _pair_response(request: Request, issued) -> PairResponse:
    services = request.app.state.services
    host = services.host or request.url.hostname or ""
    return PairResponse(
        token=issued.token,
        expires_at=issued.expires_at,
        laptop_name=services.laptop_name,
        api=API_VERSION,
        host=host,
        port=services.settings.port,
    )


@router.post("/claim", response_model=PairResponse)
def claim_pin(body: PairClaimRequest, request: Request) -> PairResponse:
    state = request.app.state
    ip = client_ip(request)
    key = f"{ip}:{body.device_id}"
    state.limiter.hit(f"pair:{key}", 5, 600)
    issued = state.pairing.claim_pin(
        body.pin,
        device_id=body.device_id,
        device_name=body.device_name,
        app_version=body.app_version,
        client_key=key,
    )
    return _pair_response(request, issued)


@router.post("/qr/claim", response_model=PairResponse)
def claim_qr(body: QrClaimRequest, request: Request) -> PairResponse:
    state = request.app.state
    ip = client_ip(request)
    state.limiter.hit(f"pairqr:{ip}:{body.device_id}", 5, 600)
    issued = state.pairing.claim_qr(
        body.qr_token,
        device_id=body.device_id,
        device_name=body.device_name,
        app_version=body.app_version,
    )
    return _pair_response(request, issued)


@router.post("/refresh", response_model=RefreshResponse)
def refresh(
    body: RefreshRequest,
    request: Request,
    device: DeviceDep,
) -> RefreshResponse:
    if body.device_id != device.device_id:
        raise ApiError(4002, "Token belongs to another device")
    issued = request.app.state.pairing.refresh(device)
    return RefreshResponse(token=issued.token, expires_at=issued.expires_at)


@router.get("/devices", response_model=DevicesResponse)
def list_devices(
    request: Request,
    device: DeviceDep,
) -> DevicesResponse:
    devices = [
        DeviceInfo(
            device_id=record.device_id,
            name=record.name,
            paired_at=record.paired_at,
            last_seen=record.last_seen,
            current=record.device_id == device.device_id,
        )
        for record in request.app.state.tokens.list_active()
    ]
    return DevicesResponse(devices=devices)


@router.delete("/devices/{device_id}", response_model=RevokeResponse)
def revoke_device(
    device_id: str,
    request: Request,
    device: DeviceDep,
) -> RevokeResponse:
    request.app.state.tokens.revoke(device_id)
    return RevokeResponse(revoked=True)
