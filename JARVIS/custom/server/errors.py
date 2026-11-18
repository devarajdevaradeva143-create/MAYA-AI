"""API error type + HTTP mapping for the Maya phone server."""

from __future__ import annotations

from typing import Any

# Contract section 3: code -> HTTP status.
HTTP_STATUS: dict[int, int] = {
    1001: 401,
    1003: 401,
    1004: 401,
    1005: 429,
    1006: 401,
    1007: 401,
    2001: 400,
    2002: 400,
    2003: 413,
    2004: 404,
    3001: 503,
    3002: 504,
    3003: 503,
    3004: 503,
    4002: 403,
    4003: 403,
    5000: 500,
}


class ApiError(Exception):
    """User-safe API failure rendered as the contract error envelope."""

    def __init__(
        self,
        code: int,
        message: str,
        status: int | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status or HTTP_STATUS.get(code, 500)
        self.details = details


def error_body(code: int, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}
