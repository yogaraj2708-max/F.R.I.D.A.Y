# Pre-4B Project State

**Evaluation Standard**: Zero-Trust Forensic Reconstruction  
**Reconstruction Scope**: F.R.I.D.A.Y. 3.0 immediately prior to the dual-model Qwen3.5:9B + Qwen3.5:4B implementation  
**Reference Baseline Commit**: [`960eacc`](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice) (`feat(release): F.R.I.D.A.Y. 3.0 Zero-Trust Certification and Release Freeze`)  
**Production Code Changes**: NONE  

---

## 1. Known Working Architecture

Immediately prior to the Qwen3.5:4B dual-model initiative, F.R.I.D.A.Y. 3.0 was structured as a unified, single-decision-maker desktop agent with strict model-agnostic boundaries:

```
                            USER / OPERATOR
                                   │ (Typed text / Audio utterance)
                                   ▼
                   F.R.I.D.A.Y. UI / VOICE ENGINE
        (PySide6 Fluent HUD, Silero VAD, Faster-Whisper, Kokoro TTS)
                                   │
                                   ▼
                     USER-SELECTED MAIN AGENT MODEL
                          (Primary: qwen3.5:9b)
                    Sole tool-selection authority
                                   │
              ┌────────────────────┴────────────────────┐
              ▼                                         ▼
         Direct Chat                            Native Tool Call
    (Streaming Markdown + TTS)                  (JSON OpenAPI Schema)
                                                        │
                                                        ▼
                                            PYTHON AGENT TOOL BRIDGE
                                            (Schema compilation & trace)
                                                        │
                                                        ▼
                                            SECURITY & RISK GATEKEEPER
                                            (SSRF, Traversal, Process deny)
                                                        │
                                                        ▼
                                            SUBSYSTEM EXECUTION & PEOV
                                            (Pre-Execute-Observe-Verify)
                                                        │
                                                        ▼
                                            SAME-MODEL REPLANNING LOOP
                                            (Evaluates physical readback)
```

### Architectural Tenets
1. **Single Cognitive Authority**: The user-selected main model was the sole intelligence that decided whether to answer directly or invoke tools. Python never used regex keyword scraping to force tool calls behind the model's back.
2. **Model Agnosticism**: No hardcoded model weights, tokens, or prompt formats existed in the main agent path. Model identity was resolved dynamically from settings.
3. **PEOV Cycle**: Every skill executed under the Precondition $\to$ Execute $\to$ Observe $\to$ Verify contract. Tool outcomes were cryptographically traced and verified via physical OS/disk/network inspection before returning to the model.
4. **Non-Blocking GUI**: All neural inference, audio generation, document parsing, and web fetching executed on dedicated `QThread` workers, maintaining a strict 60 FPS UI refresh rate.

- *Evidence Sources*: [FINAL_ARCHITECTURE.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_ARCHITECTURE.md) Sections 1 & 2; [RELEASE_CERTIFICATION.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/RELEASE_CERTIFICATION.md) Sections 1 & 3; `friday_ui/core/engine.py` (lines 4350–4430 at commit `960eacc`).

---

## 2. Main Model State

1. **Known Working Primary Model**: `qwen3.5:9b` running via the local Ollama API server (`http://localhost:11434`).
2. **Dynamic Model Resolution**:
   - Resolved via `settings.get("model", "qwen3.5:9b")` (fallback to `"llama3.2:3b"` in `DEFAULT_SETTINGS` of `friday_core/settings.py`).
   - The system was designed to allow changing the model string without breaking internal architecture.
3. **Runtime Capability Probing**:
   - Implemented in `FridayEngine.get_model_tool_capability_status()`: executed a live, harmless `test_echo` tool call before allowing native tool execution.
   - Statuses: `VERIFIED`, `UNAVAILABLE`, `BLOCKED`, `FAILED`, `UNVERIFIED`.
   - If a model failed the probe (e.g. models < 3B parameters such as `llama3.2:1b` or `qwen2.5:0.5b` exhibiting > 45% JSON format errors), `is_tool_capable` was set to `False`, tool schemas were withheld, and the model was treated safely as a text-only conversational model (`UNSUPPORTED_FOR_SELECTED_MODEL`) without crashing.
4. **Specialist Models**:
   - Visual tasks routed to dedicated vision specialist `qwen2.5vl:3b`.
   - The specialist extracted structured scene information, OCR, and bounding boxes into an `ImageContext` object.
   - The Main Agent Model (`qwen3.5:9b`) consumed the `ImageContext` data to formulate its answer; the vision model never superseded the main cognitive loop.

- *Evidence Sources*: [RELEASE_CERTIFICATION.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/RELEASE_CERTIFICATION.md) Section 1; [FINAL_KNOWN_LIMITATIONS.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_KNOWN_LIMITATIONS.md) Section 1; [FINAL_FEATURE_MATRIX.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_FEATURE_MATRIX.json) (Feature `F-002`); `friday_ui/core/engine.py` (lines 905–949 at commit `960eacc`).

---

## 3. Tool Calling

1. **Tool Specification & Discovery**:
   - Managed centrally by `AgentToolBridge` in `friday_core/skills/agent_bridge.py`.
   - Compiled OpenAPI-compliant function schemas directly from the `SkillRegistry` and system primitives:
     - `calculate`: Safe AST math evaluator (zero `eval()` usage).
     - `web_search`: DuckDuckGo live web query for breaking news and facts.
     - `web_fetch`: HTTP webpage content retriever with SSRF protection.
     - `deep_research`: Multi-source research dossier synthesizer with query decomposition.
     - `read_document` & `edit_document`: Ingests and surgically mutates PDF, DOCX, TXT, CSV files.
     - `inspect_image`: Interrogates attached screenshots via vision specialist.
     - `launch_app`, `inspect_ui`, `type_text`, `close_app`: UI automation primitives.
     - `system_telemetry`: CPU, RAM, battery, and process diagnostics.
     - `query_knowledge_base`: Semantic vector RAG search.
2. **Tool Dispatch & Provenance**:
   - The Main LLM emitted standard Ollama/OpenAI tool call objects (`name`, `arguments`, `id`).
   - Every tool execution was assigned a cryptographically unique `trace_id` (`trace-<uuid>`).
   - Gated by the `SecurityGatekeeper` before execution.
   - Emitted structured results back to the model with verified physical provenance (`[VERIFIED TOOL PROVENANCE | tool: <name> | status: SUCCESS | verification: VERIFIED | trace: <id>]`).
3. **Multi-Turn Replanning**:
   - Bounded agent loop (up to 5 turns).
   - If a tool failed or returned rejected verification, the error was packaged and handed back to the same model to replan or notify the user truthfully.

- *Evidence Sources*: `friday_core/skills/agent_bridge.py` (commit `960eacc`); [FINAL_SMOKE_RESULTS.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_SMOKE_RESULTS.json) (`3_native_tool`); [FINAL_FEATURE_MATRIX.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_FEATURE_MATRIX.json) (`F-003`, `F-004`).

---

## 4. Routing

1. **Cascading Hybrid Intent Router** (`friday_core/router/semantic_router.py`):
   - **Tier 0 (Deterministic Regex)**: Zero-latency (< 1ms) match for greetings and conversational pleasantries (`"hi"`, `"hello"`, `"good morning"`). Returned deterministic natural greetings (`"Hello Boss"`) without burning LLM inference or spinning up tools.
   - **Tier 1 (Centroid Embedding Classifier)**: Deterministic 384-dimensional Blake2b hashed projection vectors executed in < 0.2ms across 12 discrete skill intents (`media_control`, `desktop_audio`, `system_telemetry`, `system_time_date`, `desktop_action`, `app_launch`, `timer_clock`, `deep_research`, `weather`, `document_qa`, `web_reading`, `general_chat`).
   - **Tier 2 (Nano-Model Disambiguation)**: Optional local small decider model (~60ms) resolving borderline confidence scores (0.70–0.85).
   - **Tier 3 (Main Reasoning Fallthrough)**: Queries with open-ended or ambiguous semantics fell straight through to the main model (`qwen3.5:9b`) equipped with full tool-calling capabilities.
2. **Compound Intent Parsing** (`friday_core/agent/compound.py`):
   - Decomposed complex multi-clause user requests (e.g. `"Open notepad and type hello"`) into sequential PEOV DAG missions.
   - Prevented greedy regexes from consuming entire phrases as application targets.

- *Evidence Sources*: `friday_core/router/semantic_router.py` (commit `960eacc`); [ROUTING_MATRIX.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/ROUTING_MATRIX.json); [FINAL_BUG_LEDGER.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_BUG_LEDGER.json) (`BUG-001`, `BUG-002`).

---

## 5. Verified Features

From [FINAL_FEATURE_MATRIX.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_FEATURE_MATRIX.json) (28 audited features):

- **F-001**: Fluent Desktop Chat Interface — **PASS**
- **F-002**: Main Agent Model Resolution (`qwen3.5:9b`) — **PASS**
- **F-003**: Native Tool Calling & Schema Bridge — **PASS**
- **F-004**: Same-Model Cognitive Replanning — **PASS**
- **F-005**: Security Risk Gatekeeper — **PASS**
- **F-006**: Safe Calculation Engine (`safe_calculate`) — **PASS**
- **F-007**: Non-Blocking OS Telemetry (0.06ms polling) — **PASS**
- **F-008**: Live HTTP Web Fetch Reader — **PASS**
- **F-009**: Deep Research Engine & Multi-Vector Synthesis — **PASS**
- **F-010**: Research Cancellation & Watchdog Timeouts — **PASS**
- **F-011**: Document Parsing & Q&A (PDF, DOCX, TXT, CSV) — **PASS**
- **F-012**: Surgical In-Place Document Editor — **PASS**
- **F-013**: Vision Specialist Ingestion & Chat Isolation — **PASS**
- **F-014**: Desktop UI Automation (Notepad, Typing, PEOV) — **PASS**
- **F-015**: Software STT Pipeline (Faster-Whisper & VAD) — **PASS**
- **F-016**: Neural TTS Pipeline (Kokoro ONNX & Thought Scrubbing) — **PASS**
- **F-017**: Acoustic Barge-In Interruption Controller — **PASS**
- **F-021**: Persistent Domain-Isolated Memory & Readback Deletion — **PASS**
- **F-022**: Hybrid RAG Knowledge Base & Deduplication — **PASS**
- **F-023**: Data-Encapsulated Prompt Injection Defense — **PASS**
- **F-024**: Task Lifecycle Supervisor (14-State Machine) — **PASS**
- **F-025**: Context Budget Manager & Bounded Compaction — **PASS**
- **F-026**: Resource Governance & Bounded FIFO Eviction — **PASS**

*(Total Verified PASS: 23 features)*

- *Evidence Sources*: [FINAL_FEATURE_MATRIX.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_FEATURE_MATRIX.json); [RELEASE_CERTIFICATION.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/RELEASE_CERTIFICATION.md) Section 2.

---

## 6. Fixed Bugs

A total of 40 historical defects were resolved prior to the freeze as documented in [FINAL_BUG_LEDGER.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_BUG_LEDGER.json):

1. **BUG-001 (Chat Silence / Greeting Latency)**: Tier 0 fast path (<1ms) added to skip unnecessary LLM inference on greetings.
2. **BUG-002 (Compound Intent App Launcher)**: `CompoundIntentParser` implemented to break compound instructions into PEOV DAG missions.
3. **BUG-004 (Protected OS Process Termination)**: `PROTECTED_SYSTEM_PROCESSES` deny-list enforced, protecting 15 Windows binaries (`csrss.exe`, `lsass.exe`, `services.exe`, etc.).
4. **BUG-005 (Approval Token Replay Attacks)**: Single-use cryptographic nonces implemented with immediate invalidation upon consumption.
5. **BUG-006 (Path Traversal Escapes)**: Canonical `Path.resolve()` containment enforced against directory traversal escapes.
6. **BUG-007 (State Machine Concurrency Races)**: `threading.RLock()` synchronization added across all state machine transitions.
7. **BUG-008 (False Success on App Termination)**: Polling verification loop added verifying HWND destruction and process exit via `psutil`.
8. **BUG-009 (Standalone Typing Routing)**: Tier 1 typing interceptor added for direct `UITypeTextSkill` dispatch.
9. **PDF UI Freeze**: Isolated large PDF parsing to a background worker with throttled markdown rendering.
10. **Telemetry HUD Lag**: Optimized CPU telemetry from 100ms to 0.06ms via non-blocking cached counters.
11. **Thought Tag Speech Leak**: Added regex thought scrubber (`<think>.*?</think>`) stripping internal model reasoning from TTS audio output.
12. **Ollama Context Overflow**: Implemented `ContextBudgetManager` bounding prompt history under 7,000 tokens while preserving system prompts, active user instructions, and tool outputs.

- *Evidence Sources*: [FINAL_BUG_LEDGER.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_BUG_LEDGER.json); [KNOWN_BUGS_FIXED.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/KNOWN_BUGS_FIXED.md).

---

## 7. Remaining Bugs

From [FINAL_BUG_LEDGER.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_BUG_LEDGER.json) and [FINAL_RELEASE_BLOCKERS.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_RELEASE_BLOCKERS.md):

- **Open Bugs**: 0 code bugs open.
- **Partially Verified / Environmentally Constrained**:
  - `BUG-003` / `Blocker 1`: Real acoustic microphone-to-speaker transducer roundtrip cannot be verified in headless CI/virtual environments; relies on simulated audio streams and programmatic VAD.
  - Interactive Browser DOM Automation (`F-019`): Blocked; currently operates static HTTP reader (`web_fetch`), unable to interact with client-side JavaScript SPAs.

- *Evidence Sources*: [FINAL_BUG_LEDGER.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_BUG_LEDGER.json) lines 5–9; [FINAL_RELEASE_BLOCKERS.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_RELEASE_BLOCKERS.md).

---

## 8. Test Status

Immediately before the 4B work, the test suite stood as follows:

1. **End-to-End Smoke Certification**:
   - Executed via `scripts/run_final_certification_smoke.py`.
   - **13 of 13 smoke tests PASSED** (Hi, Calculator, Native Tool, Web Query, Deep Research, PDF, DOCX, Image, Notepad Automation, Voice Command, Memory Lifecycle, Cancellation, Restart Persistence).
2. **Dedicated Security Red-Team**:
   - Executed via `pytest tests/security/ tests/test_phase15_security.py ...`.
   - **32 of 32 tests PASSED** (SSRF, path traversal, process denial, approval nonces, prompt injection containment).
3. **Persistence and Resource Cleanup**:
   - Executed via `pytest tests/test_settings.py tests/test_session_store.py tests/test_memory_lifecycle.py tests/test_subprocess_cleanup.py tests/test_socket_cleanup.py`.
   - **18 of 18 tests PASSED**.
4. **Total Test Corpus**:
   - 169 test files tracked in `tests/` at commit `960eacc`.
   - Zero test failures across audited operational suites.

- *Evidence Sources*: [FINAL_SMOKE_RESULTS.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_SMOKE_RESULTS.json); [FINAL_SECURITY_RESULTS.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_SECURITY_RESULTS.json); `transcript.jsonl` steps 5803–5814.

---

## 9. Known Limitations

Documented in [FINAL_KNOWN_LIMITATIONS.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_KNOWN_LIMITATIONS.md) and [FINAL_RELEASE_BLOCKERS.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_RELEASE_BLOCKERS.md):

1. **Hardware / Resource Limits**:
   - `qwen3.5:9b` alongside Kokoro TTS (ONNX) and Faster-Whisper required a minimum of **8 GB VRAM** (or 16 GB high-speed system RAM). CPU fallback degraded inference latency from ~35ms/token to ~250ms/token.
   - Small models (< 3B parameters) failed structured tool schemas (> 45% format errors) and could not serve as the primary tool agent.
2. **Web / Browser Limitations**:
   - Static HTTP reader (`httpx` + `lxml`) could not render JavaScript-only Single Page Applications (SPAs).
3. **Desktop Automation Boundaries**:
   - Only standard Win32, WPF, UWP controls exposing accessibility trees were interactable; custom DirectX/game canvases were unsupported.
   - UIPI boundary: Standard user Friday process could not inject keystrokes or inspect Administrator-elevated windows.
4. **Audio Hardware Boundary**:
   - Audio hot-plugging (switching Windows audio devices during streaming) required restarting the voice loop.
5. **Release Blockers (Preventing Production Release Gate `YES`)**:
   - Blocker 1: Unverified Real Acoustic Microphone-to-Speaker Loop (CRITICAL)
   - Blocker 2: Interactive Browser DOM Automation (HIGH)
   - Blocker 3: Physical Scanned Paper OCR (HIGH)
   - Blocker 4: Continuous 4-Hour Uninterrupted Soak Stability (HIGH)
   - Blocker 5: Clean-Machine Packaged Build Validation (HIGH)

- *Evidence Sources*: [FINAL_KNOWN_LIMITATIONS.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_KNOWN_LIMITATIONS.md); [FINAL_RELEASE_BLOCKERS.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_RELEASE_BLOCKERS.md); [RELEASE_CERTIFICATION.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/RELEASE_CERTIFICATION.md) Section 8.

---

## 10. Planned Next Step Before 4B

Immediately prior to the user requesting the 4B dual-model work:

1. **The Codebase Was Formally Frozen**:
   - Recorded in [RELEASE_CERTIFICATION.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/RELEASE_CERTIFICATION.md) Section 9: `RELEASE_READY = NO`.
   - The freeze directive prohibited adding features, speculative fixes, or architectural redesigns.
2. **Planned Road-Map**:
   - Resolve the 5 physical/environmental release blockers on physical hardware:
     - Run physical workstation acoustic microphone-to-speaker verification.
     - Execute the continuous 4-hour soak burn-in run.
     - Test the standalone PyInstaller compiled bundle on a clean Windows VM lacking development runtimes.
     - Investigate interactive DOM automation or maintain static reader boundaries.
     - Test paper OCR on physical scanner hardware.
3. **Intervening User Directive**:
   - At step 5858, the user submitted a new architectural requirement: introduce `qwen3.5:4b` as an interchangeable first-class main agent model alongside `qwen3.5:9b` to support low-VRAM machines with 100% platform capability parity.

- *Evidence Sources*: [RELEASE_CERTIFICATION.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/RELEASE_CERTIFICATION.md) Section 9; `transcript.jsonl` steps 5775, 5832, 5858.

---

## 11. Evidence Sources

All statements in this document are directly derived from the following concrete artifacts:

| Artifact | File Path | Scope |
|---|---|---|
| Release Certification | [RELEASE_CERTIFICATION.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/RELEASE_CERTIFICATION.md) | Release candidate identity, smoke summary, freeze decision |
| System Architecture | [FINAL_ARCHITECTURE.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_ARCHITECTURE.md) | Subsystem topologies, single cognitive agent loop, PEOV |
| Known Limitations | [FINAL_KNOWN_LIMITATIONS.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_KNOWN_LIMITATIONS.md) | Operational boundaries, VRAM constraints, UIPI limits |
| Release Blockers | [FINAL_RELEASE_BLOCKERS.md](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_RELEASE_BLOCKERS.md) | 5 hardware and environmental blockers |
| Feature Matrix | [FINAL_FEATURE_MATRIX.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_FEATURE_MATRIX.json) | 28 audited features (23 PASS, 1 BLOCKED, 4 UNVERIFIED) |
| Bug Ledger | [FINAL_BUG_LEDGER.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_BUG_LEDGER.json) | 41 audited defects (40 resolved, 1 partial) |
| Smoke Results | [FINAL_SMOKE_RESULTS.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_SMOKE_RESULTS.json) | 13/13 verified smoke run evidence |
| Security Results | [FINAL_SECURITY_RESULTS.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_SECURITY_RESULTS.json) | 32/32 red-team security test evidence |
| Failure Matrix | [FINAL_FAILURE_MATRIX.json](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/FINAL_FAILURE_MATRIX.json) | Fail-closed handling across all failure domains |
| Release Hashes | [RELEASE_HASHES.txt](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/RELEASE_HASHES.txt) | SHA-256 integrity hashes of core modules |
| Git Commit | `960eacc` | Commit snapshot of Zero-Trust Certification and Release Freeze |
| Conversation Log | `transcript.jsonl` | Steps 5770–5858 logging the exact sequence of commands and prompts |

---

## 12. Confidence / Unverified Items

1. **Reconstruction Confidence**: **100% (HIGH)**
   - The repository contains complete, uncorrupted forensic records, commit logs, test reports, and configuration files for commit `960eacc`.
2. **Items Unverified at That Time (Inherited from Release Freeze)**:
   - Physical microphone-to-speaker acoustic feedback on physical hardware.
   - Interactive DOM web automation (marked BLOCKED).
   - Continuous 4-hour soak run (only short 20-cycle soak was executed).
   - Clean-machine VM testing of the compiled standalone executable.
   - Physical paper OCR scanning.
