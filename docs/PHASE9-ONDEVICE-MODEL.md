# Maya Mobile — Phase 9: On-Device Model (pending)

Status: **Implemented (native).** NDK 27.2 + CMake 3.22 wired; llama.cpp linked; JNI (loadModel/generate/cancel/unload) built for arm64 + x86_64. Model file + chat fallback optional.

## What's needed
1. Install NDK + CMake:
   ```powershell
   $sdk = "$env:LOCALAPPDATA\Android\Sdk"
   & "$sdk\cmdline-tools\latest\bin\sdkmanager.bat" "ndk;27.2.12479018" "cmake;3.22.1"
   ```
2. Add to `app/build.gradle.kts`:
   - `externalNativeBuild { cmake { path = file("src/main/cpp/CMakeLists.txt") } }`
   - NDK version, abiFilters = ["arm64-v8a", "x86_64"]
3. Place llama.cpp under `app/src/main/cpp/llama.cpp` (git submodule).
4. Write JNI wrapper `native-lib.cpp` exposing:
   - `loadModel(path)`, `generate(prompt, maxTokens, callback)`, `cancel()`, `unload()`
5. Kotlin side: `OnDeviceModelManager` (already scaffolded) + `LocalChatRepository` calling JNI via `external`/`System.loadLibrary`.
6. Copy a Qwen3 1.7B Q4 GGUF into `app/src/main/assets/models/` or download on first run into `filesDir/models/qwen3-1.7b-q4.gguf`.
7. Wire fallback in ChatViewModel: if laptop disconnected and model installed → use local; else show banner.

## DoD
- Model loads on arm64 device/emulator.
- Reply generated offline (airplane mode).
- Cancel + unload works.
- No crash on low memory (use `ComponentCallbacks2.onTrimMemory`).

## Current implementation
- `com.devaraj.maya.data.model.NativeLlama` JNI bridge (status/loadModel/generate/cancel/unload).
- `com.devaraj.maya.data.model.OnDeviceModelManager` (isInstalled, load, generate, unload, statusText).
- Native lib `libmaya_llama.so` built for arm64-v8a + x86_64.
- Chat fallback wiring into ChatViewModel is the remaining polish (optional).
