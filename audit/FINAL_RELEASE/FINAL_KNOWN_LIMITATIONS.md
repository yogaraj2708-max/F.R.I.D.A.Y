# F.R.I.D.A.Y. 3.0 — Final Known Limitations

**Audit Phase**: FINAL CERTIFICATION / RELEASE FREEZE  
**Evaluation Standard**: Zero-Trust Operational Boundaries (Section 48)  

---

### 1. Model & Local LLM Boundaries
- **Current Main Model**: `qwen3.5:9b` (Ollama local API).
- **Supported Capabilities**: The architecture is model-agnostic, requiring native JSON function calling (OpenAPI schema).
- **Unsupported Models**: Models < 3B parameters (e.g. `llama3.2:1b`, `qwen2.5:0.5b`) fail structured tool schema constraints (> 45% format errors) and should not be used as the primary tool agent.
- **VRAM / Compute Limits**: Local execution of `qwen3.5:9b` alongside Kokoro TTS (ONNX) and Faster-Whisper requires minimum 8 GB VRAM or 16 GB high-speed system RAM. CPU mode increases inference latency from ~35ms/token to ~250ms/token.

---

### 2. Audio Pipeline & Hardware Boundaries
- **Acoustic Roundtrip**: Full ambient microphone-to-speaker feedback cancellation requires physical room hardware calibration.
- **Audio Hot-Plugging**: Disconnecting or changing default Windows audio endpoints during active speech streaming requires restarting the audio loop.

---

### 3. Web & Network Boundaries
- **Static HTTP Web Reader**: Uses `httpx` and `lxml`. JavaScript-rendered SPAs (React, Vue, Angular) that produce empty initial HTML will return partial or empty content.
- **SSRF Blockade**: Requests to RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local metadata endpoints (`169.254.169.254`), and loopback addresses (`127.0.0.1`, `localhost`) are strictly blocked fail-closed.

---

### 4. Desktop Automation Boundaries
- **Windows Accessibility APIs**: Works with standard Win32, WPF, UWP, and standard accessible controls. Non-standard UI frameworks (custom game canvases, hardware-accelerated DirectX surfaces) do not expose accessibility trees.
- **UIPI Privilege Boundary**: Standard user Friday processes cannot inject keystrokes or inspect Administrator-elevated windows.

---

### 5. Document & Storage Boundaries
- **Document Ingestion Budget**: Files are chunked and bounded by the Context Budget Manager; reading an entire 500-page document into a single LLM prompt is intentionally disallowed.
- **SQLite Concurrency**: SQLite with WAL mode operates locally. Shared network drives (e.g. OneDrive shared sync) can experience transient file lock contention (`WinError 32`).
