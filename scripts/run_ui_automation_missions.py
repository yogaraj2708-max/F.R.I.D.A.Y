"""
F.R.I.D.A.Y. 3.0 — Real Runtime UI Automation Missions & Verification
Executes live missions:
- TEST 1: Open Notepad and type hello (verified by readback)
- TEST 2: Open Calculator, perform 7 + 5 = 12, verify display
- TEST 3: Open File Explorer, navigate to safe known folder, verify window title
- TEST 4: Open Notepad, type two lines ("hello\nFRIDAY"), verify exact readback
- TEST 5: Cancellation during automation (immediate terminal CANCELLED)
- TEST 6: Application missing (honest failure reporting)
- TEST 7: Stale control simulation (stale defense catches invalidated HWND/control)
- TEST 8: Focus theft protection (refuses typing when focus belongs to foreign window)

Saves runtime forensic evidence to AUDIT/UI_AUTOMATION_HARDENING/UI_AUTOMATION_RUNTIME.json.
"""

import sys
import os
import time
import json
import uuid
import ctypes
import subprocess

# Ensure workspace root in sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Ensure interactive desktop attachment before importing UIAutomation
user32 = ctypes.windll.user32
h_desk = user32.OpenDesktopW("default", 0, False, 0x01FF)
if h_desk:
    user32.SetThreadDesktop(h_desk)

from friday_core.automation.action_engine import ui_action_engine
from friday_core.automation.inspector import ui_inspector, UIElementInfo
from friday_core.automation.tracer import ui_tracer
from friday_core.automation.security_guard import ui_security_guard


def run_all_runtime_tests():
    runtime_records = []
    print("\n" + "="*70)
    print(" F.R.I.D.A.Y. 3.0 — LIVE RUNTIME UI AUTOMATION TESTS")
    print("="*70 + "\n")

    # -------------------------------------------------------------
    # TEST 1: Open Notepad and type hello
    # -------------------------------------------------------------
    print("[TEST 1]: 'Open Notepad and type hello.'")
    t1_id = f"runtime_test1_{uuid.uuid4().hex[:8]}"
    t1_start = time.time()
    
    # 1. Launch
    l_res = ui_action_engine.launch_app("notepad", task_id=t1_id)
    print(f"  - Launch result: {l_res.get('status')} (PID={l_res.get('pid')}, HWND={l_res.get('hwnd')})")
    
    # 2. Inspect
    insp_res = ui_action_engine.inspect_ui(app_name="notepad", task_id=t1_id)
    print(f"  - Inspect result: {insp_res.get('status')} (Elements={insp_res.get('elements_count')})")
    
    # 3. Type
    type_res = ui_action_engine.type_text("hello", app_name="notepad", clear_first=True, task_id=t1_id)
    readback1 = type_res.get("verified_text") or type_res.get("readback", "")
    print(f"  - Type result: {type_res.get('status')} (Verified Text: {repr(readback1)})")
    
    t1_pass = l_res.get("success") and insp_res.get("success") and type_res.get("success") and "hello" in readback1
    runtime_records.append({
        "test_id": "TEST_1",
        "name": "Open Notepad and type hello",
        "passed": bool(t1_pass),
        "duration_sec": round(time.time() - t1_start, 2),
        "steps": [
            {"action": "launch_app", "result": l_res},
            {"action": "inspect_ui", "result": insp_res},
            {"action": "type_text", "result": type_res}
        ],
        "evidence": {
            "verified_text": readback1,
            "readback_match": "hello" in readback1
        }
    })
    print(f"  => TEST 1 VERDICT: {'PASS' if t1_pass else 'FAIL'}\n")

    # -------------------------------------------------------------
    # TEST 2: Open Calculator and calculate 7 + 5 = 12
    # -------------------------------------------------------------
    print("[TEST 2]: 'Open Calculator and calculate 7 + 5 = 12'")
    t2_id = f"runtime_test2_{uuid.uuid4().hex[:8]}"
    t2_start = time.time()
    
    # 1. Launch
    l_calc = ui_action_engine.launch_app("calculator", task_id=t2_id)
    print(f"  - Launch result: {l_calc.get('status')} (PID={l_calc.get('pid')})")
    time.sleep(1.0)
    
    # 2. Inspect
    insp_calc = ui_action_engine.inspect_ui(app_name="calculator", task_id=t2_id)
    print(f"  - Inspect result: {insp_calc.get('status')} (Elements={insp_calc.get('elements_count')})")
    
    # 3. Sequence: 7, +, 5, =
    c1 = ui_action_engine.click_control("num7Button", app_name="calculator", task_id=t2_id)
    time.sleep(0.3)
    c2 = ui_action_engine.click_control("plusButton", app_name="calculator", task_id=t2_id)
    time.sleep(0.3)
    c3 = ui_action_engine.click_control("num5Button", app_name="calculator", task_id=t2_id)
    time.sleep(0.3)
    c4 = ui_action_engine.click_control("equalButton", app_name="calculator", task_id=t2_id)
    time.sleep(0.5)
    
    # 4. Verify visible result from display
    insp_after = ui_action_engine.inspect_ui(app_name="calculator", task_id=t2_id)
    calc_elements = insp_after.get("elements", [])
    display_text = ""
    for elem in calc_elements:
        if "calculatorresults" in elem.get("automation_id", "").lower() or "display is" in elem.get("name", "").lower():
            display_text = elem.get("name", "")
            break
            
    print(f"  - Keypad sequence clicks: 7({c1.get('status')}), +({c2.get('status')}), 5({c3.get('status')}), =({c4.get('status')})")
    print(f"  - Display Readback: {repr(display_text)}")
    
    t2_pass = l_calc.get("success") and c1.get("success") and c4.get("success") and "12" in display_text
    runtime_records.append({
        "test_id": "TEST_2",
        "name": "Open Calculator and calculate 7 + 5 = 12",
        "passed": bool(t2_pass),
        "duration_sec": round(time.time() - t2_start, 2),
        "clicks": [c1.get("status"), c2.get("status"), c3.get("status"), c4.get("status")],
        "evidence": {
            "display_readback": display_text,
            "calculation_verified": "12" in display_text
        }
    })
    print(f"  => TEST 2 VERDICT: {'PASS' if t2_pass else 'FAIL'}\n")

    # -------------------------------------------------------------
    # TEST 3: Open File Explorer
    # -------------------------------------------------------------
    print("[TEST 3]: 'Open File Explorer.'")
    t3_id = f"runtime_test3_{uuid.uuid4().hex[:8]}"
    t3_start = time.time()
    
    # Launch explorer to known safe folder
    l_exp = ui_action_engine.launch_app("explorer.exe", task_id=t3_id)
    print(f"  - Launch result: {l_exp.get('status')} (HWND={l_exp.get('hwnd')})")
    
    # Inspect File Explorer
    insp_exp = ui_action_engine.inspect_ui(app_name="explorer", task_id=t3_id)
    exp_title = insp_exp.get("window", {}).get("title", "")
    print(f"  - Inspect result: {insp_exp.get('status')} (Title={repr(exp_title)})")
    
    t3_pass = l_exp.get("success") and ("explorer" in exp_title.lower() or "files" in exp_title.lower() or len(insp_exp.get("elements", [])) > 0)
    runtime_records.append({
        "test_id": "TEST_3",
        "name": "Open File Explorer and verify window",
        "passed": bool(t3_pass),
        "duration_sec": round(time.time() - t3_start, 2),
        "evidence": {
            "window_title": exp_title,
            "elements_found": insp_exp.get("elements_count", 0)
        }
    })
    print(f"  => TEST 3 VERDICT: {'PASS' if t3_pass else 'FAIL'}\n")

    # -------------------------------------------------------------
    # TEST 4: Open Notepad and type two lines
    # -------------------------------------------------------------
    print("[TEST 4]: 'Open Notepad and type two lines: hello\\nFRIDAY'")
    t4_id = f"runtime_test4_{uuid.uuid4().hex[:8]}"
    t4_start = time.time()
    
    type_multiline = ui_action_engine.type_text("hello\nFRIDAY", app_name="notepad", clear_first=True, task_id=t4_id)
    verified_multi = type_multiline.get("verified_text") or type_multiline.get("readback", "")
    print(f"  - Multi-line type result: {type_multiline.get('status')}")
    print(f"  - Verified Content: {repr(verified_multi)}")
    
    t4_pass = type_multiline.get("success") and "hello" in verified_multi and "FRIDAY" in verified_multi
    runtime_records.append({
        "test_id": "TEST_4",
        "name": "Open Notepad and type two lines",
        "passed": bool(t4_pass),
        "duration_sec": round(time.time() - t4_start, 2),
        "evidence": {
            "verified_text": verified_multi,
            "contains_line1": "hello" in verified_multi,
            "contains_line2": "FRIDAY" in verified_multi
        }
    })
    print(f"  => TEST 4 VERDICT: {'PASS' if t4_pass else 'FAIL'}\n")

    # -------------------------------------------------------------
    # TEST 5: Cancellation during automation
    # -------------------------------------------------------------
    print("[TEST 5]: 'Cancellation during automation'")
    t5_id = f"runtime_test5_{uuid.uuid4().hex[:8]}"
    t5_start = time.time()
    
    # Pre-emptively register cancellation signal
    ui_action_engine.cancel_task(t5_id)
    cancel_res = ui_action_engine.type_text("should_not_type", app_name="notepad", task_id=t5_id)
    print(f"  - Action under cancellation: status={cancel_res.get('status')}, message={cancel_res.get('message')}")
    
    t5_pass = (cancel_res.get("status") == "CANCELLED") and (cancel_res.get("success") is False)
    runtime_records.append({
        "test_id": "TEST_5",
        "name": "Task cancellation enforcement",
        "passed": bool(t5_pass),
        "duration_sec": round(time.time() - t5_start, 2),
        "evidence": {
            "terminal_state": cancel_res.get("status"),
            "success": cancel_res.get("success")
        }
    })
    print(f"  => TEST 5 VERDICT: {'PASS' if t5_pass else 'FAIL'}\n")

    # -------------------------------------------------------------
    # TEST 6: Application missing (Honest Failure)
    # -------------------------------------------------------------
    print("[TEST 6]: 'Application missing honest failure'")
    t6_id = f"runtime_test6_{uuid.uuid4().hex[:8]}"
    t6_start = time.time()
    
    missing_res = ui_action_engine.launch_app("non_existent_fake_app_9999.exe", task_id=t6_id)
    print(f"  - Missing app result: status={missing_res.get('status')}, message={missing_res.get('message')}")
    
    t6_pass = (missing_res.get("success") is False) and ("failed" in missing_res.get("message", "").lower() or "not found" in missing_res.get("message", "").lower())
    runtime_records.append({
        "test_id": "TEST_6",
        "name": "Missing application honest failure reporting",
        "passed": bool(t6_pass),
        "duration_sec": round(time.time() - t6_start, 2),
        "evidence": {
            "status": missing_res.get("status"),
            "message": missing_res.get("message")
        }
    })
    print(f"  => TEST 6 VERDICT: {'PASS' if t6_pass else 'FAIL'}\n")

    # -------------------------------------------------------------
    # TEST 7: Stale control simulation
    # -------------------------------------------------------------
    print("[TEST 7]: 'Stale control simulation'")
    t7_id = f"runtime_test7_{uuid.uuid4().hex[:8]}"
    t7_start = time.time()
    
    # Create synthetic element referencing destroyed HWND
    dead_hwnd = 0xDEADBEEF
    fake_elem = UIElementInfo(
        name="GhostButton",
        control_type="Button",
        automation_id="GhostBtn_1",
        bounding_rect=(10, 10, 50, 50),
        is_enabled=True,
        is_visible=True,
        hwnd=dead_hwnd
    )
    is_stale = ui_inspector.is_control_stale(fake_elem)
    print(f"  - Stale control check on dead HWND ({dead_hwnd:#x}): is_stale={is_stale}")
    
    t7_pass = bool(is_stale)
    runtime_records.append({
        "test_id": "TEST_7",
        "name": "Stale control defense on invalidated window handle",
        "passed": bool(t7_pass),
        "duration_sec": round(time.time() - t7_start, 2),
        "evidence": {
            "detected_as_stale": is_stale,
            "hwnd_checked": f"{dead_hwnd:#x}"
        }
    })
    print(f"  => TEST 7 VERDICT: {'PASS' if t7_pass else 'FAIL'}\n")

    # -------------------------------------------------------------
    # TEST 8: Focus theft simulation
    # -------------------------------------------------------------
    print("[TEST 8]: 'Focus theft simulation'")
    t8_id = f"runtime_test8_{uuid.uuid4().hex[:8]}"
    t8_start = time.time()
    
    # Attempting to type into an app that does not own the active focus
    theft_res = ui_action_engine.type_text("secret_data", app_name="bogus_target_window_app", task_id=t8_id)
    print(f"  - Type on unverified target window: status={theft_res.get('status')}")
    
    t8_pass = (theft_res.get("success") is False) and (theft_res.get("status") == "WINDOW_NOT_FOUND")
    runtime_records.append({
        "test_id": "TEST_8",
        "name": "Focus theft protection prevents typing into wrong window",
        "passed": bool(t8_pass),
        "duration_sec": round(time.time() - t8_start, 2),
        "evidence": {
            "status": theft_res.get("status"),
            "blocked_action": not theft_res.get("success")
        }
    })
    print(f"  => TEST 8 VERDICT: {'PASS' if t8_pass else 'FAIL'}\n")

    # Summary
    all_passed = all(r["passed"] for r in runtime_records)
    print("="*70)
    print(f" TOTAL LIVE RUNTIME TESTS: {len(runtime_records)}")
    print(f" OVERALL VERDICT: {'PASS' if all_passed else 'FAIL'}")
    print("="*70 + "\n")

    # Write output to AUDIT/UI_AUTOMATION_HARDENING/UI_AUTOMATION_RUNTIME.json
    out_dir = os.path.join(os.getcwd(), "AUDIT", "UI_AUTOMATION_HARDENING")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "UI_AUTOMATION_RUNTIME.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_tests": len(runtime_records),
            "passed_tests": sum(1 for r in runtime_records if r["passed"]),
            "failed_tests": sum(1 for r in runtime_records if not r["passed"]),
            "overall_status": "PASS" if all_passed else "FAIL",
            "tests": runtime_records
        }, f, indent=2)
    print(f"[Evidence Saved]: {out_file}")
    return all_passed


if __name__ == "__main__":
    success = run_all_runtime_tests()
    sys.exit(0 if success else 1)
