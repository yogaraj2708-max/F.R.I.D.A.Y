# Untested / Unverified Features (Lacking Live Physical Evidence)

Per Rules 0.12, 0.19, 0.20, 0.21, 39, and 51, the following features cannot be marked PASS because physical hardware or long-duration soak environments were unavailable:

1. **Interactive Browser DOM Actions (F-027)**
   - *Current State*: HTTP web page fetching and parsing (`F-014`) pass 100% with live network tests.
   - *Unverified*: Real interactive browser DOM control (clicks, typing into form fields, scrolling, popup handling in Chromium/Edge) was not executed live against a running browser process. Per Rule 0.19 ("Do not claim browser support if only HTTP fetching exists") and Rule 8, this remains **UNVERIFIED**.

2. **Physical Audio Acoustic Round-Trip (F-003) & Duplex Wake Word (F-032)**
   - *Current State*: Voice loop, PyAudio integration, VAD, Whisper STT integration, and edge-tts synthesis pass programmatic and unit tests.
   - *Unverified*: A physical microphone transducer receiving live acoustic sound and a physical speaker producing audible playback in a closed-loop acoustic test was not performed (Rule 0.21: "Do not claim microphone support if a real microphone→STT→reasoning→TTS→speaker test has not completed"). Status: **PARTIALLY VERIFIED / UNVERIFIED**.

3. **Continuous 4-Hour Soak & Memory Leak Test (F-042)**
   - *Current State*: Short-term stress tests and 24-suite regression tests passed with zero deadlocks and zero memory corruption.
   - *Blocked*: Rule 39 strictly requires: "minimum 4-hour soak where environment permits... Zero-leak evidence required for PASS." This was not executed due to audit session duration limits. Status: **BLOCKED**.

4. **Live Physical Scanned Document OCR (F-030)**
   - *Current State*: OCR helper modules exist, and visual text extraction via `qwen2.5vl:3b` in the specialist vision pipeline is fully operational (verified in `F-031`).
   - *Unverified*: Optical recognition on live physical flatbed/feeder paper scanner hardware was not tested on physical scan devices. Status: **UNVERIFIED**.
   - *Note on F-031 (Vision Model Analysis)*: **PASS**. The specialist vision architecture (`qwen2.5vl:3b` -> structured `ImageContext` -> main model handoff with grounded follow-ups) was verified end-to-end against live Ollama with 100% pass rate across 7 runtime scenarios.

5. **Clean-Machine Packaged Build Validation (F-038)**
   - *Current State*: `FRIDAY_3.0.spec` and `build_exe.py` are present and compile cleanly.
   - *Unverified*: Deploying the resulting `.exe` installer onto a clean Windows machine without Python or development tools installed has not been verified (Rules 50, 51). Status: **UNVERIFIED**.
