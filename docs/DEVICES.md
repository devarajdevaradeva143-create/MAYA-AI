# Multi-device pairing + signed sync bundles

Maya can pair a **trusted device** (another laptop, a phone, a USB stick) and
exchange **signed JSON bundles** with it. There is no server and no cloud
account: you move the bundle yourself over USB, a local share, or any path you
trust.

> **Signed, not encrypted.** A bundle proves it came from a paired device and
> was not changed in transit. Anyone who has the bundle can read its contents.
> Keep private files out of bundles unless the transfer path itself is safe.

## Commands

```powershell
# 1. On the first laptop: generate a 128-bit pairing code (shown once)
maya devices pair phone
# -> Pairing code (shown once, not stored): 7c1f...e2  (32 hex characters)

# Or enter your own code with hidden input (16+ characters)
maya devices pair phone --ask-code

maya devices list                  # names, display ids, last sync
maya devices revoke phone --yes    # forget the device; old bundles stop importing

# 2. Export files for that device (hidden prompt for the code)
maya devices export phone --source "..\MAYA AI\knowledge" --out D:\maya\bundle.json

# 3. On the other Maya install: pair the same name with the same code, then import
maya devices pair phone --ask-code
maya devices import D:\maya\bundle.json --dest "D:\MayaInbox"
```

`--code VALUE` still works for automation, but it exposes the long-lived code
in shell history and process lists. Prefer the default hidden prompt, or
`--ask-code` when pairing. The code is never written to the bundle or to
`devices.json`.

`import` refuses to replace existing files unless you pass `--overwrite`.

## What is stored

`MAYA AI/memory/offline/devices.json` (override: `MAYA_DEVICES_STORE`):

```json
{
  "version": 1,
  "devices": {
    "phone": {
      "name": "phone",
      "id": "9d1f...",
      "kind": "bundle",
      "code_algo": "pbkdf2_sha256",
      "code_iterations": 600000,
      "code_salt": "...",
      "code_hash": "...",
      "created": 1760000000,
      "last_sync": 1760000100
    }
  }
}
```

Only a salted PBKDF2-SHA256 hash (600,000 iterations) of the pairing code is
stored. The `id` is a random display identifier — it is **not** derived from the
code and is not used for authentication. Revoking a device removes the record,
so its bundles can no longer be imported even if the file is still on disk.

## Bundle format

```json
{
  "format": "maya-device-bundle",
  "version": 1,
  "device": "phone",
  "created": 1760000100,
  "kdf": {"algo": "pbkdf2_sha256", "iterations": 600000, "salt": "..."},
  "files": [
    {"path": "notes/a.txt", "size": 12, "sha256": "...", "data": "<base64>"}
  ],
  "hmac": "..."
}
```

The HMAC-SHA256 covers a canonical JSON encoding of every field except `hmac`.
The key is derived from the pairing code with PBKDF2-SHA256 (600k iterations,
fresh random salt per bundle). Both installations that pair the same name and
code derive the same key, so they accept each other's bundles without sharing a
second secret. Import checks, in order:

1. bundle file size cap (before JSON parsing), then format/version
2. sender name is still paired
3. pairing code hash (with the record's stored iteration count)
4. KDF algorithm, iteration count and salt length (no downgrade)
5. HMAC signature
6. file count and per-file declared size (before base64 decode)
7. base64 length, decoded size and SHA-256
8. path is relative; no `..`, drive, colon/ADS, control characters, reserved
   Windows names, or trailing dots/spaces
9. resolved target stays under `--dest`; no duplicate or file/folder-conflicting
   bundle paths; destination parents are not files
10. existing-file conflicts (unless `--overwrite`)

Validation happens before any final write. Files are staged inside `--dest`;
existing files are moved to a backup directory and restored if a later move
fails. A successful import leaves no staging files.

**Replay:** bundles have no nonce or anti-rollback counter. Re-importing an old
signed bundle with `--overwrite` restores its old contents. Delete bundles after
use if rollback matters.

## What is refused by default

Export refuses these unless `--allow-sensitive` is passed:

- `.env` / `.env.*`
- `devices.json`, `security.json`, `biometrics.json`
- `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.kdbx`, `id_rsa*`, `id_ed25519*`
- anything inside `DEVARAJ/`, `.ssh/`, `.gnupg/`

Symlinks and Windows directory junctions are never followed. A junction inside
a selected folder is skipped, so files outside the selected tree cannot slip
into a bundle.

## Limits

`MAYA AI/config/settings.yaml`:

```yaml
devices:
  bundle:
    max_files: 200
    max_mb: 25
```

Both export and import enforce these. Export checks each file's `stat()` size
before reading it; import caps the JSON read and checks each declared size
before decoding base64. A bundle larger than the receiving laptop's limit is
refused even when its signature is valid.

## Privacy

- Everything is local; no network call is made by pairing or bundling.
- Offline memory is never sent automatically — you choose the `--source` paths.
- `DEVARAJ/`, `.env` and security stores are refused unless you explicitly pass
  `--allow-sensitive`; even then, the bundle is plaintext.
- The bundle is **not encrypted**; use it on USB/local shares, not public links.
- A stolen bundle without the pairing code cannot be imported (the HMAC key is
  derived from the code), but its file contents are readable.
- The store and bundle files are written with owner-only permissions where the
  OS supports it.

## Troubleshooting

| Message | Meaning |
|---|---|
| `Pairing code must be at least 16 characters` | use a longer code (spaces are stripped) |
| `Device 'x' is already paired` | `devices revoke x` first, then pair again |
| `Pairing code is wrong` | same code must be used on both installations |
| `Bundle signature is invalid` | edited/corrupted file, wrong code, or created before re-pairing with a new code |
| `Sender 'x' is not paired on this laptop` | pair the device here first |
| `N file(s) already exist` | choose another `--dest` or add `--overwrite` |
| `Bundle limit is N files` | split the export or raise the config limit |
| `Unsafe path` | absolute/`..`/drive/ADS/reserved name — rejected |
| `Bundle paths conflict as file/folder` | a trusted bundle tried to create both `a` and `a/b` |
| `Refusing to bundle file '.env'` | add `--allow-sensitive` only if intended |
| `Symlinks/junctions are not bundled` | select the real folder instead |
| `Bundle KDF parameters are not allowed` | bundle was made with unsupported settings |
| `Bundle file is larger than ...` | file fails the size cap before parsing |

## Tests

`custom/tests/test_devices.py` — pairing/hash/revoke, whitespace and weak codes,
cross-install roundtrip, export limits, sensitive deny-list, junction/symlink
containment, wrong code, unpaired sender, re-pairing, tampering, KDF downgrade,
path traversal/ADS/reserved names, duplicate/prefix paths, write-failure
rollback, overwrite, corrupt-store preservation, CLI prompts and terminal
escape sanitising.

## Status

Pairing and signed bundles are implemented and tested. **Transport is manual**
(USB / local share); automatic Wi-Fi transfer is still future work. Discovery,
ADB and Wi-Fi helpers remain available but are separate from this trusted
pairing path.
