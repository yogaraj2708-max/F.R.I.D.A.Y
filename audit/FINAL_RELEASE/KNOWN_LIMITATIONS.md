# F.R.I.D.A.Y. 3.0 — Known Limitations

**Audit Phase**: FINAL SYSTEM INTEGRATION / ZERO-TRUST RELEASE GATE  
**Date**: 2026-09-28  

The following limitations are intrinsic constraints of the current environment, hardware architecture, and implementation boundaries. These are **not disguised bug fixes**, but documented boundaries of operation.

---

## 1. Model Support & Local LLM Requirements

1. **Current Primary Model**:
   - The user-selected primary model is `qwen3.5:9b`.
   - The agent architecture is model-agnostic, but requires an Ollama or OpenAI-compatible endpoint that supports native JSON tool calling (OpenAPI function definitions).
2. **Unsupported Models**:
   - Extremely small models (< 3B parameters, e.g. `llama3.2:1b`, `qwen2.5:0.5b`) fail structured tool schema validation (> 45% format deviations or hallucinated tool arguments) and should only be used for conversational chat or fast-tier synthesis.
   - Models lacking native tool-calling capabilities will fail to invoke tools deterministically.
3. **Local Compute & VRAM Requirements**:
   - Running `qwen3.5:9b` (KV context 8192) alongside Kokoro TTS (ONNX) and Faster-Whisper requires a minimum of 8 GB VRAM (GPU) or 16 GB high-speed system RAM (CPU mode). On CPU-only systems, generation latency increases from ~35ms/token to ~250ms/token.

---

## 2. Hardware Dependencies & Audio Pipeline

1. **Physical Microphone & Speaker Hardware**:
   - Acoustic round-trip (ambient sound $\to$ transducer $\to$ driver $\to$ STT $\to$ LLM $\to$ TTS $\to$ speaker $\to$ room) requires active physical hardware. In headless environments, virtual audio devices or programmatic fixtures must be used.
2. **PyAudio / PortAudio OS Device Management**:
   - On Windows, audio device index changes (e.g. unplugging a USB headset) require re-enumerating devices. Hot-plugging audio devices during active streaming requires restarting the voice loop.
3. **Physical Optical Scanner Hardware**:
   - Scanned physical document OCR requires external TWAIN/WIA scanner hardware or pre-captured camera images.

---

## 3. Web & Network Boundaries

1. **HTTP Web Reader vs. Interactive Browser**:
   - The web subsystem uses static HTTP retrieval (`httpx` + HTML text extraction).
   - Single Page Applications (SPAs) relying heavily on client-side client JavaScript hydration (e.g. React/Vue apps that render blank HTML until JS loads) will return partial or empty text bodies.
   - Interactive DOM automation (clicking buttons, filling multi-step web forms, solving CAPTCHAs) is not supported.
2. **SSRF & Private Network Guardrails**:
   - Requests to RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local metadata endpoints (`169.254.169.254`), and loopback addresses (`127.0.0.1`, `localhost`) are strictly blocked by the security risk gate.

---

## 4. Desktop Automation Boundaries

1. **Windows UI Automation API Limitations**:
   - Desktop automation relies on `pywinauto` / `uiautomation` and accessibility trees.
   - Non-standard UI applications (games, DirectX overlays, custom canvas rendering, Electron apps with disabled accessibility flags) do not expose semantic controls, falling back to window-level focus or failing control resolution.
2. **Privilege Isolation (UAC)**:
   - F.R.I.D.A.Y. running under standard user permissions cannot inspect or type text into elevated (Administrator / SYSTEM) windows due to Windows User Interface Privilege Isolation (UIPI).

---

## 5. Storage, RAG & Vector Database

1. **Local SQLite & Chroma Storage**:
   - Database operations use SQLite with Write-Ahead Logging (WAL) mode. Heavy multi-process concurrent access on network-attached storage (e.g. OneDrive shared folders) can encounter transient file lock contention (`WinError 32`).
2. **Document Ingestion Limits**:
   - Raw documents are capped to prevent context window explosion. Multi-hundred page documents are chunked and retrieved via hybrid BM25 + embedding ranking; reading an entire 500-page book in a single LLM prompt is intentionally disallowed by the Context Budget Manager.

---

## 6. Long-Run Soak & Stress

1. **Soak Duration**:
   - Verified up to 20-30 consecutive cycles per subsystem. Uninterrupted 24/7 continuous operation has not been validated in a dedicated multi-day burn-in environment.
