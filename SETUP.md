# MAYA AI — Full Setup Guide

> How to get Maya AI running on a fresh Windows (or Fedora) machine.
> For **building from source**, see `BUILD.md`.
> For **what's pending**, see `PENDING.md`.

---

## 1. What you're setting up

Maya AI is a **local-first personal AI assistant**:

- **Laptop app** (Windows): PySide6 desktop app — chat, voice, PC control, monitoring, English teacher, security (PIN/Hello/voiceprint), phone server.
- **Mobile app** (Android): phone companion that pairs over LAN.
- **Engine**: OpenJarvis + Qwen 3B (Lemonade server on port 13305).
- **Cloud (optional)**: Gemini via separate `maya-cloud` command.

Hardware tested: HP OmniBook 5 (Ryzen AI 5 340), Windows 11.

---

## 2. Quick start (end user — prebuilt exe)

1. Download `mayaai.exe` (from `LAPTOP\windows\dist\` or a release).
2. Put the `MAYA AI\` folder next to the exe (or set `MAYA_AI_HOME`).
3. Double-click `Maya AI.lnk` (or `mayaai.exe`).
4. First launch: no PIN → app opens. Go to **Security** page → set a PIN.
5. (Optional) Pair phone: Settings → Phone server → Start → New pairing PIN → enter in phone app.

That's it. No cloud, no account.

---

## 3. Developer setup (from source)

### 3.1 Clone

```powershell
git clone https://github.com/devarajdevaradeva143-create/MAYA-AI.git
cd "MAYA-AI"
```

Clone the engine (separate repo, read-only for us):
```powershell
cd JARVIS
git clone https://github.com/openjarvis/openjarvis.git OpenJarvis
cd ..
```

### 3.2 Install `uv` + Python 3.13

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 3.3 Windows app dependencies

```powershell
cd "LAPTOP\windows"
uv sync
.\.venv\Scripts\python.exe -m app --version   # "Maya AI 0.1.0"
```

### 3.4 Engine dependencies

```powershell
cd "JARVIS"
uv sync
uv run python -m custom.cli --help
```

### 3.5 Install Lemonade (engine server)

OpenJarvis talks to a Lemonade server on port 13305. Install Lemonade per `docs/ENGINE-SETUP.md`, then start it. Without it, chat returns empty (the app still boots).

---

## 4. First-run configuration

### 4.1 Settings (`MAYA AI\config\settings.yaml`)

Source of truth. Defaults work out of the box. Key sections:

```yaml
ui:
  theme: system            # dark | light | system
  window_width: 1180
  window_height: 760
  minimize_to_tray: true
  close_to_tray: true
  start_minimized: false
  confirm_destructive: true

server:
  enabled: true
  host: 0.0.0.0
  port: 8420
  lan_only: true

wake:
  enabled: true
  name: Maya
  name_repeat: 3
  clap_count: 3

voice:
  tts:
    engine: auto            # auto | piper | sapi
    preferred_voices: [heera, neerja]
  stt:
    engine: vosk
    model_root: MAYA AI/Model/models
    models: { en: vosk-en, en-in: vosk-en-in }
```

Edit via the in-app Settings page (YAML round-trip + timestamped backups) — don't hand-edit unless you know the schema.

### 4.2 Secrets (`.env`)

Create `MAYA AI\.env` (gitignored) or project-root `.env`:

```
GEMINI_API_KEY=...          # optional, for maya-cloud
MAYA_AI_HOME=...            # optional override
MAYA_DATA_HOME=...          # optional override
```

Or use `maya-cloud set-key` (hidden prompt → `.env`, owner-only permissions).

### 4.3 Voice models

Already present:
- `MAYA AI\Model\models\vosk-en` (English STT)
- `MAYA AI\Model\models\vosk-en-in` (Indian English STT)
- `MAYA AI\Model\models\vosk-spk` (speaker verification)

Tamil STT: not available (Vosk has no Tamil model) — see pending.

### 4.4 TTS voices

- Windows SAPI voices (heera, neerja, zira) work out of the box.
- Tamil TTS: install Piper + place a Tamil `.onnx` + config in `MAYA AI\voice\tamil\`. `tools/voice.py` prefers Piper automatically. Do not fake Tamil output.

### 4.5 Security (PIN)

1. Launch app → Security page → "Set PIN" → enter 4+ digits → confirm.
2. PIN is hashed (PBKDF2-SHA256 + salt) in `MAYA AI\memory\offline\security.json`. Never in `settings.yaml`.
3. On next launch with a PIN set and session locked, the lock screen appears.
4. Windows Hello: "Check availability" → "Verify now" (uses `MAYA AI\security\bin\MAYA.exe` helper, local only).
5. Voiceprint: "Enroll via CLI" opens a console (3 phrases).

Reset PIN: delete `MAYA AI\memory\offline\security.json` (with permission) → next launch unlocked.

---

## 5. Running

```powershell
cd "LAPTOP\windows"
.\.venv\Scripts\python.exe -m app            # GUI
.\.venv\Scripts\python.exe -m app --tray     # system tray
.\.venv\Scripts\python.exe -m app --headless # phone server only
```

In-app:
- Chat: type → Enter; Stop/Retry; persona switch (Maya / English Teacher)
- Voice: orb button → PTT; wake status chip
- PC control: pick action → Run (confirm dialog for risky ones)
- Monitor: live cards (CPU/RAM/GPU/NPU/battery/disks/uptime)
- Teacher: pick lesson → answer → feedback
- Security: PIN/Hello/voiceprint/audit log
- Settings: theme, tray behaviour, phone server Start/Stop/PIN, auto-start checkbox

---

## 6. Phone pairing (LAN)

1. Laptop + phone on same Wi-Fi.
2. App → Settings → Phone server → **Start server** (port 8420).
3. **New pairing PIN** → 6-digit PIN (valid ~2 min).
4. Phone app → Pair with PIN → enter PIN.
5. (Optional) Check "Start phone server with Maya" → auto-starts on next launch (persisted as `server.auto_start`).

Health check: `GET http://<laptop-ip>:8420/api/v1/health`.

---

## 7. Fedora (not yet validated on hardware)

```bash
cd "LAPTOP/fedora"
bash install_service.sh   # systemd unit
```

See `LAPTOP/fedora/README.md`. Idle lock needs `GetLastInputInfo` (Windows) or `xprintidle` (Fedora X11); on Wayland idle locking is inactive.

---

## 8. Mobile app setup

```powershell
cd "MOBILE APP"
.\gradlew.bat assembleDebug      # debug APK
.\gradlew.bat assembleRelease    # release APK (needs signing config)
```

APK output: `MOBILE APP/app/build/outputs/apk/`. Source: `MOBILE APP/app/src/main/`.

Phase 9 (on-device model test) is pending — see `docs/PHASE9-ONDEVICE-MODEL.md`.

---

## 9. Git workflow

```powershell
cd "C:\path\to\MAYA AI PROJECT"
git status
git add -A
git commit -m "your message"
git push origin main
```

Remote: `https://github.com/devarajdevaradeva143-create/MAYA-AI.git` (branch `main`).

`JARVIS/OpenJarvis/` is a separate git repo (read-only engine) — never commit its changes into this repo.

---

## 10. Verify everything works

```powershell
cd "LAPTOP\windows"
.\.venv\Scripts\python.exe -m pytest -q          # 185 tests
.\.venv\Scripts\ruff.exe check app tests          # All checks passed
.\.venv\Scripts\python.exe -m PyInstaller mayaai.spec --noconfirm
.\dist\mayaai.exe --version                      # Maya AI 0.1.0
git -C "JARVIS\OpenJarvis" status --porcelain     # must be empty
```

---

*Setup guide — Maya AI project. Update when setup steps change.*
