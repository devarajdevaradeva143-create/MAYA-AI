# Security 🔐

Maya AI security module — all local, nothing uploaded.

**Implemented:**

| Method | Code | Notes |
|---|---|---|
| PIN lock | `custom/tools/security.py` | PBKDF2-SHA256, 5-attempt lockout, backup code |
| Face | `custom/tools/biometrics.py` + `bin/MAYA.exe` | Windows Hello, IR camera, anti-spoof |
| Voice | `custom/tools/biometrics.py` | spoken phrase hash + Vosk `vosk-spk` voiceprint |
| Unauthorized alerts | `custom/tools/security.py` | local audit list |

**Data:**

- `MAYA AI/memory/offline/security.json` — PIN hash + salt
- `MAYA AI/memory/offline/biometrics.json` — phrase hashes + voice vector
- `MAYA AI/security/bin/MAYA.exe` — your own Windows Hello bridge build
- `MAYA AI/Model/models/vosk-spk` — speaker model (13 MB)

**Rules:**

- Biometrics laptop-la mattum 🔒
- Cloud-kku poagadhu ❌
- No audio / no photo is ever written to disk
- PIN is always the fallback

Guides: `docs/BIOMETRICS.md`. Status: working (face + voice) and wired into
the session lock — `maya lock`, `maya security unlock --face|--voice`, and the
`--unlock` flags on the biometric commands. While locked, the full CLI is
guarded: only unlock/status/biometric verification/help stay available, and
`maya-cloud ask/chat` refuse to send.
