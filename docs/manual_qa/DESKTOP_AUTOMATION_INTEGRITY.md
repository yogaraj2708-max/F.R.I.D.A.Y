# F.R.I.D.A.Y. 3.0 — Desktop Automation Reliability & Integrity Verification Report

**Date**: September 29, 2026  
**Subsystem**: Desktop UI Automation, Window Lifecycle Management, Input Injection, Tool Dispatch Bridge  
**Target Environment**: Windows 11 Interactive Desktop  
**Primary Model**: `qwen3.5:9b` (Ollama Native Tool Calling)  
**Overall Verdict**: **100% PASS — ALL ZERO-TRUST CONTRACTS VERIFIED**

---

## 1. Executive Summary

This QA report documents the end-to-end reliability overhaul and live runtime verification of F.R.I.D.A.Y.'s desktop automation subsystem. Prior to this intervention, desktop automation suffered from seven severe failure modes:
1. Multiple Notepad instances/tabs spawned for a single user request.
2. Microsoft Word launched when unrequested.
3. Automation requests failing to complete.
4. Text insertion scrambling and corruption during typing.
5. Wrong window/application receiving keyboard inputs.
6. Automation retries spawning duplicate side effects.
7. Workarounds reported instead of completing the requested task.

All seven failure modes were systematically diagnosed, root causes isolated, and repaired with zero-trust architectural guards. The repairs were verified across two comprehensive regression suites:
- [`tests/regression/test_desktop_automation_integrity.py`](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/tests/regression/test_desktop_automation_integrity.py) (**8/8 PASSED**)
- [`tests/regression/test_notepad_multiline_typing_regression.py`](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/tests/regression/test_notepad_multiline_typing_regression.py) (**10/10 PASSED**)
- Live Windows Desktop Verification Mission via `FridayBrain.query_llm`: *"Open Notepad and write a simple C program to calculate area of a triangle."* (**100% PASS — MISSION SUCCESS**)

---

## 2. Core Root Causes & Architectural Repairs

### Root Cause 1: Interactive Desktop Worker Timeout Causing Parallel Typing Collision
- **Defect**: In `friday_core/system/window_manager.py`, `run_on_interactive_desktop` had a hardcoded `10.0s` timeout on worker threads. When typing large text (e.g. 500+ characters requiring ~13-15s), the worker thread was still typing at character 300 when `t.join(10.0)` expired. The fallback branch then executed `func(*args, **kwargs)` directly on the calling thread, causing **two threads to type into the same Notepad simultaneously**, interleaving characters (`#include` mixed with `printf`).
- **Fix**: Replaced the 10.0s timeout with a 60.0s configurable window and completely removed the concurrent fallback branch.

### Root Cause 2: Schema Pollution & Tool Duplication
- **Defect**: `get_agent_tools()` exposed both core tools (`launch_app`, `type_text`, `inspect_ui`) and legacy skills (`app_launcher`, `ui_type_text`, `word_drafter`, `ui_key_press`, `ui_focus`, `ui_verify_content`). This confused the LLM into invoking redundant tools or choosing `word_drafter` for unrequested actions.
- **Fix**: Added an explicit exclusion set in `agent_tool_bridge.get_tool_schemas()` ensuring only canonical, authoritative tools are presented to the model.

### Root Cause 3: Authoritative Application Selection Violation
- **Defect**: When users requested Notepad, models could hallucinate arguments or trigger keyword handlers for Word or VS Code.
- **Fix**: Implemented strict Authoritative Application Selection in `agent_tool_bridge.risk_gate()` that extracts explicit application names from the user query and strictly blocks any tool invocation targeting unrequested applications.

### Root Cause 4: Caret Disconnect & Replace Mode Overwrites
- **Defect**: In modern Windows 11 Notepad (WinUI 3 / XAML Island), calling Win32 `SetForegroundWindow` activates the top-level window but does not place the caret in the XAML RichEdit control. Subsequent `Ctrl+A + Delete` was lost, causing new text to type directly into un-cleared content.
- **Fix**: `type_real_keystrokes` and `action_engine.py` now locate the active `DocumentControl` / `EditControl` and invoke `Click(simulateMove=False)` before sending `Ctrl+A + Delete`.

### Root Cause 5: Windows IME Operator / Symbol Dropping
- **Defect**: Special characters like `%`, `&`, `"`, `'`, `<`, `>`, `*`, `+`, `-`, `/`, `=` did not have boundary spacing and could be dropped by Windows 11 IME text buffer suggestion loops.
- **Fix**: Expanded the punctuation boundary delay tuple in `mouse_keyboard.py` to include all operators, quotes, and symbols with 30ms spacing.

### Root Cause 6: Scoped Single-Retry with Exact Readback Verification
- **Defect**: Transient keystroke drops under heavy background load would fail the entire user request.
- **Fix**: Added a scoped single retry at 14ms pacing on the exact same bound HWND (0 new processes, 0 new windows) with strict equality verification before returning.

---

## 3. Live Runtime Verification Evidence

### Primary Command:
`"Open Notepad and write a simple C program to calculate area of a triangle."`

### Desktop State Audit:
| Metric | Expected | Actual Live State | Status |
| :--- | :--- | :--- | :--- |
| **Notepad Processes** | Exactly 1 | 1 (PID: 27184) | **PASS** |
| **Notepad GUI Windows** | Exactly 1 | 1 (HWND: 4261426) | **PASS** |
| **Word Processes** | Exactly 0 | 0 | **PASS** |
| **Word Windows** | Exactly 0 | 0 | **PASS** |
| **Target App Selection** | Notepad Only | `notepad` (0 unrequested apps) | **PASS** |
| **Insertion Backend** | `SendInput` | `REAL_KEYSTROKE` | **PASS** |
| **Content Integrity** | Valid C Triangle Code | Exact Match Readback | **PASS** |
| **Agent Mission Status** | `COMPLETED` | `COMPLETED` (2 Tool Calls) | **PASS** |

### Tool Provenance Sequence:
1. `launch_app(app_name='notepad')` -> `status: VERIFIED`, HWND: 4261426, PID: 27184
2. `type_text(app_name='notepad', text='...', mode='replace')` -> `status: VERIFIED` via `REAL_KEYSTROKE`

### Exact Screen Readback Extracted from UI Control:
```c
#include <stdio.h>
int main() {
    float base, height, area;
    // Input from user
    printf("Enter the base of the triangle: ");
    scanf("%f", &base);
    printf("Enter the height of the triangle: ");
    scanf("%f", &height);
    // Calculate area
    area = 0.5 * base * height;
    printf("\nArea of the triangle = %.2f square units\n", area);
    return 0;
}
```

---

## 4. Test Suite Execution Summary

### Suite 1: `test_desktop_automation_integrity.py` (8/8 PASS in 19.35s)
- **Test 1**: Single window launch -> 1 Notepad instance/tab created (**PASS**)
- **Test 2**: Window reuse -> Existing window targeted, 0 new processes (**PASS**)
- **Test 3**: Minimized window reuse -> Restored from iconic state, 0 new windows (**PASS**)
- **Test 4**: Real multiline typing with special characters (`{}[]()<>"'\|&%^$@#;:`) (**PASS**)
- **Test 5**: Exact equality readback verification (`EXPECTED == ACTUAL`) (**PASS**)
- **Test 6**: Authoritative application selection -> Notepad allowed, Word/VS Code rejected (**PASS**)
- **Test 7**: Idempotent operation deduplication -> Duplicate calls return cached result (**PASS**)
- **Test 8**: Failure injection & honest reporting -> Closed/invalid target reported cleanly (**PASS**)

### Suite 2: `test_notepad_multiline_typing_regression.py` (10/10 PASS in 93.76s)
- All 10 multiline, C code, anaphora, special characters, and security gate tests passed with 100% success on live Windows runtime.

---

## 5. Artifact Provenance
- Test Suite: [`tests/regression/test_desktop_automation_integrity.py`](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/tests/regression/test_desktop_automation_integrity.py)
- Verification Runner: [`scripts/verify_desktop_automation_live.py`](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/scripts/verify_desktop_automation_live.py)
- Forensic Evidence: [`audit/FINAL_RELEASE/DESKTOP_AUTOMATION_LIVE_EVIDENCE.json`](file:///c:/Users/Admin/OneDrive/Documents/Friday%20voice/audit/FINAL_RELEASE/DESKTOP_AUTOMATION_LIVE_EVIDENCE.json)
