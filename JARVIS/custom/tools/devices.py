"""Maya AI Multi-device Connection tools.

Provides local Wi-Fi connection, Android phone synchronization, and remote access.
All operations are LOCAL first — remote access requires explicit user permission.

Per AGENTS.md: Multi-device Connection — Local Wi-Fi first, Remote access with password protection.
Personal details device-ku device poagadhu 🔒
"""

import sys
import os

import subprocess
from typing import List, Dict, Any, Optional
from pathlib import Path

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import shutil
import tempfile
import time

from ..config import PROJECT_ROOT, load_settings


ENV_DEVICES_STORE = "MAYA_DEVICES_STORE"
ENV_BUNDLE_NONCES = "MAYA_BUNDLE_NONCES"
STORE_FILENAME = "devices.json"
DEFAULT_OFFLINE_MEMORY = "memory/offline"
CODE_ITERATIONS = 600_000
BUNDLE_ITERATIONS = 600_000
BUNDLE_FORMAT = "maya-device-bundle"
BUNDLE_VERSION = 1
BUNDLE_NONCE_TTL_S = 30 * 24 * 60 * 60
MIN_CODE_LEN = 16
MAX_CODE_LEN = 256
MAX_NAME_LEN = 32
DEFAULT_MAX_FILES = 200
DEFAULT_MAX_MB = 25
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}
SENSITIVE_DIRS = {"devaraj", ".ssh", ".gnupg"}
SENSITIVE_NAMES = {
    ".env",
    "devices.json",
    "security.json",
    "biometrics.json",
}
SENSITIVE_PREFIXES = (".env.", "id_rsa", "id_ed25519", "id_ecdsa")
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".kdbx"}
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL", "CLOCK$",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


# ── Device Discovery ───────────────────────────────────────────────────────

def discover_local_devices(network_range: str = "192.168.1.0/24") -> List[Dict[str, Any]]:
    """Discover devices on local Wi-Fi network.

    Pings common IPs and returns responsive devices.
    """
    devices = []
    # Extract base IP for subnet scanning
    parts = network_range.split("/")[0].split(".")
    base_ip = f"{parts[0]}.{parts[1]}.{parts[2]}."

    # Common local IPs to check
    test_ips = [
        base_ip + "1",    # Router
        base_ip + "255",  # Broadcast
    ]

    for ip in test_ips:
        try:
            result = subprocess.run(
                ["ping", "-n", "1", "-w", "100", ip],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and "bytes=" in result.stdout:
                devices.append({
                    "ip": ip,
                    "status": "online",
                    "type": "local_device",
                })
        except Exception:
            pass

    return devices


# ── Android Connection ─────────────────────────────────────────────────────

def check_adb_available() -> bool:
    """Check if ADB (Android Debug Bridge) is available."""
    try:
        result = subprocess.run(
            ["adb", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_connected_androids() -> List[Dict[str, Any]]:
    """Get list of connected Android devices via ADB."""
    if not check_adb_available():
        return [{"status": "adb_not_available", "note": "Install ADB: sdkmanager 'platform-tools'"}]

    try:
        result = subprocess.run(
            ["adb", "devices"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        devices = []
        lines = result.stdout.strip().split("\n")
        for line in lines[1:]:  # Skip header
            if line.strip():
                parts = line.split("\t")
                if len(parts) >= 2:
                    devices.append({
                        "serial": parts[0],
                        "status": parts[1] if len(parts) > 1 else "unknown",
                    })
        return devices
    except Exception as e:
        return [{"status": "error", "note": f"ADB error: {e}"}]


# ── Wi-Fi Connection ──────────────────────────────────────────────────────

def validate_wifi_credentials(ssid: str, password: str) -> Dict[str, Any]:
    """Validate Wi-Fi connection credentials.

    Per AGENTS.md: Remote access — password protection.
    """
    # Simple validation — check they're not empty
    result = {
        "ssid": ssid.strip() if ssid else "",
        "password": password.strip() if password else "",
        "valid": bool(ssid.strip()) and bool(password.strip()),
    }
    return result


def test_wifi_connection(ssid: str, password: str) -> Dict[str, Any]:
    """Test Wi-Fi connection (platform-specific).

    Returns connection status.
    """
    if sys.platform == "win32":
        # Windows netsh command
        try:
            result = subprocess.run(
                ["netsh", "wlan", "connect", f"name={ssid}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout[-200:] if result.stdout else "",
                "error": result.stderr[-200:] if result.stderr else "",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    elif sys.platform == "linux":
        # Linux nmcli or iwconfig
        try:
            result = subprocess.run(
                ["nmcli", "device", "wifi", "connect", ssid, "password", password],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout[-200:] if result.stdout else "",
                "error": result.stderr[-200:] if result.stderr else "",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        return {"success": False, "note": "Wi-Fi connection not implemented for this platform"}


# ── Laptop Synchronization ────────────────────────────────────────────────

def get_laptop_info() -> Dict[str, Any]:
    """Get laptop identification info for sync purposes."""
    return {
        "hostname": os.environ.get("COMPUTERNAME", "unknown") if sys.platform == "win32" else os.environ.get("HOSTNAME", "unknown"),
        "platform": sys.platform,
        "python_version": __import__("sys").version.split(" ")[0],
        "maya_version": "0.1.0",
    }


def sync_file_between_devices(
    source_path: str,
    dest_path: str,
    remote_host: str,
    remote_user: str = "",
) -> Dict[str, Any]:
    """Sync a file between devices over SSH/Network.

    Per AGENTS.md: Un details device-ku device poagadhu 🔒
    - Local file copy first (no permission needed)
    - Remote copy requires explicit user permission
    """
    result = {
        "source": source_path,
        "destination": f"{remote_user}@{remote_host}:{dest_path}" if remote_user else dest_path,
        "remote_host": remote_host,
        "sync_type": "ssh" if remote_user else "local",
    }

    # Local sync (no remote user)
    if not remote_user:
        try:
            if os.path.exists(source_path):
                import shutil
                shutil.copy2(source_path, dest_path)
                result["status"] = "synced_local"
                result["note"] = "Local file copy completed"
            else:
                result["status"] = "source_not_found"
                result["note"] = f"Source file not found: {source_path}"
        except Exception as e:
            result["status"] = "error"
            result["note"] = f"Local sync error: {e}"
    else:
        # Remote sync requires explicit permission
        result["note"] = "Remote sync requires user permission — use maya devices sync command"
        result["status"] = "permission_required"

    return result


# ── Remote Access ─────────────────────────────────────────────────────────

def check_remote_access_allowed() -> Dict[str, Any]:
    """Check if remote access is configured and allowed.

    Per AGENTS.md: Remote access — password protection 🔒
    """
    # Check for common remote access configs
    config_paths = [
        r"~/.openjarvis/config.toml",
        r"~/.ssh/config",
    ]

    result = {"remote_access": False, "configs_checked": [], "note": "No remote access configured"}

    for cfg_path in config_paths:
        expanded = os.path.expanduser(cfg_path)
        result["configs_checked"].append(expanded)
        if os.path.exists(expanded):
            result["remote_access"] = True
            result["note"] = f"Remote access config found: {expanded}"
            break

    return result


# ── CLI Integration helpers ───────────────────────────────────────────────

def get_device_status_summary() -> str:
    """Return a formatted summary of device status for Maya to display."""
    parts = []

    # Paired (trusted) devices — local registry only.
    paired = list_paired_devices()
    parts.append(f"Paired: {len(paired)}")

    # Local devices
    local = discover_local_devices()
    parts.append(f"Local devices: {len(local)} found")

    # Android
    androids = get_connected_androids()
    if androids:
        android_status = androids[0].get("status", "none")
        parts.append(f"Android: {android_status}")

    # Remote access
    remote = check_remote_access_allowed()
    parts.append(f"Remote access: {'Enabled' if remote['remote_access'] else 'Disabled'}")

    # Laptop info
    laptop = get_laptop_info()
    parts.append(f"Laptop: {laptop['hostname']} ({laptop['platform']})")

    return " | ".join(parts)


# ── Trusted device registry ───────────────────────────────────────────────
#
# Pairing stores only a salted hash of the shared code. Bundles are signed
# with a key derived from that code, so another Maya install needs the same
# code to import them. Nothing here touches the network.

def _settings() -> Dict[str, Any]:
    try:
        settings = load_settings()
    except Exception:  # pragma: no cover - config must never crash devices
        return {}
    return settings if isinstance(settings, dict) else {}


def _devices_store_path() -> Path:
    override = os.environ.get(ENV_DEVICES_STORE, "").strip()
    if override:
        return Path(override).expanduser()
    memory = _settings().get("memory", {})
    offline = memory.get("offline", DEFAULT_OFFLINE_MEMORY) if isinstance(memory, dict) else DEFAULT_OFFLINE_MEMORY
    dir_path = Path(str(offline))
    if not dir_path.is_absolute():
        dir_path = PROJECT_ROOT / "MAYA AI" / dir_path
    return dir_path / STORE_FILENAME


def _default_store() -> Dict[str, Any]:
    return {"version": 1, "devices": {}}


def _load_store() -> Dict[str, Any]:
    path = _devices_store_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("devices"), dict):
            raise ValueError("invalid devices store")
        return data
    except ValueError:
        # Keep broken data for recovery instead of silently overwriting it.
        try:
            backup = path.with_name(path.name + f".corrupt-{int(time.time())}")
            os.replace(path, backup)
        except OSError:
            pass
    except OSError:
        pass
    return _default_store()


def _save_store(data: Dict[str, Any]) -> None:
    path = _devices_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def normalize_device_name(name: str) -> str:
    """Return a safe lowercase device name, or raise ``ValueError``."""
    text = str(name or "").strip().lower()
    if not text:
        raise ValueError("Device name is required.")
    if len(text) > MAX_NAME_LEN:
        raise ValueError(f"Device name must be at most {MAX_NAME_LEN} characters.")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", text):
        raise ValueError("Use letters, digits, '-' or '_' only (start with a letter/digit).")
    return text


def _hash_code(code: str, salt_hex: str, iterations: int = CODE_ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", _clean_code(code).encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
    ).hex()


def _clean_code(code: Any) -> str:
    """Strip surrounding whitespace; whitespace-only codes become empty."""
    return str(code or "").strip()


def _display(value: Any, limit: int = 64) -> str:
    """Make bundle-derived text safe to print in a terminal."""
    text = str(value)[:limit]
    return "".join(char if char.isprintable() else "?" for char in text)


def _public_device(record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": record.get("name"),
        "id": record.get("id"),
        "kind": record.get("kind", "bundle"),
        "created": record.get("created", 0),
        "last_sync": record.get("last_sync", 0),
    }


def pair_device(name: str, code: Optional[str] = None) -> Dict[str, Any]:
    """Register a trusted device. Returns the generated code exactly once.

    ``code`` is never stored raw; only a salted PBKDF2 hash. When omitted a
    128-bit code (32 hex characters) is generated and returned in the result.
    """
    try:
        clean = normalize_device_name(name)
    except ValueError as exc:
        return {"ok": False, "code": "bad_name", "error": str(exc)}

    data = _load_store()
    if clean in data["devices"]:
        return {
            "ok": False,
            "code": "already_paired",
            "error": f"Device '{clean}' is already paired. Revoke it first.",
        }

    generated = code is None
    if generated:
        code = secrets.token_hex(16)
    else:
        code = _clean_code(code)
    if len(code) < MIN_CODE_LEN:
        return {
            "ok": False,
            "code": "weak_code",
            "error": f"Pairing code must be at least {MIN_CODE_LEN} characters (spaces are stripped).",
        }
    if len(code) > MAX_CODE_LEN:
        return {
            "ok": False,
            "code": "weak_code",
            "error": f"Pairing code must be at most {MAX_CODE_LEN} characters.",
        }

    salt = secrets.token_hex(16)
    record = {
        "name": clean,
        "id": secrets.token_hex(8),
        "kind": "bundle",
        "code_algo": "pbkdf2_sha256",
        "code_iterations": CODE_ITERATIONS,
        "code_salt": salt,
        "code_hash": _hash_code(code, salt),
        "created": int(time.time()),
        "last_sync": 0,
    }
    data["devices"][clean] = record
    try:
        _save_store(data)
    except OSError:
        return {"ok": False, "code": "save_failed", "error": "Pairing data could not be saved."}

    result: Dict[str, Any] = {
        "ok": True,
        "name": clean,
        "id": record["id"],
        "generated": generated,
    }
    if generated:
        result["code"] = code
    return result


def list_paired_devices() -> List[Dict[str, Any]]:
    """Return paired devices without hashes or salts."""
    devices = _load_store()["devices"]
    return [
        _public_device(devices[name])
        for name in sorted(devices, key=lambda key: devices[key].get("created", 0))
    ]


def _device_record(name: str) -> Optional[Dict[str, Any]]:
    try:
        clean = normalize_device_name(name)
    except ValueError:
        return None
    return _load_store()["devices"].get(clean)


def verify_pair_code(name: str, code: str) -> bool:
    """Constant-time check of a device's pairing code."""
    record = _device_record(name)
    if not record:
        return False
    try:
        salt = record.get("code_salt", "")
        expected = record.get("code_hash", "")
        iterations = int(record.get("code_iterations", CODE_ITERATIONS))
        if not (100_000 <= iterations <= 2_000_000):
            return False
        candidate = _hash_code(code, salt, iterations)
    except (ValueError, TypeError, OverflowError):
        return False
    return bool(expected) and hmac.compare_digest(candidate, expected)


def revoke_device(name: str) -> Dict[str, Any]:
    """Remove a paired device. Existing bundles can no longer be imported."""
    record = _device_record(name)
    if not record:
        return {"ok": False, "code": "not_paired", "error": f"Device '{name}' is not paired."}
    data = _load_store()
    data["devices"].pop(record["name"], None)
    try:
        _save_store(data)
    except OSError:
        return {"ok": False, "code": "save_failed", "error": "Pairing data could not be saved."}
    return {"ok": True, "name": record["name"]}


def _touch_device(name: str) -> None:
    data = _load_store()
    record = data["devices"].get(name)
    if record:
        record["last_sync"] = int(time.time())
        try:
            _save_store(data)
        except OSError:
            pass


# ── Bundle nonce ledger (anti-replay) ─────────────────────────────────────

def _nonces_store_path() -> Path:
    override = os.environ.get(ENV_BUNDLE_NONCES, "").strip()
    if override:
        return Path(override).expanduser()
    memory = _settings().get("memory", {})
    offline = memory.get("offline", DEFAULT_OFFLINE_MEMORY) if isinstance(memory, dict) else DEFAULT_OFFLINE_MEMORY
    dir_path = Path(str(offline))
    if not dir_path.is_absolute():
        dir_path = PROJECT_ROOT / "MAYA AI" / dir_path
    return dir_path / "bundle_nonces.json"


def _load_nonces() -> dict[str, Any]:
    path = _nonces_store_path()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return {"version": 1, "seen": {}}
    if not isinstance(data, dict) or not isinstance(data.get("seen"), dict):
        return {"version": 1, "seen": {}}
    return {"version": 1, "seen": data["seen"]}


def _prune_nonces(data: dict[str, Any]) -> dict[str, Any]:
    seen = data.get("seen", {})
    if not isinstance(seen, dict):
        seen = {}
    now = time.time()
    pruned = {k: v for k, v in seen.items() if isinstance(v, (int, float)) and (now - float(v)) < BUNDLE_NONCE_TTL_S}
    return {"version": 1, "seen": pruned}


def _save_nonces(data: dict[str, Any]) -> None:
    path = _nonces_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    pruned = _prune_nonces(data)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(pruned, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


# ── Signed sync bundles ───────────────────────────────────────────────────

def _bundle_limits() -> tuple[int, int]:
    devices_cfg = _settings().get("devices", {})
    bundle_cfg = devices_cfg.get("bundle", {}) if isinstance(devices_cfg, dict) else {}
    try:
        max_files = max(1, int(bundle_cfg.get("max_files", DEFAULT_MAX_FILES)))
    except (TypeError, ValueError):
        max_files = DEFAULT_MAX_FILES
    try:
        max_mb = max(0.001, float(bundle_cfg.get("max_mb", DEFAULT_MAX_MB)))
    except (TypeError, ValueError):
        max_mb = DEFAULT_MAX_MB
    return max_files, int(max_mb * 1024 * 1024)


def _canonical(fields: Dict[str, Any]) -> bytes:
    return json.dumps(
        fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _bundle_key(code: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", _clean_code(code).encode("utf-8"), salt, int(iterations), dklen=32
    )


def _sign_bundle(fields: Dict[str, Any], key: bytes) -> str:
    payload = {name: value for name, value in fields.items() if name != "hmac"}
    return hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()


def _safe_relative(path: str):
    """Validate a bundle path; raise ``ValueError`` when unsafe.

    Rejects absolute/drive/UNC paths, traversal, control characters, NTFS
    alternate-data-stream colons, Windows reserved device names, and trailing
    dots/spaces. Only relative, portable path components survive.
    """
    from pathlib import PurePosixPath, PureWindowsPath

    text = str(path).replace("\\", "/").strip()
    if not text:
        raise ValueError("empty path")
    rel = PurePosixPath(text)
    if rel.is_absolute() or not rel.parts:
        raise ValueError("absolute path")
    if PureWindowsPath(text).drive:
        raise ValueError("drive path")
    for part in rel.parts:
        if part in ("", ".", ".."):
            raise ValueError("path traversal")
        if ":" in part:
            raise ValueError("drive/stream path")
        if any(ord(char) < 32 for char in part):
            raise ValueError("control character")
        if part.endswith((" ", ".")) or part.startswith(" "):
            raise ValueError("invalid trailing/leading character")
        base = part.split(".", 1)[0].upper()
        if base in RESERVED_NAMES:
            raise ValueError("reserved device name")
    return rel


def _is_link(path: Path) -> bool:
    """True for symlinks and Windows directory junctions."""
    try:
        if path.is_symlink():
            return True
        is_junction = getattr(path, "is_junction", None)
        if callable(is_junction) and is_junction():
            return True
    except OSError:
        return True
    return False


def _sensitive_reason(path: Path) -> Optional[str]:
    """Return why a path should be denied by default, or ``None``."""
    for part in path.parts:
        if part.lower() in SENSITIVE_DIRS:
            return f"folder '{part}'"
    name = path.name.lower()
    if name in SENSITIVE_NAMES:
        return f"file '{path.name}'"
    if name.startswith(SENSITIVE_PREFIXES):
        return f"file '{path.name}'"
    if any(name.endswith(suffix) for suffix in SENSITIVE_SUFFIXES):
        return f"file '{path.name}'"
    return None


def _walk_source_files(root: Path):
    """Yield regular files under ``root`` without following links/junctions."""
    resolved_root = root.resolve()
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in SKIP_DIRS and not _is_link(current_path / name)
        )
        for name in sorted(filenames):
            child = current_path / name
            if _is_link(child) or not child.is_file():
                continue
            try:
                if not child.resolve().is_relative_to(resolved_root):
                    continue
            except (OSError, ValueError):
                continue
            yield child


def _collect_sources(
    sources: List[str], max_files: int, max_bytes: int, allow_sensitive: bool = False
) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    seen: set[str] = set()
    total = 0

    for source in sources:
        path = Path(str(source)).expanduser()
        if not path.exists():
            return {"ok": False, "code": "source_not_found", "error": f"Source not found: {source}"}
        if _is_link(path):
            return {
                "ok": False,
                "code": "symlink_refused",
                "error": f"Symlinks/junctions are not bundled: {source}",
            }

        if path.is_file():
            pairs = [(path, path.name)]
        elif path.is_dir():
            pairs = [
                (child, (Path(path.name) / child.relative_to(path)).as_posix())
                for child in _walk_source_files(path)
            ]
        else:
            return {"ok": False, "code": "unsupported_source", "error": f"Not a file or folder: {source}"}

        for file_path, relative in pairs:
            if not allow_sensitive:
                reason = _sensitive_reason(file_path)
                if reason:
                    return {
                        "ok": False,
                        "code": "sensitive_file",
                        "error": (
                            f"Refusing to bundle {reason} ({relative}). "
                            "Use --allow-sensitive only if you really mean it."
                        ),
                    }
            if relative in seen:
                return {
                    "ok": False,
                    "code": "duplicate_path",
                    "error": f"Two sources produce the same bundle path: {relative}",
                }
            seen.add(relative)
            try:
                size = file_path.stat().st_size
            except OSError as exc:
                return {"ok": False, "code": "read_failed", "error": f"Could not read {relative}: {exc}"}
            if len(entries) >= max_files:
                return {
                    "ok": False,
                    "code": "too_many_files",
                    "error": f"Bundle limit is {max_files} files.",
                }
            if total + size > max_bytes:
                return {
                    "ok": False,
                    "code": "too_large",
                    "error": f"Bundle limit is {max_bytes // (1024 * 1024)} MB.",
                }
            try:
                raw = file_path.read_bytes()
            except (OSError, MemoryError) as exc:
                return {"ok": False, "code": "read_failed", "error": f"Could not read {relative}: {exc}"}
            size = len(raw)
            if total + size > max_bytes:
                return {
                    "ok": False,
                    "code": "too_large",
                    "error": f"Bundle limit is {max_bytes // (1024 * 1024)} MB.",
                }
            total += size
            entries.append({
                "path": relative,
                "size": size,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "data": base64.b64encode(raw).decode("ascii"),
            })

    if not entries:
        return {"ok": False, "code": "empty", "error": "No files to bundle."}
    return {"ok": True, "entries": entries, "bytes": total}


def export_bundle(
    name: str,
    code: str,
    sources: List[str],
    out_path: str,
    allow_sensitive: bool = False,
) -> Dict[str, Any]:
    """Write an HMAC-signed JSON bundle for a paired device.

    The bundle is **not encrypted** — it proves authenticity/integrity with the
    pairing code. Transfer it over a trusted path (USB, local share) and keep
    the pairing code secret. Secret stores and `DEVARAJ/` are refused unless
    ``allow_sensitive`` is set.
    """
    record = _device_record(name)
    if not record:
        return {"ok": False, "code": "not_paired", "error": f"Device '{name}' is not paired."}
    if not verify_pair_code(record["name"], code):
        return {"ok": False, "code": "bad_code", "error": "Pairing code is wrong."}

    max_files, max_bytes = _bundle_limits()
    collected = _collect_sources(
        list(sources), max_files, max_bytes, allow_sensitive=allow_sensitive
    )
    if not collected["ok"]:
        return collected

    kdf_salt = secrets.token_bytes(16)
    fields: Dict[str, Any] = {
        "format": BUNDLE_FORMAT,
        "version": BUNDLE_VERSION,
        "nonce": secrets.token_hex(16),
        "device": record["name"],
        "created": int(time.time()),
        "kdf": {
            "algo": "pbkdf2_sha256",
            "iterations": BUNDLE_ITERATIONS,
            "salt": kdf_salt.hex(),
        },
        "files": [
            {"path": entry["path"], "size": entry["size"], "sha256": entry["sha256"], "data": entry["data"]}
            for entry in collected["entries"]
        ],
    }
    key = _bundle_key(code, kdf_salt, BUNDLE_ITERATIONS)
    fields["hmac"] = _sign_bundle(fields, key)

    out = Path(out_path).expanduser()
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=out.name + ".", suffix=".tmp", dir=str(out.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(fields, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, out)
        except OSError:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except OSError as exc:
        return {"ok": False, "code": "write_failed", "error": f"Could not write bundle: {exc}"}

    _touch_device(record["name"])
    return {
        "ok": True,
        "device": record["name"],
        "files": len(fields["files"]),
        "bytes": collected["bytes"],
        "out": str(out),
    }


def import_bundle(
    bundle_path: str,
    dest_dir: str,
    code: str,
    overwrite: bool = False,
    allow_replay: bool = False,
) -> Dict[str, Any]:
    """Verify a signed bundle and extract it under ``dest_dir``.

    Validation happens before any write. Files are staged inside ``dest_dir``;
    existing files are backed up and restored if a later move fails.
    """
    path = Path(bundle_path).expanduser()
    max_files, max_bytes = _bundle_limits()
    max_json = max(1_000_000, max_bytes * 2 + 65_536)

    try:
        if path.stat().st_size > max_json:
            return {
                "ok": False,
                "code": "too_large",
                "error": f"Bundle file is larger than the {max_bytes // (1024 * 1024)} MB limit allows.",
            }
        raw_text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"ok": False, "code": "bundle_not_found", "error": f"Bundle not found: {bundle_path}"}
    except OSError as exc:
        return {"ok": False, "code": "bad_bundle", "error": f"Could not read bundle: {exc}"}

    try:
        bundle = json.loads(raw_text)
    except (ValueError, RecursionError, MemoryError):
        return {"ok": False, "code": "bad_bundle", "error": "Bundle is not valid JSON."}
    if not isinstance(bundle, dict):
        return {"ok": False, "code": "bad_bundle", "error": "Bundle is not a JSON object."}
    if bundle.get("format") != BUNDLE_FORMAT or bundle.get("version") != BUNDLE_VERSION:
        return {"ok": False, "code": "bad_bundle", "error": "Unknown bundle format/version."}

    raw_device = bundle.get("device", "")
    device_name = _display(raw_device)
    record = _device_record(str(raw_device))
    if not record:
        return {
            "ok": False,
            "code": "not_paired",
            "error": f"Sender '{device_name}' is not paired on this laptop.",
        }
    if not verify_pair_code(record["name"], code):
        return {"ok": False, "code": "bad_code", "error": "Pairing code is wrong."}

    kdf = bundle.get("kdf")
    if not isinstance(kdf, dict):
        return {"ok": False, "code": "bad_bundle", "error": "Bundle has no KDF data."}
    if kdf.get("algo") != "pbkdf2_sha256":
        return {"ok": False, "code": "bad_bundle", "error": "Bundle KDF algorithm is not supported."}
    try:
        salt = bytes.fromhex(str(kdf.get("salt", "")))
        iterations = int(kdf.get("iterations"))
    except (ValueError, TypeError, OverflowError):
        return {"ok": False, "code": "bad_bundle", "error": "Bundle KDF data is invalid."}
    if iterations != BUNDLE_ITERATIONS or not (16 <= len(salt) <= 64):
        return {"ok": False, "code": "bad_bundle", "error": "Bundle KDF parameters are not allowed."}

    key = _bundle_key(code, salt, iterations)
    expected = _sign_bundle(bundle, key)
    if not hmac.compare_digest(str(bundle.get("hmac", "")), expected):
        return {
            "ok": False,
            "code": "tampered",
            "error": (
                "Bundle signature is invalid (wrong code, edited file, or "
                "created before the device was re-paired with a new code)."
            ),
        }

    # ── Anti-replay (nonce) ─────────────────────────────────────────────
    nonce = bundle.get("nonce")
    if isinstance(nonce, str) and nonce.strip():
        nonce = nonce.strip()
        ledger = _load_nonces()
        seen = ledger.get("seen", {})
        if isinstance(seen, dict) and nonce in seen and not allow_replay:
            return {
                "ok": False,
                "code": "replay",
                "error": "This bundle was already imported. Re-export a fresh bundle to import again.",
            }

    files = bundle.get("files")
    if not isinstance(files, list) or not files:
        return {"ok": False, "code": "bad_bundle", "error": "Bundle contains no files."}
    if len(files) > max_files:
        return {"ok": False, "code": "too_many_files", "error": f"Bundle has more than {max_files} files."}

    dest_root = Path(dest_dir).expanduser().resolve()
    if dest_root.exists() and not dest_root.is_dir():
        return {"ok": False, "code": "invalid_target", "error": f"Destination is not a folder: {dest_root}"}

    plan: List[tuple[Path, bytes]] = []
    total = 0
    conflicts: List[str] = []
    seen_paths: set[tuple[str, ...]] = set()

    for entry in files:
        if not isinstance(entry, dict):
            return {"ok": False, "code": "bad_bundle", "error": "Bundle file entry is invalid."}
        try:
            rel = _safe_relative(str(entry.get("path", "")))
        except ValueError as exc:
            return {
                "ok": False,
                "code": "invalid_path",
                "error": f"Unsafe path {_display(entry.get('path'))!r}: {exc}",
            }

        key_parts = tuple(os.path.normcase(part) for part in rel.parts)
        if key_parts in seen_paths:
            return {
                "ok": False,
                "code": "duplicate_path",
                "error": f"Bundle contains the same path twice: {rel.as_posix()}",
            }
        for existing in seen_paths:
            if key_parts[: len(existing)] == existing or existing[: len(key_parts)] == key_parts:
                return {
                    "ok": False,
                    "code": "path_conflict",
                    "error": f"Bundle paths conflict as file/folder: {rel.as_posix()}",
                }
        seen_paths.add(key_parts)

        try:
            size = int(entry.get("size", -1))
        except (TypeError, ValueError, OverflowError):
            return {"ok": False, "code": "bad_bundle", "error": "Bundle file size is invalid."}
        if size < 0:
            return {"ok": False, "code": "bad_bundle", "error": "Bundle file size is invalid."}
        if total + size > max_bytes:
            return {"ok": False, "code": "too_large", "error": f"Bundle exceeds {max_bytes // (1024 * 1024)} MB."}

        data_text = str(entry.get("data", ""))
        expected_b64 = 4 * ((size + 2) // 3)
        if len(data_text) != expected_b64:
            return {"ok": False, "code": "corrupt", "error": f"Base64 length mismatch for {rel.as_posix()}."}
        try:
            raw = base64.b64decode(data_text, validate=True)
        except (ValueError, TypeError, binascii.Error):
            return {"ok": False, "code": "corrupt", "error": f"Base64 data is invalid for {rel.as_posix()}."}
        if len(raw) != size:
            return {"ok": False, "code": "corrupt", "error": f"Size mismatch for {rel.as_posix()}."}
        if hashlib.sha256(raw).hexdigest() != str(entry.get("sha256", "")):
            return {"ok": False, "code": "corrupt", "error": f"Hash mismatch for {rel.as_posix()}."}
        total += size

        try:
            target = (dest_root / Path(*rel.parts)).resolve()
        except (OSError, ValueError, OverflowError) as exc:
            return {"ok": False, "code": "invalid_path", "error": f"Path cannot be resolved: {rel.as_posix()} ({exc})"}
        if not target.is_relative_to(dest_root):
            return {"ok": False, "code": "invalid_path", "error": f"Path escapes destination: {rel.as_posix()}"}

        parent = target.parent
        while parent != dest_root and parent != parent.parent:
            if parent.exists() and parent.is_file():
                return {"ok": False, "code": "invalid_target", "error": f"Parent is a file: {rel.as_posix()}"}
            parent = parent.parent
        if target.exists() and target.is_dir():
            return {"ok": False, "code": "invalid_target", "error": f"Destination is a folder: {rel.as_posix()}"}
        if target.exists() and not overwrite:
            conflicts.append(rel.as_posix())
        plan.append((target, raw))

    if conflicts:
        return {
            "ok": False,
            "code": "exists",
            "error": f"{len(conflicts)} file(s) already exist. Use --overwrite to replace them.",
            "conflicts": conflicts[:20],
        }

    try:
        dest_root.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".maya-import-", dir=str(dest_root)))
    except OSError as exc:
        return {"ok": False, "code": "write_failed", "error": f"Could not prepare destination: {exc}"}

    backup_dir = staging / "backup"
    committed: List[tuple[Path, Optional[Path]]] = []
    try:
        backup_dir.mkdir()
        staged_files: List[Path] = []
        for index, (_target, raw) in enumerate(plan):
            staged = staging / f"file-{index}"
            staged.write_bytes(raw)
            staged_files.append(staged)

        for index, ((target, _raw), staged) in enumerate(zip(plan, staged_files)):
            target.parent.mkdir(parents=True, exist_ok=True)
            backup: Optional[Path] = None
            if target.exists():
                backup = backup_dir / f"backup-{index}"
                os.replace(target, backup)
            os.replace(staged, target)
            committed.append((target, backup))
    except (OSError, ValueError, MemoryError) as exc:
        for target, backup in reversed(committed):
            try:
                if backup is not None:
                    os.replace(backup, target)
                else:
                    target.unlink(missing_ok=True)
            except OSError:
                pass
        return {"ok": False, "code": "write_failed", "error": f"Could not write files: {exc}"}
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    _touch_device(record["name"])

    # Record the nonce only after a fully successful import.
    nonce = bundle.get("nonce")
    if isinstance(nonce, str) and nonce.strip():
        ledger = _load_nonces()
        seen = ledger.get("seen", {})
        if not isinstance(seen, dict):
            seen = {}
        seen[nonce.strip()] = time.time()
        try:
            _save_nonces({"version": 1, "seen": seen})
        except OSError:
            pass

    return {
        "ok": True,
        "device": record["name"],
        "files": len(plan),
        "bytes": total,
        "dest": str(dest_root),
    }