# KNOWN SYSTEM LIMITATIONS & BOUNDARIES

### 1. Hardware Memory & Model Sizing Constraints
- **Host RAM Utilization**: The host workstation has 16.0 GB RAM total, of which ~14.0 GB is utilized under full desktop workload.
- **VRAM Boundary**: The GPU has ~4.0 GB VRAM available. The primary model `qwen3.5:9b` (Q4_K_M) requires 6.28 GB memory, resulting in ~18 layers offloaded to GPU and remaining layers evaluated on CPU/System RAM.
- **Latency Impact**: On cold start or complex multi-tool synthesis turns, inference throughput operates at ~2–4 tokens/sec, causing turn completion times of 40–90 seconds for large queries.
- **Mitigation**: Staging the streaming chat bubble immediately (`stream_started`) and updating live HUD and bubble status (`status_updated`) provides continuous visual feedback so the user is never left in an unobservable waiting state.

### 2. Multi-Hour Continuous Soak Testing
- **Status**: **UNVERIFIED**
- **Rationale**: While isolated regression and component soak suites execute and pass, an unmonitored 24-hour continuous burn-in soak test has not been executed in this interactive development pass.

### 3. Physical Hardware Peripheral Disconnection
- **Status**: **UNVERIFIED**
- **Rationale**: Software audio fallback when PyAudio reports missing input devices is verified via mock injection in `tests/test_voice_engine.py`, but physical USB disconnect during active DMA capture requires physical hardware manipulation.
