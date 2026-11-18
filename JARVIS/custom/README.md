# custom

Maya AI-oda **namma code ellam** inga irukkum.
`JARVIS/OpenJarvis/` = official engine — **read-only** ❌ (edit pannaadhu).

## Enna inga irukku?

```
custom/
├─ cli.py          ← `maya` command (click CLI)
├─ config.py       ← settings.yaml loader
├─ engine/         ← engine bridge (Lemonade HTTP / openjarvis subprocess)
│  └─ bridge.py    ← chat + health + streaming, strips <think> blocks
├─ persona/        ← persona load logic (girlfriend / english teacher)
├─ tools/          ← assistant, monitor, devices, knowledge, language...
│  ├─ assistant.py    ← reminders + to-dos (local JSON persistence)
│  ├─ chat_history.py ← chat history → memory/offline only
│  ├─ knowledge.py    ← PDF / text search + persisted index
│  ├─ rag.py          ← chunking + BM25/semantic hybrid retrieval + grounded answers
│  ├─ embeddings.py   ← model2vec local embeddings (optional, BM25 fallback)
│  ├─ biometrics.py   ← Windows Hello face + Vosk phrase/voiceprint (local only)
│  ├─ devices.py      ← trusted pairing + HMAC-signed bundles (local only)
│  ├─ cloud.py        ← Gemini REST client (separate `maya-cloud` command)
│  ├─ monitor.py      ← CPU / RAM / GPU / NPU / temp / battery + alerts
│  ├─ security.py     ← PIN lock (PBKDF2), lockout, backup code
│  ├─ watchdog.py     ← idle/session auto-lock + optional voice re-check
│  ├─ voice.py        ← TTS (Piper → Windows SAPI), wake phrase
│  ├─ voice_stt.py    ← offline Vosk STT (file + microphone)
│  ├─ voice_clap.py   ← 3-clap wake detection
│  └─ store.py        ← offline JSON store helper
├─ plugins/        ← future OpenJarvis plugins
├─ wheels/         ← offline wheels (vosk, comtypes, ...)
├─ tests/          ← pytest tests
└─ README.md
```

## Rule

| ✅ | ❌ |
|---|---|
| Namma code `custom/` la mattum | `JARVIS/OpenJarvis/` edit pannaadhu |
| Engine change venum-na `JARVIS/patches/*.patch` | Engine-la direct-ah code ezhuthaadhu |

## Epdi run pannanum?

Package install pannina `maya` command kidaikkum:

```powershell
cd JARVIS
uv run maya --help
uv run maya wake
uv run maya todo add "Review AGENTS.md"
uv run maya todo list
uv run maya todo complete 1
uv run maya reminder set "09:00" "Drink water"
uv run maya reminder list
uv run maya config
uv run maya chat                   # real AI chat (Lemonade engine)
uv run maya security set-pin 1234
uv run maya security unlock --face
uv run maya lock
uv run maya security watchdog          # idle/session auto-lock + optional voice check
uv run maya biometrics status
uv run maya monitor status
uv run maya voice speak "Hello da"
uv run maya knowledge search "keyword"
uv run maya knowledge rag-search "session lock"
uv run maya devices pair phone
uv run maya devices list
uv run maya devices export phone --source "..\docs" --out "D:\maya\bundle.json"
uv run maya devices import "D:\maya\bundle.json" --dest "D:\MayaInbox"
```

Cloud is a separate command (never mixed with offline memory):

```powershell
uv run maya-cloud status
uv run maya-cloud set-key
uv run maya-cloud ask "Explain CMake in two lines" --dry-run
```

Install illama, direct-ah:

```powershell
python -m custom.cli --help
python -m custom.cli todo list
```

Tests:

```powershell
uv run python -m pytest custom/tests -q
```

> Python 3.13 use pannu (`JARVIS/.python-version`). OpenJarvis engine
> `requires-python = ">=3.10,<3.14"` — so rendu-me 3.13 interpreter share pannum.

## Config

Ellam `MAYA AI/config/settings.yaml` la irundhu dhaan varum.
Code-la settings hardcode pannaadhu.

## Privacy 🔒

- To-dos / reminders → `MAYA AI/memory/offline/assistant.json` mattum
- `memory/online/` kku ethuvum pogaadhu
- Personal details cloud-kku pogaadhu
- OpenJarvis read-only — namma ellam `custom/` la mattum ✅
