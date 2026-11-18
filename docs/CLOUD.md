# Maya AI — Cloud (Gemini)

> Ithu **separate command** mattum: `maya-cloud`.
> Normal `maya chat` edhuvum cloud-kku anuppaadhu. Ever.

## Why it is separate

AGENTS.md rule: offline → online data pogaadhu. So cloud access is not a
setting you flip inside chat — it is a different executable that you run on
purpose, and it asks before every session (and every `ask`, unless `--yes`).

## One-time setup

1. Get a key: <https://aistudio.google.com/app/apikey>
2. Store it with the **hidden prompt** (recommended — the key never appears in
   shell history, process lists, or chat):

   ```powershell
   cd JARVIS
   python -m custom.cloud_cli set-key
   # or, after `uv pip install -e .`:
   maya-cloud set-key
   ```

   This writes `GEMINI_API_KEY=...` to `MAYA AI PROJECT\.env` atomically,
   preserves other lines/comments, and restricts the file to your account. The
   value is never printed.

   For automation, export the key and read it from the environment instead of
   putting it in a command line:

   ```powershell
   $env:GEMINI_API_KEY = "..."
   python -m custom.cloud_cli set-key --from-env --force
   ```

   Manual alternative: create `.env` in the project root (next to `AGENTS.md`)
   from `.env.example`. **Never commit `.env`** — it is in `.gitignore`. Never
   paste the key into chat or a command argument.

3. Check it (only the last four characters are shown):

   ```powershell
   cd JARVIS
   python -m custom.cloud_cli status
   # or, after `uv pip install -e .`:
   maya-cloud status
   ```

## Commands

```powershell
maya-cloud status
maya-cloud set-key                      # hidden prompt → .env
maya-cloud set-key --from-env --force   # automation (key from environment)
maya-cloud ask "Explain CMake in two lines"
maya-cloud ask "Summarise this" --file notes.md
maya-cloud ask "..." --dry-run          # show payload, send nothing
maya-cloud ask "..." --yes              # skip the confirmation
maya-cloud ask "..." --no-log           # do not write the online log
maya-cloud chat                         # interactive, confirms once
```

`--dry-run` is the safest way to see exactly what would leave the laptop.

### Lock guard

When the Maya session is locked (`maya lock`), `maya-cloud ask` and
`maya-cloud chat` refuse to run — a locked session must not leak local files to
Gemini through the separate cloud command. `maya-cloud status` and `--help`
still work. Unlock first with `maya security unlock <pin|--face|--voice>`.

## What gets sent

Only this:

- the prompt you typed
- any file you attached explicitly with `--file`
- an optional `--system` instruction you passed

**Never sent automatically:** offline memory, chat history, reminders, to-dos,
documents, personal details, microphone audio, or anything from `DEVARAJ/`.

## Configuration

`MAYA AI/config/settings.yaml`:

```yaml
cloud:
  enabled: true             # false = maya-cloud refuses to send
  provider: gemini
  model: gemini-3.5-flash
  endpoint: https://generativelanguage.googleapis.com/v1beta
  timeout: 60
  temperature: 0.7
  max_tokens: 1024
  require_confirmation: true
```

Model change panna indha value mattum edit pannu — code-la hardcode illa.

## Online history

Cloud exchanges are stored **separately** from offline memory:

```
MAYA AI/memory/online/cloud_log.jsonl
```

Offline data (`memory/offline/`) is never merged with it. Delete the file any
time to clear cloud history; `--no-log` skips writing entirely.

## Troubleshooting

| Symptom | Meaning |
|---|---|
| `No GEMINI_API_KEY found` | `.env` missing or key line empty |
| `Gemini key was rejected` | wrong/expired key — create a new one |
| `Gemini HTTP 404` | model name wrong or not available to your key |
| `Gemini returned nothing (SAFETY)` | prompt was blocked by safety filters |
| `Cannot reach Gemini` | no internet / firewall — cloud is optional, Maya stays offline |
| `Cloud is disabled in settings.yaml` | set `cloud.enabled: true` |

## Cost & privacy reminder

Gemini is a third-party service: what you send is processed by Google under
their terms. Keep prompts free of personal data. For anything private, use the
offline `maya chat` instead.
