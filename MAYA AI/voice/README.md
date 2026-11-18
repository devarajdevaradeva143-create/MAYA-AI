# Voices

Maya AI voice files inga irukkum.

```
voices/
├─ tamil/     → Tamil voice (Piper .onnx)
├─ english/   → English voice
└─ README.md
```

## Windows vs Fedora — voice change aaguma?

**Voice file (.onnx) = same** — rendu OS-layum work aagum ✅
**Piper binary mattum vera:**
- Windows → `piper.exe`
- Fedora → `piper` (Linux binary)

So voice **maaradhu** — same Tamil voice dhaan. Engine binary mattum OS-kku vera.

- Windows: Piper + SAPI fallback
- Fedora: Piper only

Status: Placeholder — voice files next step.
