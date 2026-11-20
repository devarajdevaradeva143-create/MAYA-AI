# Fedora — Maya AI

Maya AI desktop app for Fedora (KDE Plasma). **Partial implementation — see Status.**

- Target: Fedora 40+ (Workstation), KDE Plasma 6.x, Wayland primary, X11 fallback.
- UI: PySide6 (Qt6) + QML (per `MAYA EXTENSION` design language — liquid glass).
- Engine: reuse `JARVIS\custom` (common code) — see `JARVIS\custom\README.md`.
- Phone server: FastAPI `:8420` (shared API contract — `docs\API-CONTRACT.md`).
- Tray + autostart via systemd user service.

## Full plan

```
LAPTOP\fedora\PLAN.md        (to be created)
```

## Shared API

```
docs\API-CONTRACT.md
docs\REQUIREMENTS.md         (master spec — three apps, three modes)
```

## Requirements (from `docs/REQUIREMENTS.md`)

Fedora app must support, with parity to Windows:

### Modes
- **AI MODE** — voice + text commands, open/close apps, file/folder creation, code write/run, file management, permission-gated actions.
- **REMOTE MODE** — live screen view, mouse + keyboard control, app open/close, file view/transfer, remote control over Wi-Fi/Hotspot/Internet, Bluetooth nearby device contact.
- **HYBRID MODE** — direct user control + AI autonomous work simultaneously, voice/text commands, live monitoring of AI work, user takeover on demand, no control conflicts.

### Features
- Fedora MAYA AI core.
- Fedora PC control.
- Screen sharing.
- Mouse & Keyboard control.
- AI-driven task execution.
- All three modes present.

### Dual boot awareness
- On boot, mobile app auto-detects which OS is running (Fedora → Fedora MAYA AI active; Windows → Offline).
- Switching OS disconnects old connection, establishes new one.

### Security
- Password authentication, encrypted transport, permission-based remote access, AI action permission control, confirmation for critical actions, instant disconnect.

### Connection Manager
Manage four connection types: Wi-Fi, Mobile Hotspot, Bluetooth, Internet.
- Discover available connections, check status, secure connect, retry on drop, switch connection type on demand, integrate across Windows/Fedora/Android.
- Bluetooth for nearby devices; Internet/Network for remote control.

## Status

**Partial.** Remote-control adapters are implemented and structurally tested;
the desktop app and full phone-server wiring are not.

### Implemented (19 Nov 2026)
- `app/services/remote_service.py`: `ScreenAdapter` (maim → scrot fallback,
  Pillow resize), `InputAdapter` (xdotool, xrandr screen size) and
  `HybridAdapter` (shared `HybridController` — same surface as Windows).
- `app/maya.service` + `app/install_service.sh`: systemd **user** service that
  starts the shared monitor (`python -m custom.cli monitor start`).
- `tests/test_remote_service.py`: 5 structural tests (pass on any OS;
  hardware-specific paths fail closed off Linux).

Run the adapter tests with the JARVIS venv:
```bash
PYTHONPATH="../JARVIS:." ../JARVIS/.venv/bin/python -m pytest tests -q
```

### Not yet implemented / needs Fedora hardware
- Phone server (FastAPI `:8420`) wired to these adapters. The Windows
  `server_service.py` is the reference, but several of its adapters are
  Windows-specific (WMI, ctypes, PowerShell, WhatsApp deep links) and must be
  ported with parity before a Fedora server can safely run. Adapter wiring into
  a live server is therefore **not claimed as done**.
- Real screen capture / xdotool input validation on Wayland + X11 (needs Fedora).
- `maya.service` / `install_service.sh` execution on Fedora hardware.
- UI (PySide6/QML), PC control page, security/PIN, Connection Manager.

### To finish (when Fedora access is available)
1. Port the platform-neutral Windows adapters (engine, voice, monitor, teacher)
   into `app/services/`; write Linux equivalents for PC control.
2. Add `app/services/server_service.py` mirroring Windows `build_services()`,
   injecting `ScreenAdapter`, `InputAdapter`, `HybridAdapter`.
3. Update `maya.service` / `install_service.sh` ExecStart to launch the server.
4. Validate capture + input on Wayland and X11.

## Existing files (keep)

- `app/services/remote_service.py` — screen / input / hybrid adapters
- `app/maya.service`, `app/install_service.sh` — systemd user service
- `tests/test_remote_service.py` — adapter tests

## Notes

- Windows app reference: `LAPTOP\windows\README.md` (build complete, 195 tests pass).
- Design language / glass theme: `MAYA EXTENSION` project + `MAYA AI PROJECT.md`.
- Do NOT edit `JARVIS\OpenJarvis\` (read-only). Namma code `JARVIS\custom\` la mattum.
path: C:\Users\devar\Desktop\MAYA AI PROJECT\LAPTOP\fedora\README.md