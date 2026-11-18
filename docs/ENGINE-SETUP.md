# Maya AI — Engine Setup

> Documents the inference backend + model choice for Maya AI.

## Backend: AMD Lemonade Server

Maya AI uses **AMD Lemonade Server** (already installed locally) as the
inference backend. It runs at `http://localhost:13305` and serves OpenAI-
compatible chat completions. FLM models run on the Ryzen AI NPU (50 TOPS).

- No model download needed — Lemonade serves pre-cached FLM models.
- Ollama is NOT used (not installed, not needed).
- OpenJarvis is available as a fallback engine mode.

## Model selection

| Setting | Value | Reason |
|---|---|---|
| `engine.model` | `qwen3.5-2b-FLM` | Small, fast, good for casual chat on this laptop |
| `engine.fallback_model` | `qwen3-it-4b-FLM` | Better quality, used if the primary is unavailable |
| `engine.host` | `http://localhost:13305` | Lemonade server endpoint |
| `engine.mode` | `direct` | HTTP straight to Lemonade (default) |

**Why qwen3.5-2b-FLM:** The HP OmniBook 5 (Ryzen AI 5 340) has limited
VRAM/RAM. The 2B model loads quickly and responds fast enough for
conversational use. The 4B and 8B models are available as fallbacks if
higher quality is needed.

**Do not download anything.** Lemonade already serves these FLM models.

## Configuration

All engine settings live in `MAYA AI/config/settings.yaml` under the
`engine:` section. Code reads from there via `custom/config.py` — never
hardcoded:

```yaml
engine:
  mode: direct          # direct | openjarvis
  type: lemonade        # lemonade backend
  host: http://localhost:13305
  model: qwen3.5-2b-FLM
  fallback_model: qwen3-it-4b-FLM
  timeout: 30           # seconds
  temperature: 0.7
  max_tokens: 512
```

## Engine bridge

Code: `JARVIS/custom/engine/bridge.py`

Two modes:

- **direct** (default): HTTP POST to `http://localhost:13305/v1/chat/completions`
- **openjarvis**: subprocess call to `JARVIS/.venv-engine/Scripts/jarvis.exe ask ...`

If the engine is unreachable, the bridge returns a clear `[engine error]`
message — it never crashes.

## Verified endpoints

- `GET /v1/models` → 200 (lists available FLM models)
- `GET /api/v1/health` → `{"status":"ok", ...}`
- `POST /v1/chat/completions` → works with `qwen3.5-2b-FLM`

## Verified CLI

```
JARVIS\.venv-engine\Scripts\jarvis.exe ask "text" -e lemonade -m qwen3.5-2b-FLM --no-stream
```

> Don't pass `--agent ''` — PowerShell drops the empty argument and Jarvis
> fails to parse the command.

## Available models (verified on this laptop)

`GET /v1/models` returned 6 models:

| Model | Notes |
|---|---|
| `qwen3.5-2b-FLM` | default — fastest |
| `qwen3-it-4b-FLM` | fallback — better quality, ~22 s/reply |
| `qwen3-8b-FLM` | strongest, but ~45 s/reply on NPU |
| `gemma3-1b-FLM` | tiny |
| `gemma4-it-e2b-FLM` | small instruct |
| `gemma4e-flash-e2b-FLM` | small flash |

## Known quality limit (honest note)

All three Qwen FLM models are **weak in Tamil / Tanglish**. The 8B model also
emits a `<think …>` preamble, which is slow and leaks into the reply.

Mitigation already in code: `custom/engine/bridge.py` strips `<think…>`
blocks before returning text (`_strip_thinking`).

To improve Tamil answers later, either:

1. pick a better Tamil-capable model and update `engine.model` in
   `settings.yaml`, or
2. keep English replies from the NPU model and do Tamil with a dedicated
   Tamil model / cloud command (`maya-cloud`, separate, permission-gated).

Nothing here downloads models automatically.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `[engine error] cannot reach engine` | start Lemonade Server; check `engine.host` |
| reply looks empty | model emitted only `<think>`; try `qwen3-it-4b-FLM` |
| `uv`/`jarvis` exit code 1 but output is fine | harmless — warnings go to stderr |
| `Failed to set up rate limiter: openjarvis_rust` | harmless warning when using `openjarvis` mode |
| slow replies (>30 s) | lower `engine.max_tokens`, or use `qwen3.5-2b-FLM` |
