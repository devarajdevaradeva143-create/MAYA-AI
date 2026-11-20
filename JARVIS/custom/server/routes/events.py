"""WS /ws/events — live monitor status + wake/notification events."""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from custom.server.auth import authenticate_websocket
from custom.server.errors import ApiError

router = APIRouter(tags=["events"])

MAX_EVENT_SOCKETS = 2
STATUS_INTERVAL_S = 2.0
PING_INTERVAL_S = 25.0
POLL_INTERVAL_S = 0.25


def _build_phone_stats(devices: list) -> list[dict]:
    """Extract phone stats from active paired devices."""
    phone_stats = []
    for d in devices:
        if d.phone_battery_percent is not None or d.phone_storage_used_percent is not None \
           or d.phone_ram_used_percent is not None or d.phone_uptime_hours is not None:
            phone_stats.append({
                "device_id": d.device_id,
                "name": d.name,
                "battery_percent": d.phone_battery_percent,
                "storage_used_percent": d.phone_storage_used_percent,
                "ram_used_percent": d.phone_ram_used_percent,
                "uptime_hours": d.phone_uptime_hours,
                "updated": d.phone_stats_updated,
            })
    return phone_stats


@router.websocket("/ws/events")
async def events_socket(websocket: WebSocket) -> None:
    try:
        authenticate_websocket(websocket)
    except ApiError:
        await websocket.close(code=4401)
        return

    state = websocket.app.state
    async with state.events_lock:
        if state.events_count >= MAX_EVENT_SOCKETS:
            await websocket.close(code=4429)
            return
        state.events_count += 1

    await websocket.accept()
    stop = asyncio.Event()

    async def _receiver() -> None:
        try:
            while True:
                await websocket.receive_json()
        except (WebSocketDisconnect, RuntimeError, ValueError):
            stop.set()

    receiver = asyncio.create_task(_receiver())
    last_status = 0.0
    last_ping = time.monotonic()
    try:
        while not stop.is_set():
            now = time.monotonic()
            if now - last_status >= STATUS_INTERVAL_S:
                try:
                    snapshot = await asyncio.to_thread(state.services.monitor.snapshot)
                    # Include paired phone stats
                    phone_stats = _build_phone_stats(state.tokens.list_active())
                    if phone_stats:
                        snapshot["phone_devices"] = phone_stats
                    await websocket.send_json({"type": "status", "data": snapshot})
                except Exception:  # noqa: BLE001 - socket or monitor failed
                    break
                last_status = now

            try:
                wake_events = state.services.wake.drain_events()
            except Exception:  # noqa: BLE001 - wake service is best effort
                wake_events = []
            for event in wake_events:
                await websocket.send_json(event)

            if now - last_ping >= PING_INTERVAL_S:
                await websocket.send_json({"type": "ping", "ts": int(time.time())})
                last_ping = now

            await asyncio.sleep(POLL_INTERVAL_S)
    except Exception:  # noqa: BLE001 - client disconnected
        pass
    finally:
        stop.set()
        receiver.cancel()
        async with state.events_lock:
            state.events_count = max(0, state.events_count - 1)
        try:
            await websocket.close()
        except RuntimeError:
            pass
