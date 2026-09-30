import sys
import os
import time
import json
import uiautomation as auto

sys.path.insert(0, ".")

from friday_core.system.window_manager import window_manager
from friday_core.skills.builtins.ui_automation import (
    UITypeTextSkill,
    UITypeTextInput,
    find_app_window
)
from friday_core.automation.mouse_keyboard import type_real_keystrokes

TEST_PAYLOAD = """#include <stdio.h>
#include <stdlib.h>
#include <math.h>

int main() {
    printf("Hello <world> {test} [123] (456) % ^ & * / \\ \" ; :\\n");
    return 0;
}"""

def analyze_string(name: str, s: str):
    special_chars = set("<>{}[ ]()%^&*/\\\"';:")
    special_count = sum(1 for c in s if c in special_chars)
    print(f"[{name}]")
    print(f"  Length: {len(s)} chars")
    print(f"  UTF-8 bytes: {len(s.encode('utf-8'))}")
    print(f"  UTF-16 code units: {len(s.encode('utf-16-le')) // 2}")
    print(f"  First char: {repr(s[0]) if s else None}")
    print(f"  Last char: {repr(s[-1]) if s else None}")
    print(f"  Newline count: {s.count(chr(10))} (CRLF: {s.count(chr(13)+chr(10))})")
    print(f"  Special chars count: {special_count}")

def run_pipeline_trace():
    print("=" * 60)
    print("PHASE 1: TRACING COMPLETE DATA PATH WITH DETERMINISTIC PAYLOAD")
    print("=" * 60)

    # Stage 1: Raw Payload
    stage1_content = TEST_PAYLOAD
    analyze_string("Stage 1: Raw Source Payload", stage1_content)

    # Stage 2: Final Content Extraction
    # Simulating what content_generation skill emits
    stage2_extracted = stage1_content.strip()
    analyze_string("Stage 2: Final Content Extraction", stage2_extracted)
    assert stage2_extracted == stage1_content, "Stage 2 differed from Stage 1!"

    # Stage 3: Mission/Tool Arguments Serialization
    tool_input = UITypeTextInput(
        app_name="Notepad",
        text=stage2_extracted,
        mode="replace"
    )
    stage3_arg_text = tool_input.text
    analyze_string("Stage 3: Tool Input Text Argument", stage3_arg_text)
    assert stage3_arg_text == stage2_extracted, "Stage 3 differed from Stage 2!"

    # Stage 4: Prepare Real Notepad Window
    print("\nEnsuring single clean Notepad window...")
    ok, target, reused, msg = window_manager.get_or_launch_window("notepad", force_new=False)
    assert ok and target, f"Failed to get Notepad window: {msg}"
    time.sleep(0.5)

    win = auto.ControlFromHandle(target.hwnd)
    edit = win.DocumentControl()
    if not edit.Exists(0, 0):
        edit = win.EditControl()
    assert edit.Exists(0, 0), "Could not find DocumentControl or EditControl in Notepad"

    # Reset editor
    vp = None
    try:
        vp = edit.GetValuePattern()
        if vp:
            vp.SetValue("")
    except Exception:
        pass
    time.sleep(0.2)

    # Stage 4 & 5: Desktop text insertion / Keyboard input transport
    print("\n[Stage 4 & 5]: Executing type_real_keystrokes...")
    t0 = time.time()
    success, msg, count = type_real_keystrokes(
        text=stage3_arg_text,
        mode="replace",
        typing_delay_ms=8.0,
        hwnd=target.hwnd
    )
    dur = time.time() - t0
    print(f"Typing completed in {dur:.2f}s: success={success}, msg='{msg}', count={count}")

    # Stage 6 & 7: Readback from live Notepad
    time.sleep(0.8)
    readback = ""
    try:
        fresh_edit = win.DocumentControl(searchDepth=4)
        if not fresh_edit.Exists(0, 0):
            fresh_edit = win.EditControl(searchDepth=4)
        if fresh_edit.Exists(0, 0):
            vp_after = fresh_edit.GetValuePattern()
            if vp_after and vp_after.Value:
                readback = vp_after.Value
            if not readback:
                tp = fresh_edit.GetTextPattern()
                if tp and tp.DocumentRange:
                    readback = tp.DocumentRange.GetText(-1)
            if not readback:
                readback = fresh_edit.GetWindowText() or ""
    except Exception as ex:
        print(f"Readback exception: {ex}")

    analyze_string("Stage 6 & 7: Live Notepad Readback", readback)

    # Comparison
    norm_expected = stage1_content.replace("\r\n", "\n").replace("\r", "\n").strip()
    norm_actual = readback.replace("\r\n", "\n").replace("\r", "\n").strip()

    print("\n" + "=" * 60)
    print("EXACT STRING EQUALITY CHECK:")
    print(f"Expected len: {len(norm_expected)}")
    print(f"Actual len:   {len(norm_actual)}")
    matches = (norm_actual == norm_expected)
    print(f"EXACT MATCH: {matches}")
    print("=" * 60)

    if not matches:
        print("\nFIRST DIFFERENCE DETECTED AT:")
        min_len = min(len(norm_actual), len(norm_expected))
        first_diff_idx = -1
        for i in range(min_len):
            if norm_actual[i] != norm_expected[i]:
                first_diff_idx = i
                print(f"Index {i}:")
                print(f"  Expected char: {repr(norm_expected[i])} (ord={ord(norm_expected[i])})")
                print(f"  Actual char:   {repr(norm_actual[i])} (ord={ord(norm_actual[i])})")
                print(f"  Expected context: {repr(norm_expected[max(0, i-15):min(len(norm_expected), i+25)])}")
                print(f"  Actual context:   {repr(norm_actual[max(0, i-15):min(len(norm_actual), i+25)])}")
                break
        if first_diff_idx == -1:
            print(f"Difference is length! Expected has {len(norm_expected)} chars, Actual has {len(norm_actual)} chars.")
            if len(norm_actual) > len(norm_expected):
                print(f"Extra actual tail: {repr(norm_actual[min_len:])}")
            else:
                print(f"Missing expected tail: {repr(norm_expected[min_len:])}")

        return False

    print("\nSUCCESS: All characters and special symbols typed and read back with 100% byte-for-byte fidelity!")
    return True

if __name__ == "__main__":
    ok = run_pipeline_trace()
    sys.exit(0 if ok else 1)
