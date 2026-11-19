# Fedora — Maya AI

Maya AI desktop app for Fedora (KDE Plasma). **Design / plan only — implementation not started.**

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

**Placeholder.** Setup files not yet present. Implementation pending.

### Not yet implemented
- App skeleton (`app/` package)
- PC control module
- Screen capture / input injection (Wayland + X11)
- Phone server (FastAPI)
- Tray / autostart (systemd)
- Security (PIN, local store)
- Connection Manager (shared module ready: `JARVIS\custom\tools\connection_manager.py`)
- Tests

### To start implementation (when ready)
1. Create `app/` package mirroring `LAPTOP\windows\app\` structure (common code in `JARVIS\custom`).
2. Implement PC control first (reuse patterns from Windows).
3. Add screen share + input injection.
4. Wire phone server with shared API contract.
5. Add security + connection manager.
6. Tests + packaging.

## Existing files (keep)

- `app/` → (empty placeholder) chat app code (future)

## Notes

- Windows app reference: `LAPTOP\windows\README.md` (build complete, 195 tests pass).
- Design language / glass theme: `MAYA EXTENSION` project + `MAYA AI PROJECT.md`.
- Do NOT edit `JARVIS\OpenJarvis\` (read-only). Namma code `JARVIS\custom\` la mattum.
path: C:\Users\devar\Desktop\MAYA AI PROJECT\LAPTOP\fedora\README.md