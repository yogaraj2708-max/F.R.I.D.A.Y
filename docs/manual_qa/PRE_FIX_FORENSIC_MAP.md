# F.R.I.D.A.Y. 3.0 — Pre-Fix Forensic Map & Architectural Failure Topology

**Audit Mode**: Zero-Trust Forensic Software Failure Audit  
**Date**: 2026-09-25  
**Auditor**: Principal Windows Automation, AI Routing & Reliability Engineer  
**Status**: Pre-Code Audit Baseline & Forensic Architectural Map  

---

## 1. System Topology & Subsystem Map

F.R.I.D.A.Y. 3.0 consists of 6 primary interacting layers:

```
[User Speech / Chat Input]
           │
           ▼
[friday_ui.core.engine: FridayBrain] ──── Tier 0 Fast-Paths (< 1ms)
           │
           ├──► [friday_core.router: SemanticIntentRouter]
           │         ├── Tier 1: FastLocalEmbedder (384-dim Blake2b hash, < 0.2ms)
           │         ├── Tier 2: Nano-Model (friday-decider / qwen2.5:0.5b / Laya ModernBERT)
           │         └── Tier 3: LLM General Chat / Reasoning (deepseek-r1:8b)
           │
           ├──► [friday_core.gatekeeper: Gatekeeper] (Action Authorization & OS Isolation)
           │
           ├──► [friday_core.agent: PEOVExecutor & CompoundIntentParser] (5-Stage DAGs)
           │
           ├──► [friday_core.skills: SkillRegistry] (22 Verifiable Built-in Skills)
           │         ├── UI Automation (UITypeTextSkill, SaveFileSkill, UIKeyPressSkill)
           │         ├── File Ops (CreateFileSkill, FileSearchSkill, FileSelectorSkill)
           │         ├── Browser Ops (BrowserNavigateSkill, BrowserDownloadSkill)
           │         ├── Desktop (ScreenshotSkill, ClipboardSkill, VolumeControlSkill)
           │         └── Telemetry, Timer, Memory, Calculator, Word
           │
           └──► [Hardware & OS Surface: Windows 11 API / Win32 / UIA / Core Audio / Sockets]
```

---

## 2. Intent Routing & Precedence Map

The intent routing pipeline resolves commands through the following cascade:

1. **Tier 0 Deterministic Regex Fast-Paths in `FridayBrain.execute_smart_skill`**:
   - `# 0.001`: Direct arithmetic evaluation (`calc.py`)
   - `# 0.002`: Weather queries
   - `# 0.003`: Greetings & identity (`hi`, `who are you`)
   - `# 0.004`: Application launch (`open <app>`)
   - `# 0.0051`: Application termination (`close <app>`)
   - `# 0.0052`: Standalone UI typing (`type <text>`)
   - `# 0.0053`: Standalone file save (`save file as <filename>`)
   - `# 0.0054`: Document / PDF Grounded QA
   - `# 0.006`: Timer countdown status
   - `# 0.008`: Native clipboard copy & paste
   - `# 0.009`: System hardware telemetry & Top CPU diagnostics
   - `# 0.010`: Direct file creation on desktop
   - `# 0.011`: File organizer dry-run preview
   - `# 0.012`: Direct file search

2. **Tier 1 Fast Local Embedding Centroid Match (< 0.2ms)**:
   - Queries `FastLocalEmbedder` across 11 intent clusters.
   - Computes blended similarity: `0.85 * max_exemplar_sim + 0.15 * centroid_sim`.
   - Threshold `0.76` for immediate deterministic dispatch.

3. **Tier 2 Nano-Model Disambiguation (40–80ms)**:
   - Invoked ONLY when Tier 1 score is ambiguous (`< 0.70`).
   - Uses `friday-decider:latest` or `qwen2.5:0.5b` or Laya ModernBERT.
   - Enforces anti-collision guards for `DOCUMENT_QA` vs `SYSTEM_TELEMETRY`.

4. **Tier 3 Heavy LLM Reasoning Hand-Off**:
   - `deepseek-r1:8b` via Ollama for multi-turn conversational reasoning, coding, and creative synthesis.

---

## 3. Forensic Code-Path Inventory: Fallback-to-LLM Risks

Any command that fails to match Tier 0 or returns `None` from Tier 1/2 falls through to `FridayBrain.query_llm()`.

| Trigger Command | Intended Action | Previous Failure Mode | Root Cause |
|:---|:---|:---|:---|
| `"read https://example.com"` | Fetch webpage DOM, parse elements, return verified text | Falls to 8B LLM; LLM hallucinates website content from memory | Missing `WEB_READING` fast-path and missing `SkillIntent.WEB_READING` enum |
| `"read heading and paragraph of http://..."` | HTTP GET, parse `<h1>` and `<p>`, verify exact nonce | Falls to 8B LLM; LLM invents generic company text | Missing HTTP DOM grounding in engine execution loop |
| `"please close notepad"` | Terminate process and verify HWND death | Fell to 8B LLM; LLM said "I closed Notepad" without closing it | Polite prefix failed strict `re.match(r"^close...")` |
| `"save as output.txt"` | Save active editor buffer to disk | Fell to 8B LLM; LLM gave instructions on how to save | Missing standalone save fast-path |
| `"what is the first sentence of this PDF?"` | Read Page 1 text stream | Collided into `SYSTEM_TELEMETRY`; reported battery % | Missing `DOCUMENT_QA` intent in router |

---

## 4. Forensic Code-Path Inventory: False-Success Risks

| Component | Code Location | False-Success Vulnerability | Eradication Architecture |
|:---|:---|:---|:---|
| `close_app` | `gatekeeper.py:270` | Empty `psutil` match returned `success=True` when window was still open | Inspects UI window, tracks real `win.ProcessId`, polls 2s, force kills, asserts `win.Exists == False` AND 0 active PIDs |
| `save_file` | `ui_automation.py:530` | Direct2D canvas returned `""`; wrote 0 bytes to disk | Caches verified text stream in `UITypeTextSkill._last_typed_text`; asserts `target_path.stat().st_size > 0` |
| `volume` | `volume.py:65` | Dispatched keystrokes without reading hardware endpoint | Precondition records `(muted, vol)`; postcondition verifies `IAudioEndpointVolume` state change |
| `screenshot` | `desktop_action.py:80` | `ms-screenclip:` launched overlay without saving image | Worker thread attached to `user32.OpenInputDesktop`; asserts file exists, size > 0, PIL dimensions > 0 |
| `clipboard` | `desktop_action.py:210` | Clipboard write failed silently on OS lock contention | Win32 API with 6 contention retries (40ms backoff) and byte readback verification |
| `web_reading` | `engine.py` | LLM generated answer from pre-trained memory without HTTP request | Must execute real HTTP request via `BrowserSession`, assert status 200, verify body contains target text |

---

## 5. Subsystem-by-Subsystem Forensic Audit

### 1. Browser & Web Subsystem
- **Current State**:
  - `friday_core/browser/session.py`: Implements `BrowserSession` using `httpx.Client` and `lxml.html`. Extracts `title`, `text_content`, and `interactive_elements`.
  - `friday_core/browser/controller.py`: Implements `BrowserController` with `BrowserAction` execution and `verify_action()`.
  - `friday_core/browser/skills.py`: Implements `BrowserNavigateSkill` and `BrowserDownloadSkill`.
  - **Defect Discovered**: In `FridayBrain.execute_smart_skill`, there is NO connection between user voice/chat commands and `BrowserNavigateSkill`! Commands like `"read http://..."` or `"extract text from http://..."` fall through to the LLM, causing memory hallucination (violating BUG-016, 017, 018 and Section H).

### 2. PDF & Document Subsystem
- **Current State**:
  - `friday_ui/core/engine.py:1972`: `_find_active_or_recent_pdf()` and `_handle_document_qa()`.
  - Uses `pypdf` for `/Title` metadata extraction and Page 1 first sentence extraction.
  - Context budgeting slices large documents into `<= 7500` characters (`<= 2500` tokens).
  - Truthful fallback on missing title: `"I couldn't verify the title from the PDF."`.
  - **Status**: Implemented and verified by `tests/regression/test_bug_009_010_011_pdf_grounding.py`.

### 3. UI Automation & Keypress Subsystem
- **Current State**:
  - `friday_core/skills/builtins/ui_automation.py`: `UITypeTextSkill` supporting `replace`, `append`, `type`, `insert`, `selection`.
  - `UIKeyPressSkill` explicitly focuses editor control before dispatching keys.
  - Caches verified text stream in `UITypeTextSkill._last_typed_text`.
  - `SaveFileSkill` verifies file on disk has `st_size > 0`.
  - **Status**: Implemented and verified live on physical Windows host.

### 4. Audio Subsystem
- **Current State**:
  - `friday_core/skills/builtins/volume.py`: Integrates `get_audio_state()` and `adjust_volume()`.
  - Precondition and postcondition assertions on `IAudioEndpointVolume`.
  - **Status**: Implemented and verified live on physical Windows host.

---

## 6. Targeted Remediation Plan for Forensic Audit

To satisfy the release-blocking requirements:
1. **Implement Web Grounding Fast-Path & Skill Integration**:
   - Add `# 0.0055 WEBPAGE GROUNDED READING & RETRIEVAL` in `FridayBrain.execute_smart_skill`.
   - Intercept URLs (`http://`, `https://`, `localhost`) and extract headings (`h1`-`h6`), paragraphs (`p`), and text.
   - If HTTP request fails or network drops, report a truthful failure message. NEVER fall back to LLM memory.
   - Add `SkillIntent.WEB_READING` to `semantic_router.py` with training exemplars.
2. **Implement Section H: Mandatory Unique-Nonce Web Test**:
   - Create `tests/regression/test_mandatory_unique_nonce_web.py`.
   - Spins up a real local `http.server` on an ephemeral port.
   - Generates a cryptographically random UUID nonce.
   - Serves `<h1>FRIDAY-UNIQUE-{nonce}</h1><p>GROUNDING-TEST-{nonce}</p>`.
   - Dispatches command `"read the heading and paragraph of http://127.0.0.1:{port}"` through `FridayBrain`.
   - Asserts:
     - Real HTTP request was logged by server.
     - Raw body contains nonce.
     - Extracted response contains exact nonce.
     - Zero LLM memory substitution.
3. **Implement Full Routing Collision Red-Team Tests**:
   - Create `tests/regression/test_routing_collision_redteam.py` testing all adversarial pairs from Section L.
4. **Implement Failure-Injection Tests**:
   - Create `tests/regression/test_failure_injection_resilience.py` testing intentional breakages (network down, bad save path, closed app, etc.) from Section M.
5. **Run Full 100+ Repetition Resource / Stability Verification**:
   - Create `scratch/stability_audit.py` to assert zero handle/memory/zombie leaks across 100+ continuous operations.
6. **Produce All 14 Required Audit Markdown Documents in `docs/manual_qa/`**.
