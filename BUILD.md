# MAYA AI — Build Guide

> Full build instructions for the Windows desktop app, mobile app, and engine.
> Companion: `PENDING.md` (what's left), `docs/HANDOFF.md` (current state).

---

## 1. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Windows | 10/11 | Tested on Windows 11 build 26300 |
| Python | 3.13 (via `uv`) | `uv` manages the venv |
| `uv` | latest | https://docs.astral.sh/uv/ |
| Git | 2.56+ | |
| Android Studio / Gradle | (mobile only) | JDK 17+ |
| Lemonade server | (engine) | OpenJarvis uses it on port 13305 |

Install `uv`:
```powershell
powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

---

## 2. Clone the repo

```powershell
git clone https://github.com/devarajdevaradeva143-create/MAYA-AI.git
cd "MAYA-AI"
```

`JARVIS/OpenJarvis/` is a **nested git repo** (read-only engine). It is not part of this repo — clone it separately if missing:
```powershell
cd JARVIS
git clone https://github.com/openjarvis/openjarvis.git OpenJarvis
cd ..
```

---

## 3. Windows desktop app

### 3.1 Install dependencies

```powershell
cd "LAPTOP\windows"
uv sync
# or: uv pip install -r requirements.txt  (if no pyproject)
```

Venv lives at `LAPTOP\windows\.venv`. `pystray`, `Pillow`, `PySide6` are here (NOT in `JARVIS\.venv`).

### 3.2 Run in dev mode

```powershell
cd "LAPTOP\windows"
.\.venv\Scripts\python.exe -m app            # GUI
.\.venv\Scripts\python.exe -m app --tray     # start in tray
.\.venv\Scripts\python.exe -m app --headless # phone server only
.\.venv\Scripts\python.exe -m app --version  # smoke
```

### 3.3 Tests + lint

```powershell
cd "LAPTOP\windows"
.\.venv\Scripts\python.exe -m pytest -q          # 195 tests
.\.venv\Scripts\ruff.exe check app tests          # must be clean
```

### 3.4 Build the exe (PyInstaller)

```powershell
cd "LAPTOP\windows"
.\.venv\Scripts\python.exe -m PyInstaller mayaai.spec --noconfirm
# -> dist\mayaai.exe  (~61 MB)
```

Verify:
```powershell
.\dist\mayaai.exe --version   # "Maya AI 0.1.0"
```

### 3.5 Desktop shortcut (manual, one-time)

```powershell
$proj = "C:\path\to\MAYA AI PROJECT"
$exe  = "$proj\LAPTOP\windows\dist\mayaai.exe"
$wsh  = New-Object -ComObject WScript.Shell
$sc   = $wsh.CreateShortcut("$env:USERPROFILE\Desktop\Maya AI.lnk")
$sc.TargetPath       = $exe
$sc.WorkingDirectory = "$proj\LAPTOP\windows\dist"
$sc.IconLocation     = "$exe,0"
$sc.Description      = "Maya AI - local-first personal assistant"
$sc.Save()
```

The exe finds `MAYA AI\` from its own folder (or `MAYA_AI_HOME`), so no env var is required.

### 3.6 How the exe resolves `MAYA AI\`

Order (see `app/paths.py` + `JARVIS/custom/config.py`):
1. `MAYA_AI_HOME` (validated against `config\settings.yaml`)
2. `MAYA AI\` beside the exe, then each parent up to 5 levels (`dist\` → `windows\` → `LAPTOP\` → project root)
3. Dev fallback: `LAPTOP\windows\..\..\MAYA AI`

At startup the app publishes the resolved folder as `MAYA_AI_HOME` so `JARVIS\custom` uses the same one. Never use `__file__` in frozen mode.

---

## 4. Engine (OpenJarvis) setup

```powershell
cd "JARVIS"
uv sync
uv run python -m custom.cli --help
```

Engine runs on Lemonade server (port 13305). Start it before the app:
```powershell
# see JARVIS/UPDATE.md and docs/ENGINE-SETUP.md
```

Config source of truth: `MAYA AI\config\settings.yaml`. Never hardcode settings in code.

---

## 5. Mobile app (Android)

```powershell
cd "MOBILE APP"
.\gradlew.bat assembleDebug      # debug APK
.\gradlew.bat assembleRelease    # release APK (needs signing config)
```

APK output: `MOBILE APP/app/build/outputs/apk/`. Source: `MOBILE APP/app/src/main/`.

Note: `MOBILE APP/app/src/main/cpp/llama.cpp` is a vendored git repo — excluded from this repo's index.

---

## 6. Config & secrets

- Settings: `MAYA AI\config\settings.yaml` (YAML, ruamel round-trip, timestamped backups in `config\backups\`).
- Secrets (API keys): `.env` (gitignored). Use `maya-cloud set-key` or `python -m custom.cloud_cli set-key`.
- PIN: hashed with PBKDF2-SHA256 + salt in `MAYA AI\memory\offline\security.json`. **Never** in `settings.yaml`.
- Personal data: `DEVARAJ\` (gitignored).

---

## 7. Fedora (not yet validated on hardware)

```bash
cd "LAPTOP/fedora"
bash install_service.sh   # systemd unit
```

See `LAPTOP/fedora/README.md`.

---

## 8. Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `[config] Warning: .../Temp/MAYA AI/config/settings.yaml not found` | Old exe built before the paths fix. Rebuild with current source. |
| `Failed to execute script 'main'` | Run the exe from a console to see the traceback (console=True). Check `MAYA AI\logs\app.log`. |
| `pystray`/`Pillow` missing | You're in `JARVIS\.venv`. Use `LAPTOP\windows\.venv`. |
| Phone server 404 on `/health` | Correct path is `/api/v1/health`. |
| `Settings key is not editable` | Add the key to `_SCHEMA` in `app/settings_repository.py`. |
| Single instance blocks second launch | Force-kill leaves a stale pipe; retry or reboot. |
| `QObject.sender() unbound` | Fixed — was calling `QObject.sender()` instead of `self.sender()`. |
| Locked out of PIN | Delete `MAYA AI\memory\offline\security.json` (with user permission) to reset. |

---

## 9. GitHub push

```powershell
cd "C:\path\to\MAYA AI PROJECT"
git status
git add -A
git commit -m "your message"
git push origin main
```

Remote: `https://github.com/devarajdevaradeva143-create/MAYA-AI.git`. Branch: `main`.

---

## 10. Verification commands (run before reporting done)

```powershell
cd "LAPTOP\windows"
.\.venv\Scripts\python.exe -m pytest -q          # 195 tests
.\.venv\Scripts\ruff.exe check app tests          # All checks passed
.\.venv\Scripts\python.exe -m PyInstaller mayaai.spec --noconfirm
.\dist\mayaai.exe --version                      # Maya AI 0.1.0
git -C "JARVIS\OpenJarvis" status --porcelain     # must be empty
```

---

*Build guide — Maya AI project. Update when build steps change.*
