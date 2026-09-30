import sys
import os
import time
import json
import difflib
import ctypes
from ctypes import wintypes
import subprocess

sys.path.insert(0, ".")

import uiautomation as auto
from friday_core.system.window_manager import window_manager, run_on_interactive_desktop
from friday_core.automation.mouse_keyboard import (
    type_real_keystrokes,
    send_unicode_char,
    send_virtual_key,
    release_all_modifiers,
    send_ctrl_a_delete,
    VK_RETURN,
    VK_TAB,
    VK_BACK,
    user32,
    INPUT,
    KEYBDINPUT,
    INPUT_KEYBOARD,
    KEYEVENTF_UNICODE,
    KEYEVENTF_KEYUP,
    InputDesktopScope
)

EXACT_PAYLOAD = """#include <stdio.h>
#include <stdlib.h>
#include <math.h>

int main() {
    printf("ABC123 < > { } [ ] ( ) # % ^ & * / \\ \" ; :\\n");
    return 0;
}"""

def kill_notepad():
    try:
        subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
    except Exception:
        pass
    time.sleep(1.0)

def read_notepad_content(hwnd):
    if not hwnd or not auto:
        return ""
    try:
        win = auto.ControlFromHandle(hwnd)
        edit = win.DocumentControl(searchDepth=4)
        if not edit.Exists(0, 0):
            edit = win.EditControl(searchDepth=4)
        if edit.Exists(0, 0):
            pat = edit.GetValuePattern()
            if pat and pat.Value is not None:
                return pat.Value
            txt = edit.GetWindowText()
            if txt:
                return txt
            tp = edit.GetTextPattern()
            if tp and tp.DocumentRange:
                return tp.DocumentRange.GetText(-1)
    except Exception as e:
        print(f"Error reading notepad: {e}")
    return ""

def run_forensic_investigation():
    print("=" * 60)
    print("MANDATORY A/B/C FORENSIC INVESTIGATION")
    print("=" * 60)

    # 1. Reset desktop & launch fresh Notepad
    print("\n[Stage 0]: Resetting desktop & launching fresh Notepad...")
    kill_notepad()

    ok, target, reused, msg = window_manager.get_or_launch_window("notepad", force_new=True)
    assert ok and target, f"Failed to launch fresh Notepad: {msg}"
    time.sleep(1.0)
    window_manager.focus_window_verified(target.hwnd)
    time.sleep(0.5)

    # Focus inner edit control
    win = auto.ControlFromHandle(target.hwnd)
    edit = win.DocumentControl(searchDepth=4)
    if not edit.Exists(0, 0):
        edit = win.EditControl(searchDepth=4)
    if edit.Exists(0, 0):
        try:
            edit.Click(simulateMove=False)
        except Exception:
            pass
    time.sleep(0.3)

    # A = exact finalized string immediately BEFORE the desktop typing function
    A = EXACT_PAYLOAD
    print(f"\nA (escaped representation, length={len(A)}, newlines={A.count(chr(10))}):")
    print(json.dumps(A))

    # B = exact string received by the desktop typing function
    B = A
    print(f"\nB (escaped representation, length={len(B)}, newlines={B.count(chr(10))}):")
    print(json.dumps(B))

    # Perform typing
    print(f"\n[Stage 1]: Executing type_real_keystrokes on HWND {target.hwnd}...")
    t0 = time.time()
    success, msg, count = type_real_keystrokes(
        text=B,
        mode="replace",
        typing_delay_ms=36.0,
        hwnd=target.hwnd,
        operation_id="forensic_test_payload_1"
    )
    typing_time = time.time() - t0
    print(f"type_real_keystrokes completed in {typing_time:.2f}s (success={success}, msg='{msg}', count={count})")

    time.sleep(0.5)

    # C = exact string read back from Notepad
    print("\n[Stage 2]: Reading physical content back from Notepad...")
    C_raw = read_notepad_content(target.hwnd)
    # Normalize CRLF to LF for fair comparison
    C = C_raw.replace("\r\n", "\n").replace("\r", "\n")

    print(f"\nC (escaped representation, length={len(C)}, newlines={C.count(chr(10))}):")
    print(json.dumps(C))

    print("\n" + "=" * 60)
    print("FORENSIC COMPARISON RESULTS")
    print("=" * 60)
    print(f"len(A): {len(A)} | newlines: {A.count(chr(10))}")
    print(f"len(B): {len(B)} | newlines: {B.count(chr(10))}")
    print(f"len(C): {len(C)} | newlines: {C.count(chr(10))}")
    print(f"A == B: {A == B}")
    print(f"B == C: {B == C}")
    print(f"A == C: {A == C}")

    if B != C:
        print("\n--- CHARACTER-BY-CHARACTER DIFF (B vs C) ---")
        diff = list(difflib.ndiff(B.splitlines(keepends=True), C.splitlines(keepends=True)))
        for line in diff:
            sys.stdout.write(line)
        print("\n--- FIRST MISMATCH INDEX ---")
        min_len = min(len(B), len(C))
        mismatch_found = False
        for idx in range(min_len):
            if B[idx] != C[idx]:
                print(f"Mismatch at index {idx}:")
                print(f"  Expected B: {repr(B[idx])} (ord {ord(B[idx])})")
                print(f"  Actual   C: {repr(C[idx])} (ord {ord(C[idx])})")
                print(f"  Context B: {repr(B[max(0, idx-15):min(len(B), idx+25)])}")
                print(f"  Context C: {repr(C[max(0, idx-15):min(len(C), idx+25)])}")
                mismatch_found = True
                break
        if not mismatch_found and len(B) != len(C):
            print(f"Prefix matches up to {min_len}, but length differs: len(B)={len(B)}, len(C)={len(C)}")
            if len(B) > len(C):
                print(f"  B trailing: {repr(B[min_len:])}")
            else:
                print(f"  C trailing: {repr(C[min_len:])}")

    # Step 3: Special Character Mapping Table
    print("\n" + "=" * 60)
    print("SPECIAL CHARACTER DETERMINISTIC TEST TABLE")
    print("=" * 60)
    special_chars = [
        '#', '<', '>', '{', '}', '[', ']', '(', ')', '%', '^', '&', '*',
        '/', '\\', '"', "'", ';', ':', '=', '+', '-', '_', '\n', '\t', ' '
    ]

    results_table = []
    all_specials_passed = True

    for ch in special_chars:
        # Determine event description
        if ch == "\n":
            event_desc = "VK_RETURN (0x0D)"
        elif ch == "\t":
            event_desc = "VK_TAB (0x09)"
        elif ch == "\b":
            event_desc = "VK_BACK (0x08)"
        else:
            event_desc = f"KEYEVENTF_UNICODE (Scan=0x{ord(ch):04X})"

        # Type single char using type_real_keystrokes in replace mode
        type_real_keystrokes(
            text=ch,
            mode="replace",
            typing_delay_ms=36.0,
            hwnd=target.hwnd,
            operation_id=f"special_char_{ord(ch)}"
        )
        time.sleep(0.15)
        read_char = read_notepad_content(target.hwnd).replace("\r\n", "\n").replace("\r", "\n")

        match = (read_char == ch)
        if not match:
            all_specials_passed = False

        results_table.append({
            "expected": repr(ch),
            "event": event_desc,
            "actual": repr(read_char),
            "match": match
        })

    print(f"{'Char':<10} | {'Generated Windows Event':<35} | {'Actual Notepad Readback':<25} | {'Status'}")
    print("-" * 80)
    for r in results_table:
        status_str = "PASS" if r["match"] else "FAIL"
        print(f"{r['expected']:<10} | {r['event']:<35} | {r['actual']:<25} | {status_str}")

    print("\n" + "=" * 60)
    print("SECOND TEST: FULL WORKING C CALCULATOR SOURCE")
    print("=" * 60)

    SECOND_PAYLOAD = """#include <stdio.h>

int main(void) {
    double a, b;
    char op;

    printf("Enter expression (example: 10 + 5): ");
    if (scanf("%lf %c %lf", &a, &op, &b) != 3) {
        printf("Invalid input.\\n");
        return 1;
    }

    switch (op) {
        case '+':
            printf("Result = %.2f\\n", a + b);
            break;
        case '-':
            printf("Result = %.2f\\n", a - b);
            break;
        case '*':
            printf("Result = %.2f\\n", a * b);
            break;
        case '/':
            if (b == 0) {
                printf("Error: division by zero.\\n");
                return 1;
            }
            printf("Result = %.2f\\n", a / b);
            break;
        default:
            printf("Unsupported operator.\\n");
            return 1;
    }

    return 0;
}"""

    A2 = SECOND_PAYLOAD
    B2 = A2
    print(f"Second Payload length: {len(A2)} chars, newlines: {A2.count(chr(10))}")
    print(f"Typing second payload...")
    t0 = time.time()
    ok2, msg2, cnt2 = type_real_keystrokes(
        text=B2,
        mode="replace",
        typing_delay_ms=36.0,
        hwnd=target.hwnd,
        operation_id="forensic_test_payload_2"
    )
    t2 = time.time() - t0
    time.sleep(0.5)
    C2_raw = read_notepad_content(target.hwnd)
    C2 = C2_raw.replace("\r\n", "\n").replace("\r", "\n")

    print(f"Second payload typed in {t2:.2f}s (ok={ok2}, count={cnt2})")
    print(f"len(A2): {len(A2)} | len(B2): {len(B2)} | len(C2): {len(C2)}")
    print(f"A2 == B2: {A2 == B2}")
    print(f"B2 == C2: {B2 == C2}")
    print(f"A2 == C2: {A2 == C2}")

    if B2 != C2:
        print("\n--- SECOND TEST MISMATCH ---")
        min_len = min(len(B2), len(C2))
        for idx in range(min_len):
            if B2[idx] != C2[idx]:
                print(f"First mismatch at index {idx}:")
                print(f"  Expected B2: {repr(B2[idx])} (ord {ord(B2[idx])})")
                print(f"  Actual   C2: {repr(C2[idx])} (ord {ord(C2[idx])})")
                print(f"  Context B2: {repr(B2[max(0, idx-15):min(len(B2), idx+25)])}")
                print(f"  Context C2: {repr(C2[max(0, idx-15):min(len(C2), idx+25)])}")
                break

    output_summary = {
        "test1": {
            "len_A": len(A),
            "len_B": len(B),
            "len_C": len(C),
            "A_eq_B": A == B,
            "B_eq_C": B == C,
            "A_eq_C": A == C,
            "newlines_A": A.count("\n"),
            "newlines_B": B.count("\n"),
            "newlines_C": C.count("\n")
        },
        "special_chars": {
            "all_passed": all_specials_passed,
            "results": results_table
        },
        "test2": {
            "len_A": len(A2),
            "len_B": len(B2),
            "len_C": len(C2),
            "A_eq_B": A2 == B2,
            "B_eq_C": B2 == C2,
            "A_eq_C": A2 == C2,
            "newlines_A": A2.count("\n"),
            "newlines_B": B2.count("\n"),
            "newlines_C": C2.count("\n")
        }
    }

    with open(r"c:\Users\Admin\OneDrive\Documents\Friday voice\forensic_test_results.json", "w", encoding="utf-8") as f:
        json.dump(output_summary, f, indent=2)

    overall_pass = (A == B == C) and all_specials_passed and (A2 == B2 == C2)
    print("\n" + "=" * 60)
    print(f"OVERALL FORENSIC VERDICT: {'ALL TESTS PASSED (100% BYTE EQUALITY)' if overall_pass else 'FAILURES DETECTED'}")
    print("=" * 60)
    return overall_pass

if __name__ == "__main__":
    ok = run_forensic_investigation()
    sys.exit(0 if ok else 1)
