"""LAN guard: private / loopback client addresses only."""

from __future__ import annotations

import ipaddress

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from custom.server.errors import error_body


def is_allowed_client(host: str | None) -> bool:
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return bool(address.is_private or address.is_loopback or address.is_link_local)


class LanGuardMiddleware:
    """ASGI middleware so WebSocket upgrades are guarded too."""

    def __init__(self, app: ASGIApp, enabled: bool = True) -> None:
        self.app = app
        self.enabled = enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if self.enabled and scope["type"] in {"http", "websocket"}:
            client = scope.get("client")
            host = client[0] if client else None
            if not is_allowed_client(host):
                if scope["type"] == "http":
                    response = JSONResponse(
                        error_body(4002, "Local network only"),
                        status_code=403,
                    )
                    await response(scope, receive, send)
                else:
                    await send({"type": "websocket.close", "code": 4403})
                return
        await self.app(scope, receive, send)
