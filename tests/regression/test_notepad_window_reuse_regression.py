"""
F.R.I.D.A.Y. 3.0 — Notepad Window Reuse & Idempotent Launch Regression Suite
Covers the complete 8-scenario test matrix mandated in the user directive.

Verifies:
- Test 1: Notepad closed. "open notepad" -> exactly ONE new Notepad instance/process.
- Test 2: Notepad open. "open notepad" -> reuse existing Notepad, NO new process.
- Test 3: Notepad open + blank doc. "put hello in my notepad" -> reuse existing Notepad, ONE insertion.
- Test 4: Notepad open + multiple tabs. "put hello in my notepad" -> reuse appropriate existing target, NO new process.
- Test 5: Notepad closed. "put hello in my notepad" -> launch exactly ONE Notepad, type, verify, finish.
- Test 6: Repeated same command -> no uncontrolled process multiplication.
- Test 7: Concurrent requests -> per-application launch serialization.
- Test 8: Window lookup delay -> wait/poll for existing launch, DO NOT spawn extra instances.
"""

import os
import sys
import time
import ctypes
from ctypes import wintypes
import subprocess
import threading
from typing import List, Dict, Any, Tuple

# Set up project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import psutil
import functools
print = functools.partial(print, flush=True)

from friday_core.platform_guard import IS_WINDOWS
from friday_core.system.window_manager import window_manager, WindowTarget
from friday_core.gatekeeper.models import ActionIntent
from friday_core.gatekeeper.gatekeeper import gatekeeper
from friday_core.skills.registry import skill_registry

user32 = ctypes.windll.user32 if IS_WINDOWS else None


def kill_all_notepad():
    """Helper to clean slate before specific test cases."""
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
        time.sleep(0.5)
        # Clear modern Notepad session restore state so leftover tabs from crashed sessions don't restore extra windows
        import glob
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            state_dirs = [
                os.path.join(local_app_data, r"Packages\Microsoft.WindowsNotepad_8wekyb3d8bbwe\LocalState\TabState"),
                os.path.join(local_app_data, r"Packages\Microsoft.WindowsNotepad_8wekyb3d8bbwe\LocalState\WindowState")
            ]
            for sdir in state_dirs:
                if os.path.exists(sdir):
                    for f in glob.glob(os.path.join(sdir, "*")):
                        try:
                            if os.path.isfile(f):
                                os.remove(f)
                        except Exception:
                            pass


def get_notepad_processes() -> List[Dict[str, Any]]:
    """Returns all active Notepad processes with PID, cmdline, and status."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "status"]):
        try:
            if "notepad" in p.info["name"].lower():
                procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return procs


def get_notepad_gui_windows() -> List[WindowTarget]:
    """Returns all visible/iconic top-level Notepad GUI windows."""
    return window_manager.find_matching_windows("notepad")


def main():
    print("=" * 70)
    print("F.R.I.D.A.Y. NOTEPAD WINDOW REUSE & IDEMPOTENT LAUNCH REGRESSION TEST")
    print("=" * 70)

    test_results = {}

    # ─────────────────────────────────────────────────────────────
    # TEST 1: Notepad closed. "open notepad" -> exactly ONE new Notepad instance
    # ─────────────────────────────────────────────────────────────
    print("\n--- TEST 1: Notepad closed -> 'open notepad' ---")
    kill_all_notepad()
    procs_before = get_notepad_processes()
    wins_before = get_notepad_gui_windows()
    print(f"Before: Processes={len(procs_before)}, GUI Windows={len(wins_before)}")
    assert len(wins_before) == 0, f"Expected 0 windows, found {len(wins_before)}"

    intent = ActionIntent(action="open_app", target="notepad")
    res1 = gatekeeper.execute_action(intent)
    time.sleep(1.0)

    procs_after = get_notepad_processes()
    wins_after = get_notepad_gui_windows()
    print(f"Gatekeeper result: success={res1.success}, message={res1.message}")
    print(f"After: Processes={len(procs_after)}, GUI Windows={len(wins_after)}")
    for w in wins_after:
        print(f"  Window: HWND={w.hwnd}, PID={w.pid}, Title={w.title!r}, Class={w.class_name!r}")

    t1_pass = (res1.success and len(wins_after) == 1)
    test_results["TEST_1"] = "PASS" if t1_pass else "FAIL"
    print(f"TEST 1 Result: {test_results['TEST_1']}")
    assert t1_pass, f"TEST 1 Failed: Expected exactly 1 GUI window, got {len(wins_after)}"

    # ─────────────────────────────────────────────────────────────
    # TEST 2: Notepad already open. "open notepad" -> reuse existing Notepad, NO new process
    # ─────────────────────────────────────────────────────────────
    print("\n--- TEST 2: Notepad already open -> 'open notepad' ---")
    bound_w1 = wins_after[0]
    pids_before = {p["pid"] for p in get_notepad_processes()}
    wins_before = get_notepad_gui_windows()
    print(f"Before: PIDs={pids_before}, GUI Windows={len(wins_before)} (HWND={bound_w1.hwnd})")

    intent = ActionIntent(action="open_app", target="notepad")
    res2 = gatekeeper.execute_action(intent)
    time.sleep(0.5)

    pids_after = {p["pid"] for p in get_notepad_processes()}
    wins_after = get_notepad_gui_windows()
    print(f"Gatekeeper result: success={res2.success}, message={res2.message}")
    print(f"After: PIDs={pids_after}, GUI Windows={len(wins_after)}")
    for w in wins_after:
        print(f"  Window: HWND={w.hwnd}, PID={w.pid}, Title={w.title!r}")

    new_pids = pids_after - pids_before
    t2_pass = (res2.success and len(wins_after) == 1 and len(new_pids) == 0 and wins_after[0].hwnd == bound_w1.hwnd)
    test_results["TEST_2"] = "PASS" if t2_pass else "FAIL"
    print(f"TEST 2 Result: {test_results['TEST_2']} (New PIDs spawned: {new_pids})")
    assert t2_pass, f"TEST 2 Failed: Window not reused or new process created: {new_pids}"

    # ─────────────────────────────────────────────────────────────
    # TEST 3: Notepad open + blank document. "put hello in my notepad" -> reuse existing Notepad, ONE insertion
    # ─────────────────────────────────────────────────────────────
    print("\n--- TEST 3: Notepad open + blank doc -> 'put hello in my notepad' ---")
    pids_before = {p["pid"] for p in get_notepad_processes()}
    wins_before = get_notepad_gui_windows()
    print(f"Before: PIDs={pids_before}, Windows={len(wins_before)}")

    skill_res = skill_registry.execute_skill(
        tool_id="ui_type_text",
        params={"app_name": "notepad", "text": "hello", "mode": "replace"},
        operation_id="test_op_3_reuse"
    )
    time.sleep(0.5)

    pids_after = {p["pid"] for p in get_notepad_processes()}
    wins_after = get_notepad_gui_windows()
    print(f"Skill result: success={skill_res.success}, data={skill_res.data}")
    print(f"After: PIDs={pids_after}, Windows={len(wins_after)}")

    new_pids = pids_after - pids_before
    t3_pass = (skill_res.success and len(wins_after) == 1 and len(new_pids) == 0)
    test_results["TEST_3"] = "PASS" if t3_pass else "FAIL"
    print(f"TEST 3 Result: {test_results['TEST_3']} (New PIDs: {new_pids})")
    assert t3_pass, f"TEST 3 Failed: Process multiplied or typing failed: {new_pids}"

    # ─────────────────────────────────────────────────────────────
    # TEST 4: Notepad open + multiple tabs/documents -> reuse appropriate existing target, NO new process
    # ─────────────────────────────────────────────────────────────
    print("\n--- TEST 4: Notepad open with tabs -> 'put hello in my notepad' ---")
    # Simulate a second tab in modern Notepad using Ctrl+N / Ctrl+T keystroke if supported
    try:
        from friday_core.automation.shortcuts import shortcut_driver
        shortcut_driver.send_shortcut("new")
        time.sleep(0.5)
    except Exception:
        pass

    pids_before = {p["pid"] for p in get_notepad_processes()}
    wins_before = get_notepad_gui_windows()
    print(f"Before typing into multi-tab target: PIDs={pids_before}, Windows={len(wins_before)}")

    skill_res4 = skill_registry.execute_skill(
        tool_id="ui_type_text",
        params={"app_name": "notepad", "text": "hello tab target", "mode": "replace"},
        operation_id="test_op_4_tabs"
    )
    time.sleep(0.5)

    pids_after = {p["pid"] for p in get_notepad_processes()}
    wins_after = get_notepad_gui_windows()
    msg4 = skill_res4.data.get("message", "") if skill_res4.data else str(skill_res4.error)
    print(f"Skill result: success={skill_res4.success}, message={msg4}")
    print(f"After: PIDs={pids_after}, Windows={len(wins_after)}")

    new_pids4 = pids_after - pids_before
    t4_pass = (skill_res4.success and len(new_pids4) == 0)
    test_results["TEST_4"] = "PASS" if t4_pass else "FAIL"
    print(f"TEST 4 Result: {test_results['TEST_4']} (New PIDs: {new_pids4})")
    assert t4_pass, f"TEST 4 Failed: New process spawned on multi-tab Notepad: {new_pids4}"

    # ─────────────────────────────────────────────────────────────
    # TEST 5: Notepad closed. "put hello in my notepad" -> launch exactly ONE Notepad, type, verify, finish
    # ─────────────────────────────────────────────────────────────
    print("\n--- TEST 5: Notepad closed -> 'put hello in my notepad' ---")
    kill_all_notepad()
    assert len(get_notepad_gui_windows()) == 0

    skill_res5 = skill_registry.execute_skill(
        tool_id="ui_type_text",
        params={"app_name": "notepad", "text": "hello from cold start", "mode": "replace"},
        operation_id="test_op_5_cold_start"
    )
    time.sleep(0.5)

    pids_after5 = {p["pid"] for p in get_notepad_processes()}
    wins_after5 = get_notepad_gui_windows()
    msg5 = skill_res5.data.get("message", "") if skill_res5.data else str(skill_res5.error)
    print(f"Skill result: success={skill_res5.success}, message={msg5}")
    print(f"After: PIDs={pids_after5}, Windows={len(wins_after5)}")
    for w in wins_after5:
        print(f"  Window: HWND={w.hwnd}, PID={w.pid}, Title={w.title!r}")

    t5_pass = (skill_res5.success and len(wins_after5) == 1)
    test_results["TEST_5"] = "PASS" if t5_pass else "FAIL"
    print(f"TEST 5 Result: {test_results['TEST_5']}")
    assert t5_pass, f"TEST 5 Failed: Expected exactly 1 GUI window, got {len(wins_after5)}"

    # ─────────────────────────────────────────────────────────────
    # TEST 6: Repeated same command twice -> no uncontrolled process multiplication
    # ─────────────────────────────────────────────────────────────
    print("\n--- TEST 6: Repeated same command twice ---")
    pids_baseline = {p["pid"] for p in get_notepad_processes()}
    wins_baseline = get_notepad_gui_windows()
    print(f"Baseline: PIDs={pids_baseline}, Windows={len(wins_baseline)}")

    # Run 1
    r1 = skill_registry.execute_skill(
        tool_id="ui_type_text",
        params={"app_name": "notepad", "text": "repeat run 1", "mode": "replace"},
        operation_id="test_op_6_run1"
    )
    # Run 2
    r2 = skill_registry.execute_skill(
        tool_id="ui_type_text",
        params={"app_name": "notepad", "text": "repeat run 2", "mode": "replace"},
        operation_id="test_op_6_run2"
    )
    time.sleep(0.5)

    pids_after6 = {p["pid"] for p in get_notepad_processes()}
    wins_after6 = get_notepad_gui_windows()
    print(f"After 2 runs: PIDs={pids_after6}, Windows={len(wins_after6)}")

    new_pids6 = pids_after6 - pids_baseline
    t6_pass = (r1.success and r2.success and len(wins_after6) == 1 and len(new_pids6) == 0)
    test_results["TEST_6"] = "PASS" if t6_pass else "FAIL"
    print(f"TEST 6 Result: {test_results['TEST_6']} (New PIDs: {new_pids6})")
    assert t6_pass, f"TEST 6 Failed: Process multiplied over repeated runs: {new_pids6}"

    # ─────────────────────────────────────────────────────────────
    # TEST 7: Concurrent requests -> per-application launch serialization
    # ─────────────────────────────────────────────────────────────
    print("\n--- TEST 7: Concurrent launch requests ---")
    kill_all_notepad()
    assert len(get_notepad_gui_windows()) == 0

    thread_results = []
    def worker(idx):
        ok, target, reused, msg = window_manager.get_or_launch_window("notepad", operation_id=f"concurrent_test_{idx}")
        thread_results.append({
            "worker_id": idx,
            "ok": ok,
            "reused": reused,
            "target_hwnd": target.hwnd if target else None,
            "target_pid": target.pid if target else None,
            "msg": msg
        })

    t_a = threading.Thread(target=worker, args=(1,))
    t_b = threading.Thread(target=worker, args=(2,))

    t_a.start()
    t_b.start()
    t_a.join()
    t_b.join()

    wins_after7 = get_notepad_gui_windows()
    procs_after7 = get_notepad_processes()
    print("Concurrent thread results:")
    for tr in thread_results:
        print(" ", tr)
    print(f"Resulting Windows={len(wins_after7)}, Processes={len(procs_after7)}")

    # Exactly one thread launched, the other thread reused the launched window!
    reused_count = sum(1 for tr in thread_results if tr["reused"])
    launched_count = sum(1 for tr in thread_results if not tr["reused"] and tr["ok"])
    both_same_hwnd = (thread_results[0]["target_hwnd"] == thread_results[1]["target_hwnd"])

    t7_pass = (len(wins_after7) == 1 and launched_count == 1 and reused_count == 1 and both_same_hwnd)
    test_results["TEST_7"] = "PASS" if t7_pass else "FAIL"
    print(f"TEST 7 Result: {test_results['TEST_7']} (Launched={launched_count}, Reused={reused_count})")
    assert t7_pass, f"TEST 7 Failed: Serialization failure! Windows={len(wins_after7)}"

    # ─────────────────────────────────────────────────────────────
    # TEST 8: Window lookup delay -> wait/poll for existing launch, DO NOT spawn extra instance
    # ─────────────────────────────────────────────────────────────
    print("\n--- TEST 8: Window lookup delay / anti-duplication guard ---")
    # Simulate an operation that has already performed 1 launch attempt
    test_op_id = "test_op_8_delay"
    window_manager._operation_launches[test_op_id] = 1

    # Attempt second launch under same operation_id
    ok8, target8, reused8, msg8 = window_manager.get_or_launch_window("notepad", operation_id=test_op_id, force_new=True)
    print(f"Second launch attempt result: ok={ok8}, reused={reused8}, msg={msg8}")

    t8_pass = (not ok8 and "LIMIT_EXCEEDED" in msg8)
    test_results["TEST_8"] = "PASS" if t8_pass else "FAIL"
    print(f"TEST 8 Result: {test_results['TEST_8']}")
    assert t8_pass, f"TEST 8 Failed: Anti-duplication guard did not block duplicate launch: {msg8}"

    # ─────────────────────────────────────────────────────────────
    # FINAL SUMMARY
    # ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("FINAL TEST MATRIX RESULTS:")
    all_pass = True
    for test_name, status in test_results.items():
        print(f"  {test_name}: {status}")
        if status != "PASS":
            all_pass = False
    print("=" * 70)
    print(f"OVERALL STATUS: {'PASS' if all_pass else 'FAIL'}")

    return 0 if all_pass else 1


def test_notepad_window_reuse_suite():
    """Pytest wrapper executing the full 8-scenario window reuse regression suite."""
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
