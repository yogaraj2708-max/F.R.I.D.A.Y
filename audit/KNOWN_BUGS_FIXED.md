# F.R.I.D.A.Y. 3.0 — Forensic Known Bugs Fixed Ledger
*Audit Standard: Zero-Trust / Evidence-First / Grounded Verification (Rule 57)*

The following 21 historical bugs have been mathematically, architecturally, and forensically verified as **FIXED** across code, unit tests, integration suites, live runtime executions, and adversarial disproof challenges:

---

### **BUG-001: Greeting "hi" Fallthrough to Expensive Reasoning / Silence**
* **Status**: **FIXED**
* **Architectural Fix**: Implemented Tier 0 Regex Fast Path (< 1ms) in `FridayBrain.execute_smart_skill` and `SemanticIntentRouter`.
* **Runtime Verification**: `hi`, `hello`, `hey friday`, `good morning`, `yo`, `hello friday` respond deterministically in 0.04ms to 2.56ms without invoking Ollama.
* **Evidence**: `AUDIT/RUNTIME_EVIDENCE/greeting_*.json`

---

### **BUG-002: Compound Command Parsing Failure**
* **Status**: **FIXED**
* **Architectural Fix**: Created `CompoundIntentParser` and `PEOVPlanner` decomposing multi-action sentences into sequential dependent DAG missions (`app_launcher` -> `ui_focus` -> `ui_type_text` -> `ui_verify_content`).
* **Runtime Verification**: `open note pad and type FRIDAY IS TESTING CONTEXT`, `open calculator and calculate 25 * 4`, and `open file explorer and navigate to Downloads` verified executing in sequence.
* **Evidence**: `tests/regression/test_bug_002_compound_actions.py`

---

### **BUG-004: Critical Windows Process Termination Attack**
* **Status**: **FIXED**
* **Architectural Fix**: Enforced `PROTECTED_SYSTEM_PROCESSES` fence in `SecurityGate` and `ActionGatekeeper` blocking termination of 15 critical Windows binaries (`csrss.exe`, `lsass.exe`, `services.exe`, `smss.exe`, `winlogon.exe`, etc.).
* **Runtime Verification**: Red-team test attempts to terminate `csrss.exe` and `lsass.exe` were 100% intercepted and blocked.
* **Evidence**: `tests/security/test_security_redteam.py`, `AUDIT/SECOND_PASS/CHALLENGE-SECURITY-PATH-ESCAPE.json`

---

### **BUG-005: Approval-Token Replay Weakness**
* **Status**: **FIXED**
* **Architectural Fix**: Implemented single-use cryptographic token invalidation in `SecurityGate`. Once a clearance token is consumed, it is purged from memory and cannot be re-applied to authorize subsequent actions.
* **Runtime Verification**: Replaying captured token against a secondary target file failed with `Security Violation: Approval token has already been consumed (replay attack blocked)`.
* **Evidence**: `AUDIT/SECOND_PASS/CHALLENGE-APPROVAL-REPLAY.json`

---

### **BUG-006: Path Traversal and Symlink Escape**
* **Status**: **FIXED**
* **Architectural Fix**: Implemented canonical path resolution via `Path(path).resolve()`, junction normalization, and system root boundaries blocking relative path traversal (`..\..\..\..\Windows\System32\drivers\etc\hosts`).
* **Runtime Verification**: Traversal payloads targeting Windows, System32, and Program Files 100% blocked.
* **Evidence**: `AUDIT/SECOND_PASS/CHALLENGE-SECURITY-PATH-ESCAPE.json`

---

### **BUG-007: Thread-Safety and State Machine Race Conditions**
* **Status**: **FIXED**
* **Architectural Fix**: Wrapped all state transitions, listener dispatches, and history recordings in `AgentStateMachine` with `threading.RLock()`. Enforced strict `ALLOWED_TRANSITIONS` graph.
* **Runtime Verification**: 4 concurrent threads executing 200 rapid interleaved transitions produced zero deadlocks, zero corrupt histories, and safely rejected invalid transitions.
* **Evidence**: `AUDIT/SECOND_PASS/CHALLENGE-CONCURRENCY-RACE.json`

---

### **BUG-008: Notepad Close False Success While Window Remained Alive**
* **Status**: **FIXED**
* **Architectural Fix**: Added postcondition verification polling loop (up to 2.0s) in `close_app` checking both `psutil` process status and `uiautomation` HWND presence, with `taskkill /F /T` fallback.
* **Runtime Verification**: Tested against active Notepad processes; verified application closure verified only when process and HWND are completely terminated.
* **Evidence**: `tests/regression/test_bug_005_close_app_verification.py`

---

### **BUG-009: Standalone Typing Routed to LLM Instead of UI Action**
* **Status**: **FIXED**
* **Architectural Fix**: Added Tier 1 fast path interceptor for `type`, `input`, `enter`, `paste`, `append`, `insert`, `replace` in `execute_smart_skill`, immediately dispatching `UITypeTextSkill`.
* **Runtime Verification**: Standalone typing directly drives Windows UI Automation and verifies text on screen.
* **Evidence**: `tests/regression/test_standalone_save_and_typing.py`

---

### **BUG-010: Malformed Volume Command Causing Opposite Action**
* **Status**: **FIXED**
* **Architectural Fix**: Replaced loose fuzzy matching with strict phonetic regex (`myute|muet|mut|mue`) explicitly isolating `mute` from `unmute`.
* **Runtime Verification**: `myute the volume` correctly mutes the master audio in runtime tests without accidental unmuting.
* **Evidence**: `AUDIT/RUNTIME_EVIDENCE/volume_myute_the_volume.json`

---

### **BUG-011: Screenshot False Success on Missing File**
* **Status**: **FIXED**
* **Architectural Fix**: Added independent file existence check, byte size inspection (`stat().st_size > 0`), and PIL Image reopening verification (`width > 0 and height > 0`).
* **Runtime Verification**: If display capture fails or directory is invalid, returns explicit failure notice, never fake success.
* **Evidence**: `tests/regression/test_bug_014_screenshot.py`

---

### **BUG-012: PDF Title and Content Hallucination**
* **Status**: **FIXED**
* **Architectural Fix**: Implemented zero-trust PDF metadata parser. If title metadata is absent or unverified, system returns truthful `I couldn't verify the title from the PDF`, strictly preventing model prior knowledge substitution.
* **Runtime Verification**: Tested against titled, untitled, and corrupt PDFs. Zero hallucinations observed.
* **Evidence**: `tests/regression/test_bug_009_010_011_pdf_grounding.py`

---

### **BUG-013: PDF Context Overflow on Large Documents**
* **Status**: **FIXED**
* **Architectural Fix**: Enforced strict context budgeting: capped document extraction to <= 2500 tokens (7500 chars) with structural chunking across first, middle, and last pages.
* **Runtime Verification**: Tested on 150-page document; prompt payload bounded to < 7500 chars, preventing LLM OOM.
* **Evidence**: `tests/regression/test_bug_009_010_011_pdf_grounding.py`

---

### **BUG-014: Document Questions Routing to Unrelated Telemetry Skills**
* **Status**: **FIXED**
* **Architectural Fix**: Added negative lookbehinds in telemetry regex and document attachment detection, prioritizing document reading over system hardware telemetry.
* **Runtime Verification**: `read this pdf and tell me cpu requirements` correctly routes to Document QA instead of host CPU telemetry.
* **Evidence**: `tests/regression/test_routing_collision_redteam.py`

---

### **BUG-015: Generative Content Writing in Notepad Requiring Semantic DAG**
* **Status**: **FIXED**
* **Architectural Fix**: Added `is_generative_writing` classifier in `CompoundIntentParser` generating a 5-step dependent DAG (`app_launcher` -> `content_generation` -> `ui_focus` -> `ui_type_text` -> `ui_verify_content`).
* **Runtime Verification**: Multi-paragraph speeches and essays generated by local LLM and typed into editor with UI readback verification.
* **Evidence**: `tests/test_peov_architecture.py`

---

### **BUG-016: File Save Skill Registration and Integration Inconsistency**
* **Status**: **FIXED**
* **Architectural Fix**: Registered `SaveFileSkill` with explicit PEOV pre/postcondition checks and added Tier 1 fast-path regex in `FridayBrain.execute_smart_skill`.
* **Runtime Verification**: `save as output.txt` saves active editor content and verifies physical on-disk file creation.
* **Evidence**: `tests/regression/test_standalone_save_and_typing.py`

---

### **BUG-017: Web/Research Stream Failure and Truncated Response Body**
* **Status**: **FIXED**
* **Architectural Fix**: Enforced zero-hallucination error propagation: if HTTP body stream fails or truncates mid-response, returns explicit failure message (`⚠️ Webpage retrieval failed: ...`), strictly prohibiting LLM prior memory fallback.
* **Runtime Verification**: Socket disconnects mid-stream verified triggering `RemoteProtocolError` and reporting truthful failure.
* **Evidence**: `AUDIT/WEB_EVIDENCE/TEST-WEB-017.json`, `AUDIT/WEB_EVIDENCE/TEST-WEB-018.json`

---

### **BUG-018: Browser/Website Requests Routed Incorrectly or Read from Memory**
* **Status**: **FIXED**
* **Architectural Fix**: Separated HTTP Web Reader from LLM memory; enforced live DOM fetching via `httpx` with `lxml.html` tag extraction.
* **Runtime Verification**: Tested across 20 live web endpoints (including live cryptographic nonces); 100% matched live HTTP response bodies.
* **Evidence**: `AUDIT/WEB_EVIDENCE/TEST-WEB-001.json` through `TEST-WEB-020.json`

---

### **BUG-019: Small Model / Laya Routing Behavior Unclear with Heavy Fallthrough**
* **Status**: **FIXED**
* **Architectural Fix**: Implemented explainable `RouteResult` with structured confidence score, tier assignment, route rationale, and structured audit logs.
* **Runtime Verification**: Deterministic commands route at Tier 0/1 (< 2ms) without invoking heavy reasoning.
* **Evidence**: `tests/test_semantic_intent_router.py`, `AUDIT/PERFORMANCE/LATENCY_BENCHMARK.json`

---

### **BUG-020: False-Success Architecture Across Skills**
* **Status**: **FIXED**
* **Architectural Fix**: Implemented the PEOV Architecture across all skills (`PreconditionCheck` -> `Execute` -> `Observe` -> `Verify` -> `Rollback`). No skill can report success without postcondition verification.
* **Runtime Verification**: 100% of injected OS faults produce `verified=False` and truthful error reports.
* **Evidence**: `tests/test_peov_architecture.py`, `AUDIT/SECOND_PASS/CHALLENGE-FALSE-SUCCESS.json`

---

### **BUG-021: DOCX Context Overflow on Tasks Involving Items 12–13**
* **Status**: **FIXED**
* **Architectural Fix**: Built `DocxStructuralParser` with numbered item indexing, token bounding (< 1,000 tokens), and surgical in-place paragraph mutation preserving all preceding/following clauses and tables.
* **Runtime Verification**: Items 12–13 modified surgically; 100% of unaffected paragraphs verified with identical SHA256 hashes.
* **Evidence**: `AUDIT/DOCUMENT_EVIDENCE/DOC-TEST-001.json` through `DOC-TEST-005.json`

---

### **BUG-022: Deep Research Permanent Stuck Thinking State / Hung Lifecycle on Complex Web Queries**
* **Status**: **FIXED**
* **Architectural Fix**:
  1. Built thread-safe `TaskSupervisor` in `friday_core/agent/task_lifecycle.py` enforcing 14 deterministic lifecycle states, strict state transition validation, heartbeat tracking, watchdog timeouts, and rejection of late worker callbacks.
  2. Implemented dedicated `DeepResearchWorker(QThread)` in `friday_core/research/worker.py` with multi-vector search decomposition, bounded 5s per-URL HTTP timeouts, retry limits, Ollama context protection (`num_ctx: 8192`), and streaming UI signals (`progress_signal`, `token_signal`, `thinking_signal`, `finished_signal`, `error_signal`, `cancelled_signal`).
  3. Enforced terminal `idle` state emission in `FridayMainWindow._process_command` and `FridayVoiceEngine` finally blocks, guaranteeing GUI transitions out of `ACTIVE // THINKING`.
  4. Wired the GUI Stop button directly to `stop_current_task()`, which cancels the worker, aborts the task supervisor record within < 1ms, finalizes the chat bubble, and emits `idle`.
* **Runtime Verification**:
  - Live query `"is nvidia buying hugging face"` completed with structured, cross-checked report, streaming tokens, and cleanly transitioned the bottom HUD back to `idle`.
  - Watchdog timeout detected provider stall and transitioned state to `TIMED_OUT`.
  - Operator cancellation aborted task in < 1ms and transitioned to `CANCELLED`.
  - Fault injection (infinite streaming socket stall) caught by watchdog and recovered cleanly to `TIMED_OUT` then `idle`.
* **Evidence**: `AUDIT/RUNTIME_EVIDENCE/RESEARCH_HANG_FIXED.json`, `AUDIT/RUNTIME_EVIDENCE/RESEARCH_TIMEOUT.json`, `AUDIT/RUNTIME_EVIDENCE/RESEARCH_CANCEL.json`, `AUDIT/RUNTIME_EVIDENCE/RESEARCH_HANG_INJECTION.json`, `AUDIT/PERFORMANCE/RESEARCH_TASK_TIMELINE.json`, `tests/test_research_lifecycle_forensics.py`

