# MAYA AI — Laptop ↔ Phone API Contract (v1)

> Ithu **single source of truth** — phone app + laptop server rendum ithai follow pannanum.
> Vera AI code pannum bothu ithai first padikkum.
> Simple Thanglish-la ezhuthirukken.

**Status:** Design locked (v1) — implementation innum illa.
**Owner files:**
- Server: `JARVIS\custom\server\` (Windows + Fedora share)
- Client: `MOBILE APP\app\src\main\java\com\devaraj\maya\data\remote\`
- Plans: `MOBILE APP\PLAN.md`, `LAPTOP\windows\PLAN.md`

---

## 0. Hard rules

1. **LAN only.** No internet, no cloud relay, no public IP.
2. Server binds `0.0.0.0:8420` aana **private IP mattum accept pannum**
   (10/8, 172.16/12, 192.168/16, 169.254/16, 127.0.0.1). Public source IP → reject `403`.
3. Phone-la irundhu **Gemini / cloud AI-ku call illa** ❌
4. Offline → online data flow **illa** ❌
5. Pairing illama auth-required endpoint call panna koodadhu.
6. Chat content server-la **store pannaadhu** — phone-la mattum history.
7. API change = **additive only**. Existing field name/type change panna koodadhu.
8. Ellam JSON UTF-8, field names `snake_case`.
9. Timestamps = Unix seconds (integer), unless noted.
10. Error format always same envelope (section 3).

---

## 1. Basics

| Item | Value |
|---|---|
| Base URL | `http://<laptop-ip>:8420/api/v1` |
| Protocol | HTTP/1.1 + WebSocket |
| Default port | `8420` |
| WS base | `ws://<laptop-ip>:8420/api/v1/ws/...` |
| JSON body limit | 1 MB |
| Audio upload limit | 5 MB |
| Server | Python FastAPI + uvicorn |
| Client | Kotlin + OkHttp |

**No TLS in v1.** Threat model = trusted home LAN. TLS + certificate pinning future-la.

`GET /health` mattum unauthenticated (phone laptop-ah kandupidikka).

---

## 2. Auth

### 2.1 Token

- Format: `maya_<43 chars urlsafe>` (opaque).
- Server stores **SHA-256(token)** mattum — plain token never disk-la.
- Header: `Authorization: Bearer <token>`
- TTL: `server.token_ttl_hours` (default **720 h = 30 days**).
- Refresh: TTL 7 days-ku kammi aanaa `POST /pair/refresh`.
- Revoke: phone-lum laptop UI-lum possible.
- Token device-ku bind aagum. Device revoke aanaa → `401 / 1007`.

### 2.2 Pairing — PIN flow

1. Laptop UI-la **Pair Phone** open → 6-digit PIN generate (TTL **120 s**, memory only).
2. Phone → `POST /pair/claim` with `pin`, `device_id`, `device_name`.
3. Server PIN verify (constant time), 5 attempts max → 10 min lockout.
4. Success → device record create + token return.
5. Phone secure storage-la token save (Android Keystore AES-GCM).

### 2.3 Pairing — QR flow

Laptop QR payload (JSON, 120 s, single-use):

```json
{
  "v": 1,
  "h": "192.168.1.5",
  "p": 8420,
  "t": "<32-byte hex one-time token>",
  "n": "Devaraj-Laptop"
}
```

- QR token server-la **hash**-ah mattum store, single use.
- Phone scan → `POST /pair/qr/claim`.
- Expired / used → `1004`.

### 2.4 Auto-connect (optional)

- User setting. Default **off**.
- Enable = stored valid token irundhaa app auto-connect pannum (prompt illa).
- Token invalid → pairing screen-ku pogum.
- "Auto-connect without pairing" **never** allowed.

### 2.5 Pairing rules

| Rule | Value |
|---|---|
| PIN length | 6 digits |
| PIN TTL | 120 s |
| PIN attempts | 5 |
| Lockout | 10 min |
| QR TTL | 120 s, single use |
| Max paired devices | 8 |
| Token TTL | 30 days |

---

## 3. Errors

```json
{
  "error": {
    "code": 1003,
    "message": "Invalid PIN",
    "details": null
  }
}
```

| Code | HTTP | Meaning |
|---|---|---|
| 1001 | 401 | Missing / invalid token |
| 1003 | 401 | Wrong PIN |
| 1004 | 401 | PIN / QR expired or used |
| 1005 | 429 | Rate limited / locked out |
| 1006 | 401 | Token expired |
| 1007 | 401 | Device revoked |
| 2001 | 400 | Bad request / validation |
| 2002 | 400 | Unsupported action |
| 2003 | 413 | Payload too large |
| 2004 | 404 | Not found |
| 3001 | 503 | Engine unavailable (laptop model down) |
| 3002 | 504 | Engine timeout |
| 3003 | 503 | STT unavailable |
| 3004 | 503 | TTS unavailable |
| 4002 | 403 | Permission denied |
| 4003 | 403 | Action blocked (dangerous) |
| 5000 | 500 | Internal error |

Error message = English, user-safe. Stack trace / path ellam client-ku anuppaadhu.

---

## 4. Endpoints — overview

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | ❌ | Server alive + capabilities |
| POST | `/pair/claim` | ❌ | PIN pairing |
| POST | `/pair/qr/claim` | ❌ | QR pairing |
| POST | `/pair/refresh` | ✅ | Token refresh |
| GET | `/pair/devices` | ✅ | Paired device list |
| DELETE | `/pair/devices/{device_id}` | ✅ | Revoke device |
| POST | `/chat` | ✅ | Non-streaming chat |
| WS | `/ws/chat` | ✅ | Streaming chat |
| POST | `/voice/stt` | ✅ | Audio → text |
| POST | `/voice/tts` | ✅ | Text → audio (WAV) |
| GET | `/voice/status` | ✅ | TTS/STT engines |
| GET | `/pc/status` | ✅ | CPU / RAM / GPU / battery / disk |
| POST | `/pc/command` | ✅ | Laptop action request |
| POST | `/pc/confirm` | ✅ | Execute confirmed action |
| POST | `/pc/cancel` | ✅ | Discard pending action |
| GET | `/wake/status` | ✅ | Wake listener state |
| POST | `/wake/listen` | ✅ | Start 60 s wake listen |
| POST | `/wake/stop` | ✅ | Stop wake listen |
| WS | `/ws/events` | ✅ | Live status + events |

---

## 5. Health

### `GET /api/v1/health`

No auth. Personal data illa.

```json
{
  "status": "ok",
  "app": "maya-laptop",
  "version": "0.1.0",
  "api": 1,
  "platform": "windows",
  "model": "qwen3-3b",
  "engine": "lemonade",
  "capabilities": [
    "chat",
    "chat_stream",
    "voice_stt",
    "voice_tts",
    "pc_control",
    "wake",
    "monitor"
  ],
  "paired_devices": 1,
  "uptime_s": 360
}
```

---

## 6. Pairing endpoints

### `POST /pair/claim`

```json
{
  "device_id": "android-id-32-hex",
  "device_name": "Devaraj Phone",
  "pin": "482913",
  "app_version": "0.1.0",
  "api": 1
}
```

Success `200`:

```json
{
  "token": "maya_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "expires_at": 1767000000,
  "laptop_name": "Devaraj-Laptop",
  "api": 1,
  "host": "192.168.1.5",
  "port": 8420
}
```

### `POST /pair/qr/claim`

```json
{
  "qr_token": "a1b2c3...",
  "device_id": "android-id-32-hex",
  "device_name": "Devaraj Phone",
  "app_version": "0.1.0",
  "api": 1
}
```

Response = same as PIN success.

### `POST /pair/refresh`

Auth header with current token.

```json
{ "device_id": "android-id-32-hex" }
```

→ `{ "token": "...", "expires_at": 1767000000 }`

### `GET /pair/devices`

```json
{
  "devices": [
    {
      "device_id": "android-id-32-hex",
      "name": "Devaraj Phone",
      "paired_at": 1760000000,
      "last_seen": 1760100000,
      "current": true
    }
  ]
}
```

### `DELETE /pair/devices/{device_id}`

→ `{ "revoked": true }`

Current device-ah revoke panna client token-ah delete pannum.

---

## 7. Chat

Server stateless. History phone-la. Client last **24 messages** mattum anuppum.

### `POST /chat`

```json
{
  "conversation_id": "c_01JABCDEF",
  "persona": "maya",
  "messages": [
    { "role": "user", "content": "enna panra?" },
    { "role": "assistant", "content": "Un pakkathula dhaan da 😊" },
    { "role": "user", "content": "time enna?" }
  ]
}
```

Rules:
- `role` = `user` | `assistant` mattum. `system` reject (`2001`).
- Max messages 24, total chars 12 000.
- Server persona system prompt-ah prepend pannum. Client system prompt anuppa koodadhu.
- `persona`: `maya` | `teacher`. Default `maya`.

Success:

```json
{
  "conversation_id": "c_01JABCDEF",
  "reply": "Ippo 7:42 PM da.",
  "model": "qwen3-3b",
  "engine": "lemonade",
  "elapsed_ms": 1830,
  "pending_action": null
}
```

`pending_action` (future tool use):

```json
{
  "confirm_token": "cf_...",
  "description": "Open Notepad",
  "action": "app.open",
  "expires_in": 60
}
```

Client `POST /pc/confirm` call pannum (section 9.3).

### `WS /ws/chat?token=<token>`

Client → server:

```json
{
  "type": "user",
  "conversation_id": "c_01JABCDEF",
  "persona": "maya",
  "messages": [{ "role": "user", "content": "Hi" }]
}
```

Server → client:

```json
{ "type": "start", "conversation_id": "c_01JABCDEF", "model": "qwen3-3b" }
{ "type": "token", "text": "Van" }
{ "type": "token", "text": "akkam" }
{ "type": "done", "elapsed_ms": 1830, "tokens": 42, "pending_action": null }
```

Error:

```json
{ "type": "error", "code": 3001, "message": "Engine unavailable" }
```

Rules:
- `ping` / `pong` every 25 s.
- Client disconnect → server generation cancel.
- Client reconnect → new request (resume illa in v1).
- One active generation per connection.

---

## 8. Voice

### `POST /voice/stt`

`multipart/form-data`:

| Field | Type | Notes |
|---|---|---|
| `audio` | file | WAV, PCM 16-bit, mono, 16 kHz |
| `lang` | text | `en` / `en-in` / `ta` |
| `duration_ms` | text | Optional |

Limits: 30 s, 5 MB.

```json
{ "text": "enna time", "lang": "en-in", "engine": "vosk" }
```

Silence → `{ "text": "", "lang": "en-in" }` (error illa).

### `POST /voice/tts`

```json
{
  "text": "Sollu da, enna venum?",
  "engine": "sapi",
  "voice": "heera",
  "lang": "en",
  "speed": 1.0
}
```

- `engine`: `sapi` | `piper` | `auto`
- `text` max 1 000 chars
- Response: `audio/wav` binary (22 050 Hz mono)
- Unavailable → `3004`

### `GET /voice/status`

```json
{
  "stt": { "engine": "vosk", "available": true, "languages": ["en", "en-in"] },
  "tts": {
    "engine": "sapi",
    "available": true,
    "voices": ["heera", "neerja", "zira"],
    "piper": { "available": false, "voices": [] }
  }
}
```

---

## 9. Laptop control

### 9.1 `GET /pc/status`

```json
{
  "ts": 1760100000,
  "cpu": { "percent": 12.5, "cores": 8, "freq_mhz": 3200 },
  "ram": { "total_gb": 15.3, "used_gb": 7.1, "percent": 46.4 },
  "gpu": { "name": "AMD Radeon 840M", "percent": null },
  "npu": { "name": "AMD XDNA", "tops": 50, "percent": null },
  "battery": { "percent": 82, "plugged": true, "seconds_left": null },
  "temps": { "cpu_c": 48.0 },
  "disks": [
    { "mount": "C:\\", "total_gb": 476.0, "used_gb": 210.0, "percent": 44.1 }
  ],
  "uptime_s": 12345
}
```

Unknown value = `null`. Client "—" kaattum.

### 9.2 `POST /pc/command`

```json
{
  "action": "app.open",
  "params": { "name": "notepad" },
  "confirm_token": null
}
```

Three possible responses:

**Done:**
```json
{ "status": "done", "result": { "message": "Opened notepad" } }
```

**Confirmation needed:**
```json
{
  "status": "needs_confirmation",
  "confirm_token": "cf_9f2...",
  "description": "Open application: notepad",
  "expires_in": 60
}
```

**Denied / blocked:**
```json
{ "status": "denied", "reason": "Action not allowed" }
```

### 9.3 `POST /pc/confirm`

```json
{ "confirm_token": "cf_9f2..." }
```

→ executes stored action → `{ "status": "done", "result": { ... } }`

Token single-use, 60 s, exact action + params-ku bind.

### 9.4 `POST /pc/cancel`

```json
{ "confirm_token": "cf_9f2..." }
```

→ `{ "status": "cancelled" }`

### 9.5 Action catalog

| Action | Params | Default permission | Notes |
|---|---|---|---|
| `app.list` | – | allow | Installed apps |
| `process.list` | – | allow | Running apps |
| `app.open` | `name` | ask | |
| `app.close` | `name` | ask | |
| `file.read` | `path` | allow* | *allowed roots only |
| `dir.list` | `path` | allow* | *allowed roots only |
| `file.write` | `path`, `content` | ask | max 256 KB |
| `file.delete` | `path`, `recursive` | ask | recycle bin prefer |
| `cmd.run` | `command`, `cwd` | ask | denylist check |
| `system.lock` | – | ask | |
| `system.sleep` | – | ask | |
| `system.shutdown` | `delay_s` (10–120) | ask | countdown + cancel |
| `system.volume` | `level` 0–100 | ask | |
| `system.mute` | `mute` bool | ask | |
| `system.screenshot` | `save_path` | ask | |
| `media.play` / `media.pause` / `media.next` / `media.prev` | – | ask | media keys |
| `clipboard.get` | – | ask | |
| `clipboard.set` | `text` | ask | max 64 KB |
| `notify` | `title`, `body` | allow | toast only |

**Allowed roots** (settings `permissions.allowed_roots`):
project root, Desktop, Documents, Downloads. System folders (`C:\Windows`, `C:\Program Files`, `AppData`) deny.

**`cmd.run` always blocked** (4003):
`format`, `diskpart`, `bcdedit`, `vssadmin delete`, `cipher /w`, `takeown /f C:\`, `icacls C:\ /reset`, `netsh advfirewall off`, `Set-MpPreference`, `net user`, `reg delete HKLM`, `del /f /s C:\`, `rm -rf /`, `Remove-Item -Recurse C:\`.

Path rules:
- Resolve absolute path, `..` reject.
- Symlink / junction target re-check.
- Denied root → `4002`.

Rate limit: 30 PC commands / min per device.

---

## 10. Events WebSocket

### `WS /ws/events?token=<token>`

Server → client every **2 s** (only while connected):

```json
{ "type": "status", "data": { "...": "same schema as /pc/status" } }
```

Other events:

```json
{ "type": "wake", "state": "listening" }
{ "type": "wake", "state": "idle" }
{ "type": "notification", "title": "Reminder", "body": "Drink water" }
{ "type": "server", "state": "shutting_down" }
{ "type": "ping", "ts": 1760100000 }
```

Client → server `{"type":"pong"}` optional.

Rules:
- Phone screen off / app background → socket close (battery).
- Reconnect backoff: 1, 2, 4, 8, 16, 30 s (cap).

---

## 11. Wake endpoints

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/wake/status` | – | `{ "listening": false, "clap": true, "name": true }` |
| POST | `/wake/listen` | `{ "seconds": 60 }` | `{ "listening": true, "expires_at": ... }` |
| POST | `/wake/stop` | – | `{ "listening": false }` |

`seconds` max 300. Server wake listener start pannum; wake aanaa events WS-la `wake` + desktop chat open.

---

## 12. Rate limits

| Scope | Limit | Lockout |
|---|---|---|
| Pair claim (per IP + device_id) | 5 / 10 min | 10 min |
| Auth failures | 10 / min | 1 min |
| General authenticated | 120 / min | 1 min |
| `/chat` | 20 / min | – |
| `/voice/stt` | 10 / min | – |
| `/pc/command` | 30 / min | – |
| `/wake/listen` | 5 / min | – |

Exceed → `429 / 1005`.

---

## 13. Confirm token lifecycle

1. `POST /pc/command` → permission `ask` → token create (60 s).
2. Client user-ku dialog kaattum.
3. Approve → `POST /pc/confirm` → execute → token delete.
4. Cancel / timeout → token delete, action never execute.
5. Token single-use. Replay → `4002`.

Confirm token store = server memory only. Server restart → pending actions cancel (safe default).

---

## 14. Compatibility

- `api: 1` — breaking change = `api: 2` + new base path `/api/v2`.
- New field add = old client ignore pannum.
- New endpoint add = old client use pannaadhu.
- Enum values extend aagalam; existing value remove koodadhu.
- `capabilities` list check pannitu client feature show pannum.

---

## 15. Implementation split

### Laptop (Python)

```
JARVIS\custom\server\
├─ __init__.py
├─ app.py            ← create_app(services)
├─ contracts.py      ← Protocol interfaces (Engine, Voice, Pc, Monitor, Pairing, Wake)
├─ models.py         ← Pydantic request/response
├─ auth.py           ← token store, hashing, rate limit
├─ pair.py           ← PIN / QR sessions
├─ confirm.py        ← confirm tokens
├─ lan.py            ← private IP guard
├─ routes\
│  ├─ health.py
│  ├─ pair.py
│  ├─ chat.py
│  ├─ voice.py
│  ├─ pc.py
│  ├─ wake.py
│  └─ events.py
└─ ws.py
```

Server **headless** — PySide6 import panna koodadhu. UI callbacks `contracts.py` Protocol moolam.

### Phone (Kotlin)

```
data\remote\
├─ ApiClient.kt
├─ MayaApi.kt
├─ Dto.kt
├─ ChatSocket.kt
├─ EventsSocket.kt
├─ DiscoveryClient.kt
├─ PrivateNetworkInterceptor.kt
└─ ErrorMapper.kt
```

---

## 16. Security checklist (implementation time)

- [ ] Token plain text disk-la illa (hash only)
- [ ] PIN constant-time compare
- [ ] PIN attempts + lockout
- [ ] QR single-use + TTL
- [ ] Revoked device → immediate 401
- [ ] Private IP guard
- [ ] Confirm token single-use + TTL
- [ ] Path traversal + symlink guard
- [ ] Command denylist
- [ ] Rate limits
- [ ] No personal data in logs
- [ ] No cloud calls
- [ ] `DEVARAJ\` folder never served
- [ ] `.env` never served
- [ ] Server error detail client-ku illa

---

## 17. Changelog

| Version | Date | Change |
|---|---|---|
| v1 | 2026-11-17 | Initial contract — pairing, chat, voice, PC control, events, wake |
