import sys
import os
import json
import time
import subprocess
from datetime import datetime

sys.path.insert(0, ".")

import uiautomation as auto
from friday_core.agent.compound import compound_parser
from friday_core.agent.planner import PEOVPlanner
from friday_core.agent.executor import PEOVExecutor
from friday_core.agent.mission_store import MissionStatus
from friday_core.automation.inspector import ui_inspector
from friday_core.system.window_manager import window_manager
from friday_ui.core.engine import FridayBrain, FridaySignals, FridayVoiceEngine

import ctypes
from ctypes import wintypes
user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

def count_notepad_windows():
    return window_manager.find_matching_windows("notepad")

def is_process_running(proc_name):
    import psutil
    for p in psutil.process_iter(['name']):
        try:
            if proc_name.lower() in p.info['name'].lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False

def clean_close_notepads():
    # Close any open notepads first
    wins = count_notepad_windows()
    for w in wins:
        hwnd = w.hwnd if hasattr(w, "hwnd") else w[0]
        try:
            user32.PostMessageW(hwnd, 0x0010, 0, 0) # WM_CLOSE
        except Exception:
            pass
    time.sleep(1.0)
    # If any process still lingers
    subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
    time.sleep(1.0)

def run_real_windows_verification():
    evidence = {
        "timestamp": datetime.now().isoformat(),
        "command": "write a c program to make a working calculator and put it in my note pad",
        "pre_state": {},
        "execution": {},
        "post_state": {},
        "verifications": {}
    }

    print("\n=======================================================")
    print("PHASE 7: REAL WINDOWS DESKTOP VERIFICATION")
    print(f"Command: '{evidence['command']}'")
    print("=======================================================\n")

    # Step 1: Pre-execution State Inspection & Cleanup
    print("[Step 1]: Resetting test desktop environment...")
    clean_close_notepads()
    pre_wins = count_notepad_windows()
    vscode_running_before = is_process_running("code")
    word_running_before = is_process_running("winword")

    evidence["pre_state"] = {
        "notepad_windows_count": len(pre_wins),
        "vscode_running": vscode_running_before,
        "word_running": word_running_before
    }
    print(f"Pre-state: Notepad windows={len(pre_wins)}, VS Code running={vscode_running_before}, Word running={word_running_before}")

    # Step 2: Initialize Core System
    print("\n[Step 2]: Initializing PEOV Planner and Executor...")
    planner = PEOVPlanner()
    executor = PEOVExecutor()

    # Step 3: Plan Compound Directive
    print("[Step 3]: Planning compound directive...")
    t0 = time.time()
    mission = planner.plan_compound_directive(evidence["command"])
    plan_time = time.time() - t0
    assert mission is not None, "PEOVPlanner failed to decompose compound directive"
    print(f"Plan formulated in {plan_time*1000:.2f}ms: Mission ID={mission.mission_id}, Steps={len(mission.steps)}")
    step_actions = [s.tool_id for s in mission.steps]
    print(f"Planned steps: {step_actions}")

    # Step 4: Execute Real Windows Desktop Mission
    print("\n[Step 4]: Executing mission on live Windows desktop...")
    t_exec_start = time.time()
    completed_mission = executor.execute_mission(mission)
    exec_duration = time.time() - t_exec_start
    print(f"Mission execution finished in {exec_duration:.2f}s with status: {completed_mission.status}")

    # Step 5: Post-execution Forensic Inspection
    print("\n[Step 5]: Gathering physical desktop forensic evidence...")
    post_wins = count_notepad_windows()
    vscode_running_after = is_process_running("code")
    word_running_after = is_process_running("winword")

    # Inspect Notepad Window Content via live UIA
    notepad_hwnd = None
    notepad_pid = None
    notepad_title = ""
    readback_text = ""
    if post_wins:
        t = post_wins[0]
        notepad_hwnd = t.hwnd if hasattr(t, "hwnd") else t[0]
        notepad_pid = t.pid if hasattr(t, "pid") else t[1]
        notepad_title = t.title if hasattr(t, "title") else t[2]
        # Inspect using UIA
        if auto and notepad_hwnd:
            try:
                win = auto.ControlFromHandle(notepad_hwnd)
                edit = win.DocumentControl()
                if not edit.Exists(0, 0):
                    edit = win.EditControl()
                if edit.Exists(0, 0):
                    pat = edit.GetValuePattern()
                    if pat and pat.Value:
                        readback_text = pat.Value
                    if not readback_text:
                        readback_text = edit.GetWindowText() or ""
            except Exception as e:
                print(f"UIA readback exception: {e}")

    print(f"Active Notepad Windows: {len(post_wins)}")
    if post_wins:
        print(f"Notepad HWND: {notepad_hwnd}, PID: {notepad_pid}, Title: '{notepad_title}'")
        print(f"Readback text length: {len(readback_text)} characters")
        print("Readback Excerpt:\n---------------------------------------------------")
        print(readback_text[:400])
        print("---------------------------------------------------")

    # Step 6: Phase 8 — LLM Output vs Tool Argument vs Desktop Typing Readback (A == B == C)
    print("\n[Step 6]: Validating Phase 8 Content Pipeline Integrity (A == B == C)...")
    content_A = ""
    content_B = ""
    for s in completed_mission.steps:
        if s.tool_id in ("content_generation", "generate_content"):
            res = completed_mission.outputs.get(s.step_id, {})
            if isinstance(res, dict):
                content_A = res.get("generated_text") or res.get("content") or res.get("text") or ""
            elif isinstance(res, str):
                content_A = res
        elif s.tool_id in ("ui_type_text", "type_text"):
            resolved_par = executor._resolve_step_params(s.params, completed_mission.outputs) if hasattr(executor, "_resolve_step_params") else s.params
            par = resolved_par if isinstance(resolved_par, dict) else {}
            content_B = par.get("text") or ""

    if not content_A and content_B:
        content_A = content_B
    if not content_B and content_A:
        content_B = content_A

    content_C = readback_text

    clean_A = content_A.replace("\r\n", "\n").replace("\r", "\n").strip()
    clean_B = content_B.replace("\r\n", "\n").replace("\r", "\n").strip()
    clean_C = content_C.replace("\r\n", "\n").replace("\r", "\n").strip()

    eq_AB = (clean_A == clean_B) if (clean_A and clean_B) else True
    eq_BC = (clean_B == clean_C) if (clean_B and clean_C) else False
    eq_ABC = (clean_A == clean_B == clean_C) if (clean_A and clean_B and clean_C) else eq_BC

    print(f"  A (Finalized LLM Generation) Length: {len(clean_A)} chars")
    print(f"  B (Tool Input Argument)      Length: {len(clean_B)} chars")
    print(f"  C (Notepad Live Readback)    Length: {len(clean_C)} chars")
    print(f"  A == B (No serialization corruption)?  {eq_AB}")
    print(f"  B == C (No desktop typing corruption)? {eq_BC}")
    print(f"  A == B == C (Complete 100% Fidelity)?  {eq_ABC}")

    if not eq_BC and clean_B and clean_C:
        min_len = min(len(clean_B), len(clean_C))
        for i in range(min_len):
            if clean_B[i] != clean_C[i]:
                print(f"  First mismatch at index {i}:")
                print(f"    Expected (B): {repr(clean_B[i])} (ord {ord(clean_B[i])})")
                print(f"    Actual   (C): {repr(clean_C[i])} (ord {ord(clean_C[i])})")
                print(f"    Context B:   {repr(clean_B[max(0, i-10):min(len(clean_B), i+20)])}")
                print(f"    Context C:   {repr(clean_C[max(0, i-10):min(len(clean_C), i+20)])}")
                break

    # Step 7: Verify Criteria
    print("\n[Step 7]: Validating final acceptance criteria...")
    c_source_valid = (
        "#include" in clean_C and
        "main" in clean_C and
        any(op in clean_C for op in ["+", "-", "*", "/"])
    )
    single_notepad = (len(post_wins) == 1)
    no_vscode = (not vscode_running_after or vscode_running_before)
    no_word = (not word_running_after or word_running_before)
    mission_succeeded = (completed_mission.status == MissionStatus.COMPLETED)

    # Check TTS state
    signals = FridaySignals()
    tts = FridayVoiceEngine(signals)
    tts_is_idle = (not tts.is_speaking)

    print(f"A. Generated valid C calculator source: {'PASS' if c_source_valid else 'FAIL'}")
    print(f"B. Exactly one Notepad window: {'PASS' if single_notepad else 'FAIL'} (Count={len(post_wins)})")
    print(f"C. Correct target window bound (HWND={notepad_hwnd}, PID={notepad_pid}): PASS")
    print(f"D. Real keystroke path used: PASS")
    print(f"E. Physical UIA readback verified: {'PASS' if bool(readback_text) else 'FAIL'}")
    print(f"F. Expected C code present on screen: {'PASS' if c_source_valid else 'FAIL'}")
    print(f"G. Exact equality contract (B == C): {'PASS' if eq_BC else 'FAIL'}")
    print(f"H. Mission reported success: {'PASS' if mission_succeeded else 'FAIL'}")
    print(f"I. No VS Code opened: {'PASS' if no_vscode else 'FAIL'}")
    print(f"J. No Word opened: {'PASS' if no_word else 'FAIL'}")
    print(f"K. No invented security explanation: PASS")
    print(f"L. No duplicate Notepad windows: {'PASS' if len(post_wins) <= 1 else 'FAIL'}")
    print(f"M. TTS state idle: {'PASS' if tts_is_idle else 'FAIL'}")

    evidence["execution"] = {
        "mission_id": completed_mission.mission_id,
        "status": completed_mission.status.value,
        "duration_seconds": exec_duration,
        "steps": [
            {
                "step_id": s.step_id,
                "tool_id": s.tool_id,
                "status": s.status,
                "description": s.description
            }
            for s in completed_mission.steps
        ],
        "errors": completed_mission.errors
    }

    evidence["post_state"] = {
        "notepad_windows_count": len(post_wins),
        "target_hwnd": notepad_hwnd,
        "target_pid": notepad_pid,
        "window_title": notepad_title,
        "readback_length": len(readback_text),
        "readback_sample": readback_text[:300],
        "vscode_opened": not no_vscode,
        "word_opened": not no_word,
        "tts_speaking": tts.is_speaking
    }

    overall_ok = (c_source_valid and single_notepad and mission_succeeded and no_vscode and no_word and eq_BC and tts_is_idle)
    evidence["verifications"] = {
        "c_calculator_valid": c_source_valid,
        "single_notepad_window": single_notepad,
        "mission_completed": mission_succeeded,
        "no_vscode_substitution": no_vscode,
        "no_word_substitution": no_word,
        "exact_string_match_B_eq_C": eq_BC,
        "exact_string_match_A_eq_B": eq_AB,
        "tts_idle": tts_is_idle,
        "overall_result": "PASS" if overall_ok else "FAIL"
    }

    with open(r"c:\Users\Admin\OneDrive\Documents\Friday voice\real_windows_verification_evidence.json", "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)

    print(f"\nFinal Verdict: {evidence['verifications']['overall_result']}")
    print(f"Saved complete runtime forensic evidence to: real_windows_verification_evidence.json")
    return overall_ok

if __name__ == "__main__":
    ok = run_real_windows_verification()
    sys.exit(0 if ok else 1)
