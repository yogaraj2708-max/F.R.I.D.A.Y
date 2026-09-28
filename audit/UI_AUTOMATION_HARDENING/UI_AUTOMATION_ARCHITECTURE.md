# F.R.I.D.A.Y. 3.0 — Desktop UI Automation & Computer Control Architecture
## Zero-Trust Forensic Hardening & Verification Specification

---

### 1. Executive Summary & Non-Interference Mandate

This document details the architectural implementation and zero-trust verification of the Desktop UI Automation and Computer Control subsystem of F.R.I.D.A.Y. 3.0. 

**Strict Design Constraint & UI Freeze**:
- The graphical user interface (PyQt6-based dark/glassmorphic dashboard) is **100% frozen**.
- Zero modifications were made to colors, tokens, layouts, fonts, or animations.
- All 15 required accessibility identifiers (`chat_input`, `send_button`, `stop_button`, `attachment_button`, `mic_button`, `model_selector`, `research_input`, `research_start_btn`, `research_stop_btn`, `doc_search_input`, `browse_doc_btn`, `ingest_btn`, `settings_category_list`, `save_settings_btn`, `model_selector_settings`) are verified and preserved intact.

---

### 2. High-Integrity Agent Pipeline

The UI automation architecture strictly enforces model-driven orchestration:
```
USER GOAL
    │
    ▼
MAIN AGENT MODEL (qwen3.5:9b)
    │
    ▼ (Native Tool Call: launch_app, click_control, type_text, inspect_ui)
Python Tool Dispatcher (friday_ui/core/engine.py & agent_bridge.py)
    │
    ▼
Security / Risk Gate (friday_core/automation/security_guard.py)
    │
    ▼
Pre-Action UI Inspection (friday_core/automation/inspector.py)
    │
    ▼
Action Execution Layer (friday_core/automation/action_engine.py)
    │
    ▼
Postcondition Verification & Readback (action_engine.py + inspector.py)
    │
    ▼ (Structured Evidence Result)
Tool Result Return
    │
    ▼
SAME MAIN AGENT MODEL (Continues reasoning or synthesizes answer)
```

**Anti-Hijacking Guarantee**:
The Python execution layer contains **zero conversational keyword heuristics** (e.g. regex matching "notepad" in chat to bypass the LLM). The main model autonomously generates tool calls based on structured JSON schemas, reads back verified postcondition state, and decides subsequent actions.

---

### 3. Five-Tier Automation Hierarchy

All interactions strictly adhere to the five-tier execution priority:

1. **Priority 1: Semantic UI Automation (UIA) & Accessibility**
   - Direct COM interface calls through Windows UIAutomation Core.
   - Leverages `InvokePattern`, `TogglePattern`, `SelectionItemPattern`, `ValuePattern`, and `TextPattern`.
   - Typed control resolution (`ButtonControl`, `MenuItemControl`, `EditControl`, `DocumentControl`, `HyperlinkControl`).
2. **Priority 2: Win32 Standard Controls**
   - Verified window messaging: `BM_CLICK` (`0x00F5`), `WM_SETTEXT` (`0x000C`), `WM_GETTEXT` (`0x000D`).
   - Operates directly on validated HWNDs without moving physical mouse coordinates.
3. **Priority 3: Keyboard Navigation & Shortcuts**
   - Precise keystroke injections via `pyautogui` / Windows `SendInput`.
   - Focus cycling via `{Tab}`, `{Alt}`, `{Ctrl}`, and accelerated mnemonics.
4. **Priority 4: Vision-Assisted Interaction**
   - Multimodal OCR and visual bounding box grounding.
   - Permitted only when UIA and Win32 controls are unavailable or custom-rendered, requiring confidence >= 0.85.
5. **Priority 5: Coordinate Interaction (Strict Final Fallback)**
   - Used only as an absolute last resort when accessibility trees, Win32 messages, shortcuts, and vision bounding are impossible.
   - Requires explicit verification bounds and postcondition inspection.

---

### 4. Interactive Desktop Attachment & COM Safety

In Windows multi-session / agent execution environments (e.g., IDE runners, service processes), Python subprocesses often spawn on background desktops (`exebox-...`), causing COM initialization errors (`WinError 170: ERROR_BUSY`) or hidden windows (`SW_HIDE`).

**Mitigations Implemented**:
- **Automatic Desktop Attachment**: Pre-attaches execution threads to `WinSta0\Default` via `user32.OpenDesktopW("default", 0, False, 0x01FF)` and `user32.SetThreadDesktop()` before importing `uiautomation`.
- **Package Hook**: `friday_core/automation/__init__.py` attaches immediately on package load.
- **Process Spawning**: Subprocess launchers configure `STARTUPINFO.lpDesktop = r"WinSta0\Default"` with `wShowWindow = SW_SHOWNORMAL` (`1`), preventing headless zombie process locks.
- **Modern Windows 11 App Activation**: Maps modern UWP/WinUI 3 applications (e.g., Windows 11 Notepad, Calculator) to `shell:AppsFolder` URIs, preventing App Execution Alias background hangs.

---

### 5. Stale-Control Defense & Verification Model

To prevent blind execution on invalidated or recycled handles:
1. **HWND Validity Check**: Invokes Win32 `IsWindow(hwnd)` before any interaction.
2. **UIA Exists Probing**: Validates that COM elements still exist in the live desktop visual tree (`element.Exists(0, 0)`).
3. **Bounding Rect Sanity**: Detects collapsed bounding boxes (`(0, 0, 0, 0)`) or elements displaced off-screen.
4. **Pre-Action & Post-Action Cycle**: Every action captures a complete `before_state` inspection and a matching `after_state` re-inspection.
5. **Mandatory Readback**: `type_text` requires verified content readback via `TextPattern.DocumentRange.GetText()` or `ValuePattern.Value` before reporting success.

---

### 6. Zero-Trust Security Gate

All desktop interactions pass through `friday_core/automation/security_guard.py`:
- **Protected Process Fencing**: Blocks targeting of critical OS processes (`csrss.exe`, `lsass.exe`, `services.exe`, `smss.exe`, `winlogon.exe`, `wininit.exe`, `svchost.exe`, `dwm.exe`, `system`, `ntoskrnl.exe`, etc.).
- **Dangerous Command Fencing**: Prevents shell exploits and destructive commands (`rmdir /s`, `del /f`, `format`, `reg delete`, `powershell -enc`, `vssadmin delete shadows`).
- **Destructive UI Action Guard**: Flags and fences controls labeled "Format", "Wipe", "Delete Partition", etc.
- **Observe-Only Mode**: Emergency panic switch immediately disables state-modifying actions while preserving read-only UI inspection.

---

### 7. Task Lifecycle & Forensic Audit Trail

- **Cancellation**: Cooperative cancellation tokens checked at each lifecycle milestone (pre-inspection, window wait, control locating, execution, readback). Terminal status is guaranteed to be `CANCELLED`.
- **Thread-Safe Audit Tracing**: All actions, inspections, failures, and security decisions are atomically appended to JSON ledgers in `AUDIT/UI_AUTOMATION_HARDENING/` without logging sensitive credentials or tokens.
