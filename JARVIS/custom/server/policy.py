"""Laptop-control action policy: catalog, path guard, command denylist.

The server validates every phone request before it reaches the desktop adapter.
Allowed roots come from `permissions.allowed_roots` in settings.yaml.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from custom.server.errors import ApiError

ALLOW = "allow"
ASK = "ask"

ACTION_POLICIES: dict[str, str] = {
    "app.list": ALLOW,
    "process.list": ALLOW,
    "app.open": ASK,
    "app.close": ASK,
    "file.read": ALLOW,
    "dir.list": ALLOW,
    "file.write": ASK,
    "file.delete": ASK,
    "cmd.run": ASK,
    "system.lock": ASK,
    "system.sleep": ASK,
    "system.shutdown": ASK,
    "system.volume": ASK,
    "system.mute": ASK,
    "system.screenshot": ASK,
    "media.play": ASK,
    "media.pause": ASK,
    "media.next": ASK,
    "media.prev": ASK,
    "clipboard.get": ASK,
    "clipboard.set": ASK,
    "notify": ALLOW,
    "whatsapp.message": ASK,
}

MAX_WRITE_BYTES = 256 * 1024
MAX_CLIPBOARD_BYTES = 64 * 1024
MAX_MESSAGE_BYTES = 4096

DENIED_COMMAND_PATTERNS: tuple[str, ...] = (
    "format",
    "diskpart",
    "bcdedit",
    "vssadmin delete",
    "cipher /w",
    "takeown /f c:\\",
    "icacls c:\\ /reset",
    "netsh advfirewall off",
    "set-mppreference",
    "net user",
    "reg delete hklm",
    "del /f /s c:\\",
    "rm -rf /",
    "remove-item -recurse c:\\",
)


def decision(action: str) -> str:
    policy = ACTION_POLICIES.get(action)
    if policy is None:
        raise ApiError(2002, "Unsupported action")
    return policy


def describe(action: str, params: dict[str, Any]) -> str:
    name = params.get("name", "")
    path = params.get("path") or params.get("save_path") or ""
    if action == "app.list":
        return "List installed applications"
    if action == "process.list":
        return "List running applications"
    if action == "app.open":
        return f"Open application: {name}"
    if action == "app.close":
        return f"Close application: {name}"
    if action == "file.read":
        return f"Read file: {path}"
    if action == "dir.list":
        return f"List folder: {path}"
    if action == "file.write":
        return f"Write file: {path}"
    if action == "file.delete":
        suffix = " (recursive)" if params.get("recursive") else ""
        return f"Delete: {path}{suffix}"
    if action == "cmd.run":
        return f"Run command: {params.get('command', '')}"
    if action == "system.lock":
        return "Lock the PC"
    if action == "system.sleep":
        return "Put the PC to sleep"
    if action == "system.shutdown":
        return f"Shut down in {params.get('delay_s', 0)} seconds"
    if action == "system.volume":
        return f"Set volume to {params.get('level', 0)}%"
    if action == "system.mute":
        return "Mute the PC" if params.get("mute") else "Unmute the PC"
    if action == "system.screenshot":
        return "Take a screenshot"
    if action.startswith("media."):
        return f"Media {action.split('.', 1)[1]}"
    if action == "clipboard.get":
        return "Read the clipboard"
    if action == "clipboard.set":
        return "Write to the clipboard"
    if action == "notify":
        return f"Show notification: {params.get('title', '')}"
    if action == "whatsapp.message":
        return f"Open WhatsApp with a message to {params.get('number', '')}"
    return action


def _require_str(params: dict[str, Any], key: str, *, max_length: int = 512) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiError(2001, f"Missing parameter: {key}")
    if len(value) > max_length:
        raise ApiError(2001, f"Parameter too long: {key}")
    return value


def _require_bool(params: dict[str, Any], key: str, default: bool = False) -> bool:
    value = params.get(key, default)
    if not isinstance(value, bool):
        raise ApiError(2001, f"Invalid parameter: {key}")
    return value


def _require_int(params: dict[str, Any], key: str, low: int, high: int) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError(2001, f"Invalid parameter: {key}")
    if not low <= value <= high:
        raise ApiError(2001, f"Parameter out of range: {key}")
    return value


def whatsapp_digits(number: str) -> str:
    """Country-code number with digits only (wa.me format)."""
    return "".join(ch for ch in number if ch.isdigit())


def _system_roots() -> list[Path]:
    roots: list[Path] = []
    for variable in ("SystemRoot", "ProgramFiles", "ProgramFiles(x86)", "APPDATA", "LOCALAPPDATA"):
        value = os.environ.get(variable)
        if value:
            try:
                roots.append(Path(value).expanduser().resolve(strict=False))
            except OSError:
                continue
    return roots


def _is_system_path(path: Path) -> bool:
    for root in _system_roots():
        try:
            if path == root or root in path.parents:
                return True
        except OSError:
            continue
    return False


def resolve_path(
    raw: str,
    allowed_roots: list[str],
    *,
    must_exist: bool = False,
) -> Path:
    """Resolve an absolute path and keep it inside the allowed roots."""
    if not isinstance(raw, str) or not raw.strip():
        raise ApiError(2001, "Missing path")
    if "\x00" in raw:
        raise ApiError(2001, "Invalid path")

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise ApiError(4002, "Path must be absolute")
    if ".." in Path(raw).parts:
        raise ApiError(4002, "Path traversal blocked")

    roots = [
        Path(root).expanduser().resolve(strict=False)
        for root in allowed_roots
        if isinstance(root, str) and root
    ]
    if not roots:
        raise ApiError(4002, "No allowed folders configured")

    resolved = candidate.resolve(strict=False)
    if _is_system_path(resolved):
        raise ApiError(4002, "System folders are blocked")
    if not any(resolved == root or root in resolved.parents for root in roots):
        raise ApiError(4002, "Path is outside allowed folders")

    if resolved.exists():
        real = resolved.resolve(strict=True)
        if _is_system_path(real):
            raise ApiError(4002, "System folders are blocked")
        if not any(real == root or root in real.parents for root in roots):
            raise ApiError(4002, "Path is outside allowed folders")
        resolved = real
    elif must_exist:
        raise ApiError(2004, "File not found")

    return resolved


def check_command(command: str) -> None:
    normalized = " ".join(command.lower().split())
    for pattern in DENIED_COMMAND_PATTERNS:
        if pattern in normalized:
            raise ApiError(4003, "Command blocked")


def validate(action: str, params: dict[str, Any], allowed_roots: list[str]) -> str:
    """Validate params + permission rules; returns the confirm description."""
    policy = decision(action)
    if not isinstance(params, dict):
        raise ApiError(2001, "Invalid parameters")

    if action in {"app.open", "app.close"}:
        name = _require_str(params, "name", max_length=128)
        if any(separator in name for separator in ("/", "\\")) or ".." in name:
            raise ApiError(4002, "Application name only")
    elif action == "file.read":
        resolve_path(_require_str(params, "path", max_length=1024), allowed_roots)
    elif action == "dir.list":
        resolve_path(_require_str(params, "path", max_length=1024), allowed_roots)
    elif action == "file.write":
        path = resolve_path(_require_str(params, "path", max_length=1024), allowed_roots)
        content = params.get("content")
        if not isinstance(content, str):
            raise ApiError(2001, "Missing parameter: content")
        if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
            raise ApiError(2003, "File content too large")
        if path.is_dir():
            raise ApiError(2001, "Target is a folder")
    elif action == "file.delete":
        resolve_path(_require_str(params, "path", max_length=1024), allowed_roots)
        _require_bool(params, "recursive", default=False)
    elif action == "cmd.run":
        command = _require_str(params, "command", max_length=2048)
        check_command(command)
        cwd = params.get("cwd")
        if cwd is not None:
            resolve_path(_require_str(params, "cwd", max_length=1024), allowed_roots)
    elif action == "system.shutdown":
        _require_int(params, "delay_s", 10, 120)
    elif action == "system.volume":
        _require_int(params, "level", 0, 100)
    elif action == "system.mute":
        _require_bool(params, "mute")
    elif action == "system.screenshot":
        save_path = params.get("save_path")
        if save_path is not None:
            resolve_path(_require_str(params, "save_path", max_length=1024), allowed_roots)
    elif action == "clipboard.set":
        text = params.get("text")
        if not isinstance(text, str):
            raise ApiError(2001, "Missing parameter: text")
        if len(text.encode("utf-8")) > MAX_CLIPBOARD_BYTES:
            raise ApiError(2003, "Clipboard text too large")
    elif action == "notify":
        _require_str(params, "title", max_length=200)
        body = params.get("body", "")
        if not isinstance(body, str) or len(body) > 1000:
            raise ApiError(2001, "Invalid parameter: body")
    elif action == "whatsapp.message":
        number = _require_str(params, "number", max_length=32)
        if not 7 <= len(whatsapp_digits(number)) <= 15:
            raise ApiError(2001, "Invalid phone number")
        text = params.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ApiError(2001, "Missing parameter: text")
        if len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise ApiError(2003, "Message too large")

    if policy == ALLOW:
        return ""
    return describe(action, params)
