# Tamil Voice (Piper)

Tamil TTS voice files inga irukkum. Ellame **offline** — cloud illa.

## Installed voice

| File | Purpose |
|---|---|
| `ta_IN-ValluvarNeural-medium.onnx` | Tamil Piper voice (VITS, 22.05 kHz) |
| `ta_IN-ValluvarNeural-medium.onnx.json` | Voice config (phonemes, inference params) |

- Source: <https://huggingface.co/Jeyaram-K/piper-tamil-voices>
- Voice: `ta_IN-ValluvarNeural-medium`
- License: Apache-2.0 (see the Hugging Face model card)
- Runtime: `piper-tts` Python API (`PiperVoice.load(...).synthesize_wav(...)`).
  The piper 1.8 CLI has a file-output bug on this machine, so Maya uses the API.

## Re-install / extra voices

1. Put any Piper Tamil `.onnx` + `.onnx.json` pair in this folder.
2. Maya picks the first `.onnx` file (sorted by name).
3. English voices go in `../english/` — Tamil never falls back to an English voice.

Tamil TTS code path: `JARVIS/custom/tools/voice.py` (`PiperTTS`) and
`LAPTOP/windows/app/services/voice_service.py` (`VoiceAdapter`).
