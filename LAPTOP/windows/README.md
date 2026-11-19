# Laptop — Windows

Maya AI desktop app for Windows (PySide6, Python 3.13).

- UI: PySide6 (Python 3.13)
- Engine: `JARVIS\custom` reuse
- Phone server: FastAPI `:8420`
- Tray + autostart + wake (3 clap / "Maya" x3)

## Full plan

```
LAPTOP\windows\PLAN.md
```

## Shared API

```
docs\API-CONTRACT.md
```

## Status

Build complete — all 7 pages wired (chat, voice, pc, monitor, teacher, security, settings).
195 tests pass, ruff clean. `dist\mayaai.exe` built.

### Implemented
- Chat: streaming, Stop, Retry, persona switch, history persistence
- Voice: STT, TTS, clap wake, name wake, Voice page
- PC control: 15 actions + confirm dialog for risky ones
- Monitoring: CPU/RAM/GPU/NPU/battery/disks/uptime cards
- English Teacher: vocabulary, grammar, pronunciation, idioms
- Security: PIN (PBKDF2, local store), Windows Hello, voiceprint, lock screen
- Settings: YAML + backups, theme, tray behaviour, phone server control
- Phone server: Start/Stop/PIN from Settings; headless mode
- Tray: close-to-tray, minimize-to-tray, start-minimized

### Run (packaged)

```
Desktop\Maya AI.lnk   ->   dist\mayaai.exe
```

The exe locates `MAYA AI\` from its own folder (or `MAYA_AI_HOME`), so the
shortcut works without setting any environment variable. See
`docs\WINDOWS-APP.md` for the resolution order.

### Run

```powershell
cd "LAPTOP\windows"
.\.venv\Scripts\python.exe -m app            # GUI
.\.venv\Scripts\python.exe -m app --tray     # start in tray
.\.venv\Scripts\python.exe -m app --headless # phone server only
```

### Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check app tests
```

## Existing files (keep)

- `app\maya_tray.py` — legacy tray (fallback)
- `app\autostart.ps1` — old autostart
- `app\install_autostart.ps1` — updated autostart
