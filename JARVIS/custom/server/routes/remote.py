"""Remote control + file transfer endpoints (contract 9A).

Every route except ``remote/start`` requires a live remote session created by
the owner's confirmation. Sessions are memory-only and device-bound.
"""

from __future__ import annotations

import mimetypes
import os
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Query, Request, Response
from starlette.responses import StreamingResponse

from custom.server import policy
from custom.server.auth import DeviceDep
from custom.server.errors import ApiError
from custom.server.models import (
    FileEntry,
    FileListResponse,
    FileRootsResponse,
    FileUploadResponse,
    RemoteInputRequest,
    RemoteInputResponse,
    RemoteStartRequest,
    RemoteStartResponse,
    RemoteStatusResponse,
    RemoteStopRequest,
    RemoteStopResponse,
)

router = APIRouter(prefix="/pc", tags=["remote"])

SCREEN_RATE_LIMIT = 120
INPUT_RATE_LIMIT = 600
FILE_RATE_LIMIT = 120
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
CHUNK = 64 * 1024

REMOTE_DESCRIPTION = "Allow remote screen and input from this phone?"


def _require_session(request: Request, token: str, device_id: str) -> int:
    remaining = request.app.state.remote.status(token, device_id)
    if remaining is None:
        raise ApiError(4002, "Remote session expired")
    return remaining


def _guard(request: Request, device_id: str, limit: int) -> None:
    request.app.state.limiter.hit(f"remote:{device_id}", limit, 60)


def _hit(request: Request, key: str, device_id: str, limit: int) -> None:
    request.app.state.limiter.hit(f"{key}:{device_id}", limit, 60)


@router.post(
    "/remote/start",
    response_model=RemoteStartResponse,
    response_model_exclude_none=True,
)
def remote_start(
    body: RemoteStartRequest,
    request: Request,
    device: DeviceDep,
) -> RemoteStartResponse:
    state = request.app.state
    services = state.services
    _guard(request, device.device_id, 20)

    if body.confirm_token:
        pending = state.confirm.pop(body.confirm_token, device.device_id)
        if pending.action != "remote.start":
            raise ApiError(4002, "Confirmation does not match this action")
        token, expires_in = state.remote.create(device.device_id)
        if services.hybrid is not None:
            try:
                services.hybrid.takeover()
            except Exception:  # noqa: BLE001 - control bus is best effort
                pass
        return RemoteStartResponse(
            status="done",
            session_token=token,
            expires_in=expires_in,
        )

    token, expires_in = state.confirm.create(
        device_id=device.device_id,
        action="remote.start",
        params={},
        description=REMOTE_DESCRIPTION,
    )
    return RemoteStartResponse(
        status="needs_confirmation",
        confirm_token=token,
        description=REMOTE_DESCRIPTION,
        expires_in=expires_in,
    )


@router.post(
    "/remote/stop",
    response_model=RemoteStopResponse,
    response_model_exclude_none=True,
)
def remote_stop(
    body: RemoteStopRequest,
    request: Request,
    device: DeviceDep,
) -> RemoteStopResponse:
    state = request.app.state
    stopped = state.remote.stop(body.session_token, device.device_id)
    if stopped and state.services.hybrid is not None:
        try:
            state.services.hybrid.release()
        except Exception:  # noqa: BLE001 - control bus is best effort
            pass
    return RemoteStopResponse()


@router.get(
    "/remote/status",
    response_model=RemoteStatusResponse,
    response_model_exclude_none=True,
)
def remote_status(
    request: Request,
    device: DeviceDep,
    session_token: str = Query(min_length=8, max_length=128),
) -> RemoteStatusResponse:
    remaining = request.app.state.remote.status(session_token, device.device_id)
    return RemoteStatusResponse(active=remaining is not None, expires_in=remaining or 0)


@router.get("/screen")
def pc_screen(
    request: Request,
    device: DeviceDep,
    session_token: str = Query(min_length=8, max_length=128),
    max_width: int = Query(default=1280, ge=320, le=1920),
    quality: int = Query(default=60, ge=30, le=85),
) -> Response:
    _require_session(request, session_token, device.device_id)
    _hit(request, "screen", device.device_id, SCREEN_RATE_LIMIT)
    screen = request.app.state.services.screen
    if screen is None:
        raise ApiError(3001, "Screen capture unavailable")
    try:
        frame = screen.capture(max_width=max_width, quality=quality)
    except Exception as exc:  # noqa: BLE001 - never leak internals
        raise ApiError(5000, "Screen capture failed") from exc
    return Response(
        content=frame.data,
        media_type=frame.media_type,
        headers={
            "Cache-Control": "no-store",
            "X-Maya-Frame": str(int(time.time() * 1000)),
            "X-Maya-Width": str(frame.width),
            "X-Maya-Height": str(frame.height),
        },
    )


@router.post(
    "/input",
    response_model=RemoteInputResponse,
    response_model_exclude_none=True,
)
def pc_input(
    body: RemoteInputRequest,
    request: Request,
    device: DeviceDep,
) -> RemoteInputResponse:
    _require_session(request, body.session_token, device.device_id)
    _hit(request, "input", device.device_id, INPUT_RATE_LIMIT)
    adapter = request.app.state.services.input
    if adapter is None:
        raise ApiError(3001, "Remote input unavailable")
    events = [event.model_dump(exclude_none=True) for event in body.events]
    try:
        applied = adapter.apply(events)
    except Exception as exc:  # noqa: BLE001 - never leak internals
        raise ApiError(5000, "Input failed") from exc
    return RemoteInputResponse(status="done", applied=int(applied))


@router.get(
    "/files/roots",
    response_model=FileRootsResponse,
    response_model_exclude_none=True,
)
def file_roots(
    request: Request,
    device: DeviceDep,
    session_token: str = Query(min_length=8, max_length=128),
) -> FileRootsResponse:
    _require_session(request, session_token, device.device_id)
    _hit(request, "files", device.device_id, FILE_RATE_LIMIT)
    roots = [
        str(root)
        for root in request.app.state.services.settings.allowed_roots
        if isinstance(root, str) and root.strip()
    ]
    return FileRootsResponse(roots=roots)


@router.get(
    "/files/list",
    response_model=FileListResponse,
    response_model_exclude_none=True,
)
def file_list(
    request: Request,
    device: DeviceDep,
    session_token: str = Query(min_length=8, max_length=128),
    path: str = Query(min_length=1, max_length=1024),
) -> FileListResponse:
    _require_session(request, session_token, device.device_id)
    _hit(request, "files", device.device_id, FILE_RATE_LIMIT)
    resolved = policy.resolve_path(
        path,
        request.app.state.services.settings.allowed_roots,
        must_exist=True,
    )
    if not resolved.is_dir():
        raise ApiError(2001, "Not a folder")
    entries: list[FileEntry] = []
    try:
        with os.scandir(resolved) as iterator:
            for entry in iterator:
                try:
                    is_dir = entry.is_dir()
                    size = entry.stat().st_size if not is_dir else None
                except OSError:
                    continue
                entries.append(
                    FileEntry(
                        name=entry.name,
                        path=entry.path,
                        is_dir=is_dir,
                        size=size,
                    )
                )
    except OSError as exc:
        raise ApiError(5000, "Could not read folder") from exc
    entries.sort(key=lambda item: (not item.is_dir, item.name.lower()))
    return FileListResponse(path=str(resolved), entries=entries)


@router.get("/files/download")
def file_download(
    request: Request,
    device: DeviceDep,
    session_token: str = Query(min_length=8, max_length=128),
    path: str = Query(min_length=1, max_length=1024),
) -> StreamingResponse:
    _require_session(request, session_token, device.device_id)
    _hit(request, "files", device.device_id, FILE_RATE_LIMIT)
    resolved = policy.resolve_path(
        path,
        request.app.state.services.settings.allowed_roots,
        must_exist=True,
    )
    if not resolved.is_file():
        raise ApiError(2001, "Not a file")
    try:
        size = resolved.stat().st_size
    except OSError as exc:
        raise ApiError(2004, "File not found") from exc
    if size > MAX_DOWNLOAD_BYTES:
        raise ApiError(2003, "File too large (50 MB max)")

    media_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"

    def chunks() -> Iterator[bytes]:
        with resolved.open("rb") as handle:
            while True:
                block = handle.read(CHUNK)
                if not block:
                    break
                yield block

    filename = quote(resolved.name, safe="")
    return StreamingResponse(
        chunks(),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "Content-Length": str(size),
            "Cache-Control": "no-store",
        },
    )


@router.put(
    "/files/upload",
    response_model=FileUploadResponse,
    response_model_exclude_none=True,
)
async def file_upload(
    request: Request,
    device: DeviceDep,
    session_token: str = Query(min_length=8, max_length=128),
    path: str = Query(min_length=1, max_length=1024),
) -> FileUploadResponse:
    _require_session(request, session_token, device.device_id)
    _hit(request, "files", device.device_id, FILE_RATE_LIMIT)
    roots = request.app.state.services.settings.allowed_roots
    target = policy.resolve_path(path, roots)
    if target.exists() and target.is_dir():
        raise ApiError(2001, "Target is a folder")
    parent = target.parent
    if not parent.is_dir():
        raise ApiError(2001, "Parent folder does not exist")

    temp = parent / f".{target.name}.maya-{uuid.uuid4().hex[:8]}.tmp"
    total = 0
    try:
        with temp.open("wb") as handle:
            async for block in request.stream():
                if not block:
                    continue
                total += len(block)
                if total > MAX_UPLOAD_BYTES:
                    raise ApiError(2003, "File too large (25 MB max)")
                handle.write(block)
        os.replace(temp, target)
    except ApiError:
        _unlink(temp)
        raise
    except OSError as exc:
        _unlink(temp)
        raise ApiError(5000, "Could not save file") from exc
    return FileUploadResponse(status="done", path=str(target), size=total)


def _unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
