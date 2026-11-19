# MAYA AI — Pending Work List

> Last updated: 19 Nov 2026
> Scope: everything in `MAYA AI PROJECT\` that is not yet done.
> Companion: `docs/HANDOFF.md` (current state), `docs/ROADMAP.md` (phase plan).

---

## 0. Status snapshot

- **Windows desktop app**: complete for the planned 11 phases + items 2-10 below (240 tests pass, ruff clean, `dist\mayaai.exe` + desktop shortcut working).
- **Git**: initialized, first commit `11444d7` pushed to `origin/main`.
- **OpenJarvis**: untouched (read-only), clean.
- **Mobile app**: Phases 0-12 + remote screen/input/files + HYBRID control bus implemented; debug APK rebuilt 19 Nov. Physical on-device tests (airplane mode, USB/BT) still pending.
- **Model**: Qwen 3B (laptop); tamil-lm-2b switch deferred by user.

---

## 1. Windows app — true pending (not implemented)

| # | Item | What's needed | Effort |
|---|---|---|---|
| 1 | OS-level autostart (boot-la Maya auto-start) | Registry write + tray-only launch wiring; `install_autostart.ps1` exists but not wired. **User asked to keep this pending.** | User |
| 2 | PIN not set confirmation | `security.json` was reset 19 Nov; next launch prompts fresh PIN setup. Confirm with user. | User |

## 2. Windows app — known limitations (by design / environment)

- STT: English + Indian English (Vosk) + Tamil (faster-whisper small). Tamil accuracy limited by the small model.
- TTS: SAPI voices (heera, neerja, zira) + Piper (English optional, Tamil installed).
- Phone server: LAN only, no TLS (LAN assumption)
- PC control: 22 actions, some Windows-only (`_require_windows`)
- Engine: Qwen (weak Tamil/Tanglish), Lemonade on port 13305
- English teacher: 4 static lessons + AI-generated lessons with progress persistence (fallback when engine is down or output is unusable).
- Knowledge/RAG: English embeddings (`potion-base-8M`); Tamil paraphrase quality low (optional upgrade to `potion-multilingual-128M`, ~512 MB)
- Translation: uses the local engine only; English→Tamil quality is limited by the 2B model.

## 3. Mobile app — pending

| # | Item | Notes |
|---|---|---|
| 1 | Phase 9 on-device model test | Airplane mode reply, cancel, unload, tok/s + RAM measurement (DoD unverified) |
| 2 | Phase 10 Vosk name detection | Not implemented |
| 3 | Phase 11 USB/BT manual test | Not run |
| 4 | Physical remote-control test | Screen/input/files exercised on Infinix X6857B (pending) |
| 5 | Fedora screen/input adapter | Windows only today; Fedora adapter not wired |
| 6 | Internet/WAN remote | Needs relay + TLS design (LAN/hotspot/USB in v1) |
| 7 | Model switch to tamil-lm-2b | Deferred by user (currently Qwen3 1.7B) |
| 8 | Maya AI-drafted WhatsApp message | Not implemented (idea: chat reply → "Send to WhatsApp" prefill) |

## 4. Cross-cutting pending (laptop + Fedora)

| # | Item | Notes |
|---|---|---|
| 1 | `maya-cloud` live call | Code complete; no key configured. Run `maya-cloud set-key` (see `docs/CLOUD.md`) |
| 2 | Fedora validation | `maya.service` + `install_service.sh` not run on Fedora hardware |
| 3 | Knowledge embeddings upgrade | Optional: `minishlab/potion-multilingual-128M` + rebuild index |
| 4 | Cloud Gemini | Live key pending (user action) |

> Tamil TTS, Tamil STT and local translation are now DONE (19 Nov) — removed from pending.

## 5. Cleanup (done 19 Nov 2026)

- ✅ Legacy duplicates removed: `MAYA AI\scripts\maya-launch.ps1`, `maya-launch.sh` (`LAPTOP\windows\app\autostart.ps1` restored — needed if item 1.1 is wired later)
- ✅ Old embedding cache removed: `MAYA AI\Model\hf\hub\models--minishlab--potion-base-8M` (~29 MB freed)
- ✅ `security.json` reset (backup: `JARVIS\backups\security.json.bak-19nov`); next launch will prompt for fresh PIN setup

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
- Remote control (19-11): server + Windows adapters + Android UI for screen (JPEG polling), tap/drag/scroll/type input, file browse/download/upload in allowed roots, HYBRID control bus with takeover/release; 22 new Windows tests (230 total pass); contract frozen v1.1 §9A/§9B; docs/REMOTE-CONTROL.md
- Phone ↔ laptop pairing 19-11: Infinix X6857B paired to `10.87.222.204:8420` over the phone's hotspot (manual IP; mDNS not used). Phone Laptop tab shows "Connected to SELVA-KUMAR" + capabilities; laptop `/api/v1/health` reports `paired_devices: 2` (this phone + an older test token). End-to-end chat verified from the phone: "hii" → laptop reply rendered with a `Laptop` badge. Headless server run with `python -u -m app --headless` so the one-time PIN is visible in stdout; PIN is valid 120 s

## 7. Known issues / pitfalls

- PowerShell reports `Exit code: 1` for `uv`/`jarvis` even on success (stderr warnings). Harmless.
- `openjarvis.security: Failed to set up rate limiter: No module named 'openjarvis_rust'` — harmless warning.
- Tests must isolate storage with temp paths (`MAYA_*_STORE`, `MAYA_CHAT_HISTORY`, etc.). Never let tests write into `MAYA AI\memory\offline\`.
- Bundles are signed, not encrypted; nonce anti-replay now included for new bundles.
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
