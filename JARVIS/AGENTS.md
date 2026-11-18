# AGENTS.md — JARVIS Code Rules

> Full guide: `..\AGENTS.md` (project root).
> Ithu code area mattum.

## Rules

1. `OpenJarvis\` = **read-only** ❌
2. Namma code ellam `custom\` la mattum ✅
3. OpenJarvis change venum-na → `patches\*.patch` ✅
4. Config = `..\MAYA AI\config\settings.yaml` (hardcode illa)
5. Secrets = `.env` (commit pannaadhu)
6. Update: `scripts\update_openjarvis.ps1` / `.sh`

## Folder meanings

| Folder | Enna |
|---|---|
| `OpenJarvis\` | Official engine — edit pannaadhu |
| `custom\` | Namma Maya code |
| `custom\persona\` | Persona loading |
| `custom\tools\` | Monitoring, reminders, knowledge |
| `custom\plugins\` | OpenJarvis plugins |
| `patches\` | Engine changes |
| `backups\` | Update history |
| `scripts\` | Update / setup |

## Privacy

- Personal details cloud-kku pogaadhu 🔒
- Offline → Online data pogaadhu ❌
- Permission illama edit / delete / command illa ⚠️
