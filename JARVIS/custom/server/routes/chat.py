"""POST /chat and WS /ws/chat."""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, Request, WebSocket
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from custom.server.auth import DeviceDep, authenticate_websocket
from custom.server.errors import ApiError
from custom.server.models import ChatRequest, ChatResponse
from custom.server.ws import (
    build_engine_messages,
    engine_error,
    error_frame,
    now_ms,
    pull_chunk,
)

router = APIRouter(tags=["chat"])

CHAT_RATE_LIMIT = 20
PING_INTERVAL_S = 25.0


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    request: Request,
    device: DeviceDep,
) -> ChatResponse:
    state = request.app.state
    state.limiter.hit(f"chat:{device.device_id}", CHAT_RATE_LIMIT, 60)
    messages = build_engine_messages(state.services, body)

    started = time.perf_counter()
    try:
        reply = state.services.engine.chat(messages)
    except Exception as exc:  # noqa: BLE001 - mapped to a contract error
        raise engine_error(exc) from exc

    return ChatResponse(
        conversation_id=body.conversation_id,
        reply=reply,
        model=state.services.model,
        engine=state.services.engine_name,
        elapsed_ms=now_ms(started),
        pending_action=None,
    )


@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket) -> None:
    try:
        device = authenticate_websocket(websocket)
    except ApiError:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    state = websocket.app.state

    while True:
        try:
            raw = await asyncio.wait_for(
                websocket.receive_json(),
                timeout=PING_INTERVAL_S,
            )
        except TimeoutError:
            await websocket.send_json({"type": "ping", "ts": int(time.time())})
            continue
        except WebSocketDisconnect:
            break
        except json.JSONDecodeError:
            await websocket.send_json(error_frame(2001, "Invalid request"))
            continue

        if not isinstance(raw, dict):
            await websocket.send_json(error_frame(2001, "Invalid request"))
            continue
        if raw.get("type") == "pong":
            continue
        if raw.get("type") == "ping":
            await websocket.send_json({"type": "pong", "ts": int(time.time())})
            continue
        if raw.get("type") != "user":
            await websocket.send_json(error_frame(2001, "Unsupported message type"))
            continue

        try:
            body = ChatRequest.model_validate(raw)
        except ValidationError:
            await websocket.send_json(error_frame(2001, "Invalid request"))
            continue

        try:
            state.limiter.hit(f"chat:{device.device_id}", CHAT_RATE_LIMIT, 60)
        except ApiError as exc:
            await websocket.send_json(error_frame(exc.code, exc.message))
            continue

        try:
            await _stream_reply(websocket, state.services, body)
        except Exception:  # noqa: BLE001 - client disconnected mid-stream
            break

    try:
        await websocket.close()
    except RuntimeError:
        pass


async def _stream_reply(websocket: WebSocket, services, body: ChatRequest) -> None:
    messages = build_engine_messages(services, body)
    started = time.perf_counter()

    await websocket.send_json(
        {
            "type": "start",
            "conversation_id": body.conversation_id,
            "model": services.model,
        }
    )

    generator = None
    tokens = 0
    try:
        generator = services.engine.chat_stream(messages)
        while True:
            chunk = await asyncio.to_thread(pull_chunk, generator)
            if chunk is None:
                break
            if not chunk:
                continue
            tokens += 1
            await websocket.send_json({"type": "token", "text": chunk})
        await websocket.send_json(
            {
                "type": "done",
                "elapsed_ms": now_ms(started),
                "tokens": tokens,
                "pending_action": None,
            }
        )
    except ApiError as exc:
        await websocket.send_json(error_frame(exc.code, exc.message))
    except (WebSocketDisconnect, ConnectionError, RuntimeError):
        raise
    except Exception as exc:  # noqa: BLE001 - mapped to a contract error
        mapped = engine_error(exc)
        await websocket.send_json(error_frame(mapped.code, mapped.message))
    finally:
        if generator is not None:
            close = getattr(generator, "close", None)
            if callable(close):
                close()
