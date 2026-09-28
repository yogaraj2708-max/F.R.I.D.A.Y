# F.R.I.D.A.Y. 3.0 — Final System Architecture

**Document Type**: Architectural Specification & Topology  
**Release Target**: F.R.I.D.A.Y. 3.0 Release Gate  
**Compliance Standard**: Zero-Trust, Model-Agnostic, Native Tool-Calling  

---

## 1. System Topology Overview

F.R.I.D.A.Y. 3.0 operates as an autonomous, multi-modal desktop assistant. The architecture strictly enforces a single, model-agnostic reasoning loop where the **User-Selected Main Agent Model** (`qwen3.5:9b`) is the sole cognitive decision-maker.

```
                    ┌─────────────────────────┐
                    │      USER / OPERATOR    │
                    └───────────┬─────────────┘
                                │ Typed Prompt / Voice Utterance
                                ▼
       ┌────────────────────────────────────────────────────────┐
       │             F.R.I.D.A.Y. UI / VOICE ENGINE              │
       │  (PySide6 Fluent HUD, VAD, Faster-Whisper, Kokoro TTS)  │
       └────────────────────────┬───────────────────────────────┘
                                │ Clean Natural Language Query
                                ▼
       ┌────────────────────────────────────────────────────────┐
       │              USER-SELECTED MAIN AGENT MODEL            │
       │                   (Current: qwen3.5:9b)                │
       └───────────┬────────────────────────────────┬───────────┘
                   │ Direct Answer                  │ Native Tool Call
                   │                                │ (JSON schema)
                   ▼                                ▼
       ┌────────────────────────┐       ┌───────────────────────────────┐
       │   UI Streaming & TTS   │       │   PYTHON AGENT TOOL BRIDGE    │
       │   (Markdown + Speech)  │       │   (OpenAPI Schema Validation) │
       └────────────────────────┘       └───────────────┬───────────────┘
                                                        │
                                                        ▼
                                        ┌───────────────────────────────┐
                                        │    SECURITY & RISK GATEKEEPER │
                                        │ (SSRF, Traversal, Process Blk)│
                                        └───────────────┬───────────────┘
                                                        │ Approved
                                                        ▼
                                        ┌───────────────────────────────┐
                                        │     REAL SUBSYSTEM EXECUTION  │
                                        │  (Research, Doc, Vision, UI)  │
                                        └───────────────┬───────────────┘
                                                        │
                                                        ▼
                                        ┌───────────────────────────────┐
                                        │  POSTCONDITION VERIFICATION   │
                                        │ (PEOV, Readback, File Check)  │
                                        └───────────────┬───────────────┘
                                                        │ Structured Result
                                                        ▼
       ┌────────────────────────────────────────────────────────┐
       │             SAME MAIN AGENT MODEL REPLANNING           │
       │          (Evaluates tool evidence or failure)          │
       └────────────────────────┬───────────────────────────────┘
                                │ Final Answer / Next Action
                                ▼
       ┌────────────────────────────────────────────────────────┐
       │                  TERMINAL TASK STATE                   │
       │   (TaskSupervisor: COMPLETED / FAILED / CANCELLED)     │
       └────────────────────────────────────────────────────────┘
```

---

## 2. Core Subsystem Architectures

### 2.1 UI Layer
- **Framework**: PySide6 (Qt for Python).
- **Core Views**:
  - `ChatView`: Natural language dialogue, streaming markdown bubbles, attachment tags.
  - `ResearchView`: Multi-query research tree, deep inspection dossiers, source provenance.
  - `DocumentsView`: Document viewer, chunk navigator, and surgical editor preview.
  - `SettingsView`: Model configuration, TTS voices, device selection, storage controls.
- **HUD & Status Bar**: Non-blocking telemetry showing CPU, RAM, active task state, and mic volume.
- **Responsiveness Guarantee**: All background workloads (LLM generation, PDF parsing, research fetching, audio capture) execute on dedicated `QThread` workers. Zero blocking on the Qt main GUI thread.

### 2.2 Main Agent Model & Dispatcher
- **Model Agnosticism**: The system maintains zero hardcoded model weights or prompt tokens. The model is resolved dynamically via `settings.get("model", "qwen3.5:9b")`.
- **Native Tool Calling**: Implements official Ollama / OpenAI function calling schemas:
  - `calculate`: Safe mathematical expression evaluation.
  - `system_telemetry`: CPU, RAM, battery, and process statistics.
  - `web_fetch`: HTTP webpage content retrieval.
  - `deep_research`: Autonomous multi-source research dossiers.
  - `read_document` & `edit_document`: Multi-format document analysis and surgical editing.
  - `inspect_image`: Structured vision specialist interrogation.
  - `launch_app`, `inspect_ui`, `type_text`, `close_app`: Desktop automation.
  - `query_knowledge_base`: Semantic vector RAG retrieval.
- **Zero Keyword Fallback**: The model makes 100% of tool-invocation decisions. Python does not parse regex keywords or force tool dispatch behind the model's back.

### 2.3 Security Subsystem & Risk Gatekeeper
- **Process Protection Fence**: Deny-list blocking termination of critical system processes (`csrss.exe`, `lsass.exe`, `services.exe`, `smss.exe`, `winlogon.exe`).
- **Path Traversal Defense**: Canonical path resolution via `Path.resolve()`, enforcing workspace and safe directory containment; blocks `..\` escapes and UNC bypasses.
- **SSRF Prevention**: Strict network boundary blocking loopback (`127.0.0.1`), cloud metadata (`169.254.169.254`), and private RFC 1918 subnets from web fetch tools.
- **Cryptographic Token Authorization**: High-risk operations (file deletion, process termination) require single-use, cryptographically nonced approval tokens with short TTLs. Replay attacks are permanently rejected.

### 2.4 Verification Subsystem (PEOV)
- **Precondition $\to$ Execute $\to$ Observe $\to$ Verify**:
  - Every skill verifies preconditions before execution.
  - Postcondition verification confirms physical side-effects on disk, OS, or network (e.g. `doc_file.read_text()` verifies replacement, `psutil` confirms process exit).
  - False-success is structurally impossible; if verification fails, the tool result is marked `REJECTED` and returned to the model for replanning.

### 2.5 Research Subsystem
- **Supervisor-Managed Worker**: `DeepResearchWorker(QThread)` runs with explicit `TaskRecord` state tracking.
- **Multi-Vector Decomposition**: Analyzes queries into orthogonal subqueries.
- **Provenance & Citations**: Every claim is linked to source URLs, HTTP status codes, retrieval timestamps, and SHA-256 content hashes.
- **Watchdog & Cancellation**: Tasks support sub-millisecond cancellation via the UI Stop button and fail-safe timeout watchdogs.

### 2.6 Document Subsystem
- **Format Coverage**: Multi-format detection via `python-magic` / MIME signatures (`TXT`, `PDF`, `DOCX`, `CSV`, `JSON`, `PY`).
- **Surgical In-Place Editor**: Performs targeted clause mutations without corrupting document formatting, XML structures, or unaffected paragraphs.
- **Worker Isolation**: Large PDF analysis (> 20 pages) runs in a background thread with throttled markdown rendering to preserve 60 FPS UI responsiveness.

### 2.7 Vision Specialist Architecture
- **Specialist Routing**: Visual queries invoke a dedicated vision model (`qwen2.5vl:3b`).
- **Structured ImageContext**: Extracts scene description, detected objects, visible OCR text, and coordinates.
- **Model Grounding**: The Main Agent Model (`qwen3.5:9b`) consumes the verified `ImageContext` to answer user questions; the vision specialist never replaces the main model.
- **Chat Isolation**: Casual chat queries with attached images bypass vision inference, preventing unnecessary GPU/compute load.

### 2.8 Desktop Automation Subsystem
- **Accessibility Integration**: Interacts with Windows applications via semantic accessibility trees.
- **Coordinate-Fallback**: Dynamic element locating is prioritized; absolute coordinates serve only as fallback.
- **Stale Control Recovery**: Handles application crashes, window minimizations, and stale element references gracefully.

### 2.9 Voice & Audio Subsystem
- **STT**: Faster-Whisper with Silero VAD for low-latency speech onset and silence detection.
- **Barge-In Acoustic Interruption**: Real-time microphone RMS monitoring triggers instant TTS cutoff when user speaks.
- **TTS Engine**: Kokoro TTS (ONNX) providing high-fidelity neural audio synthesis with robust fallback if audio hardware is unavailable.
- **Transcript Deduplication**: Temporal suppression window prevents duplicate trigger execution from acoustic echoes.

### 2.10 Memory & RAG Subsystem
- **Multi-Tier Hierarchy**:
  - Working Memory (current session, capped at 20 turns).
  - Short-Term Session Cache.
  - Long-Term Persistent Memory (SQLite WAL, domain-isolated: Project, Personal, Tech, Research).
  - Vector Knowledge Base (BM25 + fast embeddings with SHA-256 chunk deduplication).
- **Prompt Injection Defense**: Attached documents and retrieved memories are strictly encapsulated as quoted data strings; instructions embedded in data cannot hijack system prompts.
- **Verified Deletion**: Memory deletions perform immediate SQLite readback verification to ensure complete physical removal.

### 2.11 Task Lifecycle & Supervision
- **State Machine**: 14 distinct states (`CREATED`, `STARTING`, `RUNNING`, `FETCHING`, `RESEARCHING`, `SYNTHESIZING`, `VERIFYING`, `COMPLETED`, `FAILED`, `TIMED_OUT`, `CANCEL_REQUESTED`, `CANCELLED`, `PAUSED`, `RECOVERED`).
- **Strict Transition Rules**: Invalid state changes are rejected fail-closed.
- **Zombie Worker Prevention**: Late callbacks from cancelled or timed-out workers are discarded.

### 2.12 Context Budgeting & Resource Governance
- **Context Budget Manager**: Hard token bounds prevent Ollama context overflows. Dynamically truncates middle conversation turns while strictly preserving system prompts, active user instructions, and tool results.
- **Resource Hygiene**: Strict eviction bounds on vision caches (20 frames max), memory turns (20 turns max), and worker thread lifetimes.
