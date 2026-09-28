# F.R.I.D.A.Y. 3.0 — Voice / STT / TTS Architecture Specification
**Subsystem**: Acoustic Perception & Neural Synthesis (`friday_core/voice/`, `friday_ui/core/engine.py`)  
**Hardening Status**: ZERO-TRUST FORENSIC HARDENED  
**Date**: September 2026  
**Scope Gate**: UI & Agent Architecture FROZEN. Subsystem hardened strictly within Voice/STT/TTS boundaries.

---

## 1. High-Level Subsystem Architecture

The voice subsystem provides deterministic, dual-tier voice interaction (hands-free wake word and push-to-talk) with acoustic duplex barge-in, multi-engine fallback, and strict isolation from the primary text chat channel.

```
                              ┌────────────────────────────────────────┐
                              │            PHYSICAL HARDWARE           │
                              │  Microphone Array / Audio Input Device │
                              └───────────────────┬────────────────────┘
                                                  │
                                                  ▼
                              ┌────────────────────────────────────────┐
                              │          AUDIO CAPTURE STREAM          │
                              │ 16kHz, Mono, 16-bit PCM (Blocking API) │
                              └───────────────────┬────────────────────┘
                                                  │
                                                  ▼
                              ┌────────────────────────────────────────┐
                              │        VOICE ACTIVITY DETECTION        │
                              │ - Adaptive Ambient Floor Tracking      │
                              │ - Transient Click Rejection (<0.20s)   │
                              │ - Max Duration Cap (14.0s)             │
                              │ - Auto-Gain Control (AGC)              │
                              └───────────────────┬────────────────────┘
                                                  │
                                                  ▼
                              ┌────────────────────────────────────────┐
                              │        SPEECH-TO-TEXT (STT)            │
                              │ Tier 1: Local CPU faster-whisper (int8)│
                              │ Tier 2: Online Google STT Fallback     │
                              │ Timeout: 8.0s | Cancel Token Guarded   │
                              └───────────────────┬────────────────────┘
                                                  │
                                                  ▼
                              ┌────────────────────────────────────────┐
                              │       CANONICAL TRANSCRIPT CLEAN       │
                              │ Normalization & Duplicate Suppression  │
                              └───────────────────┬────────────────────┘
                                                  │
                                                  ▼
                              ┌────────────────────────────────────────┐
                              │          VOICE SECURITY GATE           │
                              │ - Prompt Injection Defense             │
                              │ - Destructive OS Directive Gating      │
                              │ - Anti-False-Success Evidence Protocol │
                              └───────────────────┬────────────────────┘
                                                  │
                                                  ▼
       ══════════════════════════════════════════════════════════════════════════════
                            IDENTICAL MODEL-DRIVEN PIPELINE
                                `brain.query_llm(...)`
       ══════════════════════════════════════════════════════════════════════════════
                                                  │
                                                  ▼
                              ┌────────────────────────────────────────┐
                              │           ASSISTANT RESPONSE           │
                              │ Delivered directly to UI Chat Bubble   │
                              │ (Chat never depends on TTS Health)     │
                              └───────────────────┬────────────────────┘
                                                  │
                                                  ▼
                              ┌────────────────────────────────────────┐
                              │        TTS TEXT SANITIZATION           │
                              │ - Strip `<think>...</think>` tags      │
                              │ - Strip `[TOOL: ...]` & trace logs     │
                              │ - Strip code blocks, backticks, URLs   │
                              │ - Normalize acronyms, symbols & emojis │
                              └───────────────────┬────────────────────┘
                                                  │
                                                  ▼
                              ┌────────────────────────────────────────┐
                              │        TEXT-TO-SPEECH (TTS)            │
                              │ Tier 1: Local Kokoro-82M ONNX          │
                              │ Tier 2: Cloud Neural Edge-TTS          │
                              │ Tier 3: In-process Windows SAPI COM    │
                              └───────────────────┬────────────────────┘
                                                  │
                                                  ▼
                              ┌────────────────────────────────────────┐
                              │        AUDIO PLAYBACK & DUPLEX         │
                              │ - PyGame Mixer Stream Playback         │
                              │ - Acoustic HUD Level Visualizer        │
                              │ - Barge-In Interruption Monitoring     │
                              │ - 0.45s Post-Speech Echo Cooldown      │
                              └────────────────────────────────────────┘
```

---

## 2. Core Architectural Invariants

### Invariant 1: Complete Text Chat Isolation
- Text chat **never** depends on microphone availability or state.
- If audio devices are missing, disconnected, or erroring, typed commands proceed without latency or failure.
- If STT crashes, typed chat is completely unaffected.

### Invariant 2: Non-Blocking TTS Failure Tolerance
- Assistant responses are rendered to the GUI text stream **before and independently** of TTS synthesis.
- A failure in audio synthesis, device loss, or playback buffer overflow **never** invalidates, deletes, or delays the text response.
- Speech errors are logged to forensics and emitted as non-fatal notifications.

### Invariant 3: Identical Agent Pipeline Parity
- Spoken transcripts enter the exact same `query_llm` agent path as typed text.
- No separate voice-only keyword router or bypass exists.
- The main LLM possesses sole authority over tool calling, research delegation, desktop automation, and response synthesis.

### Invariant 4: Zero-Trust Security Boundary
- All voice transcripts are treated as **untrusted user input**.
- Destructive commands (e.g., formatting disks, mass deletion) and prompt injections are strictly intercepted before execution.
- Anti-false-success gating enforces that transcription success is strictly separated from tool execution success and verification success.

---

## 3. Subsystem Component Specifications

### 3.1 Device Manager (`friday_core/voice/device_manager.py`)
- **Enumeration**: Uses `sounddevice.query_devices()` to map physical and virtual hardware.
- **Negotiation**: Probes candidate sample rates `[16000, 44100, 48000, 24000, 22050, 8000]` to guarantee stable stream initialization.
- **Failover**: Falls back from invalid configured device IDs to system defaults automatically without process termination.

### 3.2 Voice Activity Detection (`friday_core/voice/vad.py`)
- **Dynamic Floor Tracking**: Continuously adapts `ambient_rms` during silence (bounded between `5.0` and `120.0` RMS to avoid noise floor runaway).
- **Transient Rejection**: Discards noise bursts shorter than `0.20s` (keyboard taps, desk thumps, mouse clicks).
- **Runaway Ceiling**: Caps uninterrupted speech recording at `14.0s`, forcing closure and transcription.
- **Pause Tolerance**: Configurable silence timeout (`1.4s`) permits natural conversational breathing and thinking pauses.
- **Auto-Gain Control (AGC)**: Cleans and normalizes low-volume speech buffers to 26,000 peak amplitude without clipping.

### 3.3 Speech-to-Text (`friday_core/voice/stt.py`)
- **Tier 1 (Offline)**: Local CPU `faster-whisper` (`tiny.en` / `base.en`) with `int8` quantization for sub-second offline recognition.
- **Tier 2 (Cloud)**: Online Google Speech Recognition fallback when local models are unavailable.
- **Bounds**: Hard timeout limit of `8.0s`.
- **Cancellation**: Cooperative `threading.Event` tokens checked at stream ingestion and segment emission.
- **Normalization**: Strips extraneous whitespace, preserves technical terms and punctuation cadence.

### 3.4 Text-to-Speech (`friday_core/voice/tts.py`)
- **Tier 1 (Offline)**: Kokoro-82M ONNX neural speech (`kokoro-v1.0.int8.onnx`, `voices-v1.0.bin`) executing locally on CPU.
- **Tier 2 (Cloud)**: Microsoft Edge-TTS neural cloud voices (`en-US-AriaNeural`, etc.).
- **Tier 3 (Local Fallback)**: Windows SAPI COM `SpVoice` (zero network, zero dependency).
- **Sanitization**: Strips internal thoughts (`<think>...</think>`), tool execution traces (`[TOOL: ...]`), code blocks, backticks, and URLs.
- **Pipelined Prefetching**: Synthesizes sentence chunk $N+1$ in background while sentence chunk $N$ is actively playing through mixer.

### 3.5 Interruption & Echo Defense (`friday_core/voice/interruption.py`)
- **Acoustic Barge-In**: Checks incoming microphone frames during assistant speech. If user speech RMS exceeds threshold (`ambient_rms * 2.8`), playback is halted instantly and speech buffers are purged.
- **Reverberation Cooldown**: Imposes a `0.45s` mute window after assistant speech finishes (`MIC_COOLDOWN_AFTER_SPEECH`) to ensure speaker audio reverb is not re-transcribed as user input.

### 3.6 Deduplication Defense (`friday_core/voice/deduplicator.py`)
- **Temporal Window**: Suppresses identical utterances received within `2.5s` of the previous turn.
- **Substring Echo Guard**: Blocks partial phrases echoing active prompts within temporal proximity.
- **History Pruning**: Memory is tightly bounded to recent timestamps, avoiding memory leaks.
