# F.R.I.D.A.Y. 2.0 / 3.0 — Forensic Regression Audit Report
## Regression Fix: Real Keystroke Typing vs Programmatic SetValue / Clipboard Paste

**Status**: **PASS**  
**Audit Date**: 2026-09-28  
**Target Environment**: Windows 11 (64-bit), Native Desktop UI Automation & User32 SendInput  
**Authoring Agent**: Antigravity (DeepMind Advanced Agentic Coding)

---

## 1. Executive Summary

| Category | Description | Status |
| :--- | :--- | :--- |
| **Real Keystroke Typing** | `user32.SendInput` character-by-character native keyboard injection | **PASS** |
| **No Programmatic SetValue** | `ValuePattern.SetValue` prohibited for normal typing insertion | **PASS** |
| **No Clipboard Paste** | User clipboard untouched; `Ctrl+V` and `WM_PASTE` prohibited for normal typing | **PASS** |
| **Small Text Typing** | `"hello world"` typed progressively with natural keystroke timing | **PASS** |
| **Multiline Text** | Newlines emit genuine `VK_RETURN` key-down/key-up events | **PASS** |
| **C Code with Braces** | `#include <stdio.h>` with `{`, `}`, quotes, indents typed literally | **PASS** |
| **Large Multiline Code** | Complete Scientific Calculator C program (~1,800 chars) typed progressively | **PASS** |
| **Conversation Anaphora** | `"put that code in my notepad"` extracts prior turn's code block | **PASS** |
| **Special Characters** | `{}[]()<>"'\|&%^$` injected via `KEYEVENTF_UNICODE` without syntax parser | **PASS** |
| **Exact Readback Equality** | CRLF-normalized `actual == expected` character equality invariant | **PASS** |
| **Security Gates** | `AutomationSecurityGuard` & `SecurityGatekeeper` active and blocking malicious commands | **PASS** |
| **Automated Test Suite** | 10/10 automated regression tests passing in live Windows runtime | **PASS** |

---

## 2. Problem Statement & UX Regression Context

### 2.1 The Previous UX Regression
While the initial fix restored multiline code insertion reliability into Notepad by adopting `ValuePattern.SetValue` and clipboard paste, it introduced a significant **user experience regression**:
- Text appeared instantly in bulk, resembling a clipboard paste or programmatic injection.
- The visual sensation of F.R.I.D.A.Y. interactively and progressively typing character-by-character was lost.
- The user explicitly required:
  > *"REAL KEYSTROKE TYPING REQUIRED — NOT PASTE / NOT SETVALUE. I want BOTH reliable insertion and natural visible typing behavior. It should look like F.R.I.D.A.Y. is actually typing."*

### 2.2 Strict Architectural Separation
To guarantee both reliability and the required visible typing UX, three distinct insertion strategies are enforced:

1. **`REAL_KEYSTROKE` (Primary Default Mode)**:
   - Emits real Windows keyboard events via `user32.SendInput`.
   - Uses `KEYEVENTF_UNICODE` for all printable characters.
   - Emits actual Virtual Key codes for control keys: `VK_RETURN` (`0x0D`), `VK_TAB` (`0x09`), `VK_BACK` (`0x08`), `VK_DELETE` (`0x2E`).
   - Uses real keyboard combos for mode preparation: `Ctrl+A` then `Delete` for replace mode; `Ctrl+End` for append mode.
   - Configurable inter-character delay (`typing_delay_ms`, default 5ms).
   - Progressive visibility in the target window.

2. **`PROGRAMMATIC_SETVALUE` (Restricted / Readback Only)**:
   - Uses `IUIAutomationValuePattern.SetValue(text)`.
   - **Strictly prohibited** for insertion in normal user-facing typing paths.
   - Retained solely for independent readback verification and programmatic inspection.

3. **`CLIPBOARD_FALLBACK` (Explicit Emergency Fallback Only)**:
   - Uses `OpenClipboard` / `SetClipboardData` + `Ctrl+V` or `WM_PASTE`.
   - **Strictly prohibited** for normal typing paths; user clipboard must remain unaltered.

---

## 3. Engineering Implementation Details

### 3.1 64-bit Compliant Windows User32 `SendInput` Engine
In `friday_core/automation/mouse_keyboard.py`:
- Defined exact 64-bit C-structure layout for `INPUT`, `KEYBDINPUT`, `MOUSEINPUT`, and `HARDWAREINPUT` (`ctypes.sizeof(INPUT) == 40`).
- Implemented `InputDesktopScope`:
  ```python
  class InputDesktopScope:
      """Context manager that temporarily attaches the thread to the active user input desktop."""
      def __enter__(self):
          if IS_WINDOWS and user32:
              self.h_orig = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
              self.h_input = user32.OpenInputDesktop(0, False, 0x01FF)
              if self.h_input:
                  user32.SetThreadDesktop(self.h_input)
          return self

      def __exit__(self, exc_type, exc_val, exc_tb):
          if IS_WINDOWS and user32:
              if self.h_orig and self.h_input:
                  user32.SetThreadDesktop(self.h_orig)
                  user32.CloseDesktop(self.h_input)
  ```
- Scoped desktop attachment ensures that `SendInput` executes with full interactive desktop permissions without interfering with UI Automation window searches on the Default desktop.

### 3.2 Literal Keystroke Emission Without Syntax Parsing
- Prior implementations using `SendKeys(text)` crashed on braces (`{...}`) because `SendKeys` interpreted braces as virtual key tokens.
- `type_real_keystrokes` processes characters directly:
  - Printable characters $\le \text{0xFFFF}$ pass scan code `ord(ch)` to `KEYEVENTF_UNICODE`.
  - Non-BMP characters (> 0xFFFF) are split into UTF-16 surrogate pairs.
  - Newlines (`\n`) emit `VK_RETURN` (`0x0D`).
  - Tabs (`\t`) emit `VK_TAB` (`0x09`).
  - No parsing of `{`, `}`, `[`, `]`, `\`, `"`, `'`, `%`, `^`, or `&` occurs.

### 3.3 Focus Safety & Continuous Window Verification
- Target HWND is verified via `user32.IsWindow(hwnd)`.
- Window is restored and brought to top via `ShowWindow(hwnd, SW_RESTORE)` and `SetForegroundWindow(hwnd)`.
- During long typing loops (such as full C programs), window validity is verified every 25 keystrokes. If the target window closes or disappears, typing halts immediately with descriptive telemetry rather than sending orphaned keystrokes.

### 3.4 Readback Exact Equality Invariant
- Windows 11 Notepad uses `RichEditD2DPT` which separates lines with `\r`.
- Readback verification normalizes CRLF (`\r\n` and `\r` $\rightarrow$ `\n`) on both actual and expected strings.
- Enforces strict character-by-character equality: `actual == expected`.

---

## 4. Test Suite Verification Matrix

All 10 regression scenarios were executed and validated against live Windows 11 Notepad:

| # | Test Case | Target Content | Expected Insertion Mode | Readback Verification | Result |
| :-: | :--- | :--- | :---: | :---: | :---: |
| 1 | Small Text | `"hello world"` | `REAL_KEYSTROKE` | Exact equality (`==`) | **PASS** |
| 2 | Multiline Text | `"line one\nline two\nline three"` | `REAL_KEYSTROKE` | Exact equality (`==`) | **PASS** |
| 3 | C Code with Braces | `#include <stdio.h>... int main() { return 0; }` | `REAL_KEYSTROKE` | Exact equality (`==`) | **PASS** |
| 4 | Large Multiline Code | Scientific Calculator in C (~1,800 characters) | `REAL_KEYSTROKE` | Exact equality (`==`) | **PASS** |
| 5 | Conversation Anaphora | `"put that code in my notepad"` | Fast-Path Anaphora Extraction | Exact C block extracted | **PASS** |
| 6 | Special Characters | `{}[]()<>"'\|&%^$` | `REAL_KEYSTROKE` | Exact equality (`==`) | **PASS** |
| 7 | Invariant Verification | `Exact Readback Equality Invariant 2026: printf(...)` | `REAL_KEYSTROKE` | Exact equality (`==`) | **PASS** |
| 8 | Security Gatekeeper | Harmless C code vs `"format C: /y"` | Evaluated by Security Guard | Allowed vs Blocked | **PASS** |
| 9 | Clipboard Preservation | Sentinel clipboard text `"PRESERVED_USER_CLIPBOARD_SECRET_98765"` | `REAL_KEYSTROKE` | Clipboard 100% unaltered | **PASS** |
| 10 | SetValue Not Used | UI Automation `ValuePattern.SetValue` monitored | `REAL_KEYSTROKE` | `SetValue.assert_not_called()` | **PASS** |

---

## 5. Live Windows Runtime Evidence

```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\Admin\OneDrive\Documents\Friday voice
configfile: pytest.ini
plugins: anyio-4.15.1, asyncio-1.4.0

tests/regression/test_notepad_multiline_typing_regression.py::test_regression_test_1_small_text PASSED
tests/regression/test_notepad_multiline_typing_regression.py::test_regression_test_2_multiline PASSED
tests/regression/test_notepad_multiline_typing_regression.py::test_regression_test_3_c_code_with_braces PASSED
tests/regression/test_notepad_multiline_typing_regression.py::test_regression_test_4_large_multiline_code PASSED
tests/regression/test_notepad_multiline_typing_regression.py::test_regression_test_5_conversation_anaphora PASSED
tests/regression/test_notepad_multiline_typing_regression.py::test_regression_test_6_special_characters PASSED
tests/regression/test_notepad_multiline_typing_regression.py::test_regression_test_7_readback_exact_equality PASSED
tests/regression/test_notepad_multiline_typing_regression.py::test_regression_test_8_security_gates_active PASSED
tests/regression/test_notepad_multiline_typing_regression.py::test_regression_test_9_no_clipboard_used_for_typing PASSED
tests/regression/test_notepad_multiline_typing_regression.py::test_regression_test_10_no_valuepattern_setvalue_for_insertion PASSED

============================= 10 passed in 88.42s =============================
```

### 5.1 Verification Checklist
- [x] Visible character-by-character typing verified.
- [x] No `ValuePattern.SetValue` text replacement in normal typing path.
- [x] No clipboard modification or `Ctrl+V` pasting.
- [x] Braces and multiline formatting preserved identically.
- [x] Exact character readback equality confirmed.
- [x] All security gatekeepers fully intact.

---

## 6. Conclusion & Sign-Off

The regression fix is complete and verified. F.R.I.D.A.Y. now types code and text into Notepad using native Windows keystrokes with progressive visual feedback, zero syntax-parsing crashes, zero clipboard interference, and strict readback verification.

**Final Verdict**: **PASS**
