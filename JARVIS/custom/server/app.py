"""FastAPI app factory for the Maya phone server (headless, no Qt)."""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from custom.server.auth import RateLimiter, TokenStore
from custom.server.confirm import ConfirmStore
from custom.server.contracts import ServerServices
from custom.server.errors import ApiError, error_body
from custom.server.lan import LanGuardMiddleware
from custom.server.pair import PairingManager
from custom.server.remote import RemoteSessionStore
from custom.server.routes import chat, events, health, hybrid, pair, pc, remote, voice, wake

logger = logging.getLogger("maya.server")

API_PREFIX = "/api/v1"
JSON_BODY_LIMIT = 1 * 1024 * 1024
AUDIO_BODY_LIMIT = 6 * 1024 * 1024
FILE_BODY_LIMIT = 25 * 1024 * 1024


class BodyLimitMiddleware:
    """Reject oversized HTTP bodies before reading them."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length:
            try:
                length = int(raw_length)
            except ValueError:
                length = 0
            path = scope.get("path", "")
            if path.endswith("/voice/stt"):
                limit = AUDIO_BODY_LIMIT
            elif path.endswith("/pc/files/upload"):
                limit = FILE_BODY_LIMIT
            else:
                limit = JSON_BODY_LIMIT
            if length > limit:
                response = JSONResponse(
                    error_body(2003, "Payload too large"),
                    status_code=413,
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


def _status_for_http(code: int) -> int:
    return {
        400: 2001,
        401: 1001,
        403: 4002,
        404: 2004,
        413: 2003,
        429: 1005,
        503: 3001,
        504: 3002,
    }.get(code, 5000)


async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    del request
    return JSONResponse(
        error_body(exc.code, exc.message, exc.details),
        status_code=exc.status,
    )


async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    del request, exc
    return JSONResponse(error_body(2001, "Invalid request"), status_code=400)


async def _http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    del request
    code = _status_for_http(exc.status_code)
    message = "Not found" if exc.status_code == 404 else "Request failed"
    return JSONResponse(error_body(code, message), status_code=exc.status_code)


async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled server error on %s: %s", request.url.path, type(exc).__name__)
    return JSONResponse(error_body(5000, "Internal server error"), status_code=500)


def create_app(
    services: ServerServices,
    *,
    token_store: TokenStore | None = None,
    limiter: RateLimiter | None = None,
    pairing: PairingManager | None = None,
    confirm_store: ConfirmStore | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Maya AI",
        version=services.version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.services = services
    app.state.tokens = token_store or TokenStore()
    app.state.limiter = limiter or RateLimiter()
    app.state.pairing = pairing or PairingManager(services.settings, app.state.tokens)
    app.state.confirm = confirm_store or ConfirmStore()
    app.state.remote = RemoteSessionStore()
    app.state.events_lock = asyncio.Lock()
    app.state.events_count = 0

    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(LanGuardMiddleware, enabled=services.settings.lan_only)

    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(Exception, _unhandled_handler)

    for module in (health, pair, chat, voice, pc, remote, hybrid, wake, events):
        app.include_router(module.router, prefix=API_PREFIX)

    return app
