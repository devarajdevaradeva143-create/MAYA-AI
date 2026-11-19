# MAYA AI — Pending Work List

> Last updated: 18 Nov 2026
> Scope: everything in `MAYA AI PROJECT\` that is not yet done.
> Companion: `docs/HANDOFF.md` (current state), `docs/ROADMAP.md` (phase plan).

---

## 0. Status snapshot

- **Windows desktop app**: complete for the planned 11 phases (195 tests pass, ruff clean, `dist\mayaai.exe` + desktop shortcut working).
- **Git**: initialized, first commit `11444d7` pushed to `origin/main`.
- **OpenJarvis**: untouched (read-only), clean.
- **Mobile app**: Phases 0-12 implemented, debug+release APK built; Phase 9 on-device model test pending.
- **Model**: Qwen 3B (laptop); tamil-lm-2b switch deferred by user.

---

## 1. Windows app — true pending (not implemented)

| # | Item | What's needed | Effort |
|---|---|---|---|
| 1 | OS-level autostart (boot-la Maya auto-start) | Registry write + tray-only launch wiring; `install_autostart.ps1` exists but not wired | Medium |
| 2 | Tamil TTS | `uv pip install piper-tts` + Tamil `.onnx` voice in `MAYA AI\voice\tamil\` (user action) | User |
| 3 | Tamil STT | Vosk has no Tamil model → Whisper (or other) recogniser; larger change | Large |
| 4 | Language Intelligence (translation) | `custom\tools\language.py` translation functions are stubs; detect/phonetic work | Medium |
| 5 | English Teacher — AI lessons | 4 hardcoded lessons; AI-generated lessons + progress persistence | Medium |
| 6 | Voiceprint enrollment wizard | Currently "Enroll via CLI" opens a console; in-app wizard needed | Medium |
| 7 | Windows Hello enrollment | UI checks availability + opens settings; actual enrollment is in Windows Settings (by design) | By design |
| 8 | Monitor WMI temp | CPU temp cached 10s; runs on UI thread (QThread move optional) | Small |
| 9 | Server Start button blocks UI | 1-2s freeze; optional QThread | Small |
| 10 | Multi-device live transport | Pairing + signed bundles work; "live transport" pending. Bundles signed-not-encrypted, no anti-replay | Large |
| 11 | PIN not set confirmation | `security.json` exists with a PIN (created 18 Nov 17:27); confirm whether user set it | User |

## 2. Windows app — known limitations (by design / environment)

- STT: English + Indian English only (no Tamil)
- TTS: SAPI voices (heera, neerja, zira); Piper optional
- Phone server: LAN only, no TLS (LAN assumption)
- PC control: 22 actions, some Windows-only (`_require_windows`)
- Engine: Qwen (weak Tamil/Tanglish), Lemonade on port 13305
- English teacher: 4 static lessons, no progress tracking
- Knowledge/RAG: English embeddings (`potion-base-8M`); Tamil paraphrase quality low (optional upgrade to `potion-multilingual-128M`, ~512 MB)

## 3. Mobile app — pending

| # | Item | Notes |
|---|---|---|
| 1 | Phase 9 on-device model test | Airplane mode reply, cancel, unload, tok/s + RAM measurement (DoD unverified) |
| 2 | Phase 10 Vosk name detection | Not implemented |
| 3 | Phase 11 USB/BT manual test | Not run |
| 4 | Phase 12 instrumented tests | `androidTest` folder missing |
| 5 | Model switch to tamil-lm-2b | Deferred by user (currently Qwen3 1.7B) |
| 6 | WhatsApp send — manual phone test | APK rebuilt 19-11 07:54 (`app-release.apk`); number `+`/spaces fix + WhatsApp Business detect added. Test: Phone tab → WhatsApp → confirm → send |
| 7 | Maya AI-drafted WhatsApp message | Not implemented (idea: chat reply → "Send to WhatsApp" prefill) |

## 4. Cross-cutting pending (laptop + Fedora)

| # | Item | Notes |
|---|---|---|
| 1 | Tamil TTS | See 1.2 |
| 2 | Tamil STT | See 1.3 |
| 3 | `maya-cloud` live call | Code complete; no key configured. Run `maya-cloud set-key` (see `docs/CLOUD.md`) |
| 4 | Fedora validation | `maya.service` + `install_service.sh` not run on Fedora hardware |
| 5 | Language Intelligence (translation) | See 1.4 |
| 6 | Knowledge embeddings upgrade | Optional: `minishlab/potion-multilingual-128M` + rebuild index |
| 7 | Cloud Gemini | Live key pending (user action) |

## 5. Cleanup (ask user first)

- Legacy duplicates: `MAYA AI\scripts\maya-launch.ps1`, `maya-launch.sh`, `LAPTOP\windows\app\autostart.ps1`
- Old embedding cache `MAYA AI\Model\hf\hub\models--minishlab--potion-base-8M` (~29 MB)
- `security.json` reset if the 17:27 PIN was not user-set

## 6. Verified complete (honest claim)

- All 11 planned Windows phases ✅
- 195 tests pass, ruff clean
- `dist\mayaai.exe` (61 MB) + desktop shortcut working
- Path bug + 3 runtime bugs fixed
- Phone server auto-start wired (Settings checkbox)
- Git initialized + first commit pushed (`11444d7` → `origin/main`)
- `JARVIS\OpenJarvis\` untouched (clean)
- Engine venv repaired 19-11: `.venv-engine` editable link pointed to deleted `maya-maya\OpenJarvis` → reinstalled from current path; `import openjarvis` + `jarvis --version` OK; JARVIS tests 333 passed / 1 skipped
- `.gitignore` fix 19-11: `DEVARAJ/` was unanchored → ignored `com/devaraj/` Kotlin package (mobile source never committed); now `/DEVARAJ/`, mobile source tracked
- PC Control page 19-11: display labels were passed straight to `ControlService` (every action failed with "Unsupported action"); added `ACTION_IDS` label→id map, `ConfirmDialog` was a `QWidget` with no `setModal` + `setContentsMargens` typo (crashed), audit signal now connected
- WhatsApp (laptop) 19-11: `whatsapp.message` action — confirm dialog → opens WhatsApp Desktop with `whatsapp://send?phone=…&text=…` prefilled (browser `wa.me` fallback); user presses Send. Tests: +9 (`tests/test_whatsapp.py`)

## 7. Known issues / pitfalls

- PowerShell reports `Exit code: 1` for `uv`/`jarvis` even on success (stderr warnings). Harmless.
- `openjarvis.security: Failed to set up rate limiter: No module named 'openjarvis_rust'` — harmless warning.
- Tests must isolate storage with temp paths (`MAYA_*_STORE`, `MAYA_CHAT_HISTORY`, etc.). Never let tests write into `MAYA AI\memory\offline\`.
- Bundles are signed, not encrypted; no anti-replay/nonce.
- Pairing codes are long-lived shared secrets; never log/print after pairing.
- `security watchdog` is command-only; never add to autostart without user asking.
- Voice re-check is fail-closed once enabled.

## 8. Suggested next steps (pick one)

1. `mobile phase 9` — on-device model test (airplane mode, cancel, unload, tok/s)
2. `tamil-lm-2b` — laptop model switch
3. `os autostart` — Windows boot autostart
4. `tamil stt` / `tamil tts` — language support
5. `teacher ai lessons` — AI-generated English lessons
6. `cloud key` — `maya-cloud set-key`

---

*Generated by Vera AI (Beam) on 18 Nov 2026. Update this file as items complete.*
