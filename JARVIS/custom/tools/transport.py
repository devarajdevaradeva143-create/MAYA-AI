"""LAN live transport for Maya signed bundles (stdlib only)."""

from __future__ import annotations

import http.server
import ipaddress
import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from custom.config import load_settings
from custom.tools import devices

DEFAULT_PORT = 8765
DEFAULT_MAX_MB = 25
CODE_HEADER = "X-Maya-Bundle"


def _settings() -> dict[str, Any]:
    try:
        data = load_settings()
    except Exception:  # pragma: no cover
        return {}
    return data if isinstance(data, dict) else {}


def _transport_cfg() -> dict[str, Any]:
    devices_cfg = _settings().get("devices", {})
    if not isinstance(devices_cfg, dict):
        return {}
    transport = devices_cfg.get("transport", {})
    return transport if isinstance(transport, dict) else {}


def _max_bytes() -> int:
    cfg = _transport_cfg()
    mb = cfg.get("max_mb", None)
    if mb is None:
        bundle_cfg = devices_cfg_bundle()
        mb = bundle_cfg.get("max_mb", DEFAULT_MAX_MB)
    try:
        return max(1, int(float(mb) * 1024 * 1024))
    except (TypeError, ValueError):
        return DEFAULT_MAX_MB * 1024 * 1024


def devices_cfg_bundle() -> dict[str, Any]:
    devices_cfg = _settings().get("devices", {})
    if not isinstance(devices_cfg, dict):
        return {}
    bundle = devices_cfg.get("bundle", {})
    return bundle if isinstance(bundle, dict) else {}


def is_private_ip(host: str, allow_loopback: bool = True) -> bool:
    """Return True when ``host`` is a private (LAN) address."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if ip.is_loopback:
        return bool(allow_loopback)
    return bool(ip.is_private)


def send_bundle(bundle_path: str, host: str, port: int = DEFAULT_PORT, timeout: float = 60.0) -> dict[str, Any]:
    """POST a signed bundle to a receiver. Never raises for network errors."""
    path = Path(bundle_path).expanduser()
    try:
        data = path.read_bytes()
    except OSError as exc:
        return {"ok": False, "code": "read_failed", "error": f"Could not read bundle: {exc}"}

    cap = _max_bytes()
    if len(data) > cap:
        return {"ok": False, "code": "too_large", "error": f"Bundle is larger than {cap // (1024 * 1024)} MB."}
    if not data:
        return {"ok": False, "code": "empty", "error": "Bundle is empty."}

    url = f"http://{host}:{int(port)}/live-bundle"
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            CODE_HEADER: "1",
            "Content-Length": str(len(data)),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8", errors="replace"))
        except (ValueError, UnicodeDecodeError):
            payload = {}
        return {
            "ok": False,
            "code": str(payload.get("code", "http_error")),
            "error": str(payload.get("error", f"HTTP {exc.code}")),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "code": "network_error", "error": str(exc)}

    try:
        payload = json.loads(body.decode("utf-8", errors="replace")) if body else {}
    except (ValueError, UnicodeDecodeError):
        payload = {}
    return {
        "ok": bool(payload.get("ok", True)),
        "bytes": len(data),
        "message": "Bundle sent." if payload.get("ok", True) else str(payload.get("error", "sent")),
        **{k: v for k, v in payload.items() if k not in ("ok",)},
    }


class _ReceiverState:
    def __init__(self) -> None:
        self.done = False
        self.result: dict[str, Any] | None = None
        self.lock = threading.Lock()


def receive_once(
    code: str,
    dest: str,
    host: str = "0.0.0.0",
    port: int = DEFAULT_PORT,
    timeout: float = 120.0,
    max_bytes: int | None = None,
    allow_public: bool = False,
) -> dict[str, Any]:
    """Receive exactly one bundle over HTTP and import it. Blocks up to ``timeout``."""
    if max_bytes is None:
        max_bytes = _max_bytes()
    dest_path = Path(dest).expanduser()
    state = _ReceiverState()

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self) -> None:  # noqa: N802
            if self.path.split("?", 1)[0] == "/health":
                self._send_json(200, {"ok": True, "name": "maya"})
            else:
                self._send_json(404, {"ok": False, "code": "not_found", "error": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            route = self.path.split("?", 1)[0]
            if route != "/live-bundle":
                self._send_json(404, {"ok": False, "code": "not_found", "error": "Not found"})
                return

            client_ip = self.client_address[0] if self.client_address else ""
            if not is_private_ip(client_ip, allow_loopback=True) and not allow_public:
                self._send_json(403, {"ok": False, "code": "public_client", "error": "Refusing non-private client."})
                with state.lock:
                    state.done = True
                    state.result = {"ok": False, "code": "public_client", "error": "Refusing non-private client."}
                return

            length_header = self.headers.get("Content-Length")
            if not length_header:
                self._send_json(411, {"ok": False, "code": "no_length", "error": "Content-Length required."})
                with state.lock:
                    state.done = True
                    state.result = {"ok": False, "code": "no_length", "error": "Content-Length required."}
                return
            try:
                total = int(length_header)
            except (TypeError, ValueError):
                self._send_json(400, {"ok": False, "code": "bad_length", "error": "Invalid Content-Length."})
                with state.lock:
                    state.done = True
                    state.result = {"ok": False, "code": "bad_length", "error": "Invalid Content-Length."}
                return
            if total <= 0 or total > max_bytes:
                self._send_json(413, {"ok": False, "code": "too_large", "error": f"Payload exceeds {max_bytes} bytes."})
                with state.lock:
                    state.done = True
                    state.result = {"ok": False, "code": "too_large", "error": f"Payload exceeds {max_bytes} bytes."}
                return

            data = bytearray()
            remaining = total
            try:
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 65536))
                    if not chunk:
                        break
                    data.extend(chunk)
                    remaining -= len(chunk)
            except Exception as exc:  # noqa: BLE001
                self._send_json(400, {"ok": False, "code": "read_error", "error": str(exc)})
                with state.lock:
                    state.done = True
                    state.result = {"ok": False, "code": "read_error", "error": str(exc)}
                return

            if len(data) != total:
                self._send_json(400, {"ok": False, "code": "incomplete", "error": "Incomplete upload."})
                with state.lock:
                    state.done = True
                    state.result = {"ok": False, "code": "incomplete", "error": "Incomplete upload."}
                return

            fd, tmp_name = tempfile.mkstemp(prefix="maya_live_", suffix=".json")
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                imported = devices.import_bundle(tmp_name, str(dest_path), code, overwrite=False, allow_replay=False)
            except Exception as exc:  # noqa: BLE001
                imported = {"ok": False, "code": "import_error", "error": str(exc)}
            finally:
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass

            result = dict(imported)
            result["bytes"] = len(data)
            if "ok" not in result:
                result["ok"] = False

            status_code = 200 if result.get("ok") else 400
            self._send_json(status_code, result)
            with state.lock:
                state.done = True
                state.result = result

        def log_message(self, *args: Any) -> None:  # noqa: D401
            return

    httpd = http.server.ThreadingHTTPServer((host, int(port)), Handler)
    httpd.daemon_threads = True
    httpd.allow_reuse_address = True
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.25}, daemon=True)
    thread.start()

    deadline = time.time() + float(timeout)
    try:
        while time.time() < deadline:
            with state.lock:
                if state.done:
                    break
            time.sleep(0.1)
    finally:
        try:
            httpd.shutdown()
        except Exception:  # noqa: BLE001
            pass
        httpd.server_close()
        thread.join(timeout=5)

    with state.lock:
        if state.result is not None:
            return state.result
    return {"ok": False, "code": "timeout", "error": "No bundle received within timeout."}


def receive_forever(
    code: str,
    dest: str,
    host: str = "0.0.0.0",
    port: int = DEFAULT_PORT,
    timeout: float = 120.0,
    max_bytes: int | None = None,
    allow_public: bool = False,
) -> None:
    """Loop receive_once until interrupted."""
    while True:
        receive_once(code, dest, host=host, port=port, timeout=timeout, max_bytes=max_bytes, allow_public=allow_public)
