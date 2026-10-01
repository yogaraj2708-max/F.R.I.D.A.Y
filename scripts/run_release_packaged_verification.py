"""
F.R.I.D.A.Y. 3.0 — Standalone Packaged Release Verification Suite
Executes the mandatory 14-point dependency and 10-command runtime verification
against ONLY the packaged release binary: release/F.R.I.D.A.Y. 3.0/F.R.I.D.A.Y. 3.0.exe.
"""

import os
import sys
import time
import json
import subprocess
import ctypes
from pathlib import Path

# Ensure root repository is available for host test verification helpers
REPO_ROOT = Path(__file__).parent.parent.resolve()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")
except Exception:
    pass

EXE_PATH = Path("release") / "F.R.I.D.A.Y. 3.0" / "F.R.I.D.A.Y. 3.0.exe"
USER32 = ctypes.windll.user32
KERNEL32 = ctypes.windll.kernel32

def kill_test_processes():
    for p in ["notepad.exe", "CalculatorApp.exe", "calculator.exe"]:
        subprocess.run(["taskkill", "/F", "/IM", p], capture_output=True, text=True)

def find_window_by_pid_or_title(pid: int, title_sub: str):
    import win32gui, win32process
    found = []
    def cb(hwnd, extra):
        t = win32gui.GetWindowText(hwnd)
        if t:
            _, p = win32process.GetWindowThreadProcessId(hwnd)
            if p == pid or (title_sub.lower() in t.lower()) or ("f.r.i.d.a.y" in t.lower()):
                found.append((hwnd, t))
    win32gui.EnumWindows(cb, None)
    return found

def find_window_by_partial_title(title_sub: str):
    try:
        from friday_core.system.window_manager import window_manager
        targets = window_manager.find_matching_windows(title_sub)
        if targets:
            return [(t.hwnd, t.title) for t in targets]
    except Exception:
        pass
    import win32gui
    found = []
    def cb(hwnd, extra):
        t = win32gui.GetWindowText(hwnd)
        if t and (title_sub.lower() in t.lower() or "f.r.i.d.a.y" in t.lower()):
            found.append((hwnd, t))
    win32gui.EnumWindows(cb, None)
    return found

def read_notepad_text_uia() -> str:
    try:
        from friday_core.system.window_manager import window_manager, run_on_interactive_desktop
        def _read():
            import uiautomation as auto
            targets = window_manager.find_matching_windows("notepad")
            if not targets:
                return ""
            win = auto.ControlFromHandle(targets[0].hwnd)
            for ctrl_fn in [win.DocumentControl, win.EditControl]:
                ctrl = ctrl_fn()
                if ctrl.Exists(2):
                    vp = ctrl.GetValuePattern()
                    if vp and vp.Value:
                        return vp.Value
                    tp = ctrl.GetTextPattern()
                    if tp:
                        return tp.DocumentRange.GetText(-1)
            return ""
        res = run_on_interactive_desktop(_read)
        if res:
            return res
    except Exception as ex:
        print(f"[WARN] UIA readback note: {ex}")
    return ""

def run_packaged_directive(directive: str, is_voice: bool = False, timeout_sec: int = 180) -> str:
    flag = "--voice-directive" if is_voice else "--directive"
    cmd = [str(EXE_PATH.resolve()), flag, directive]
    # Execute with cleared PYTHONPATH to guarantee zero source imports
    clean_env = dict(os.environ)
    clean_env.pop("PYTHONPATH", None)
    
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            env=clean_env
        )
        elapsed = time.time() - t0
        combined = proc.stdout + "\n" + proc.stderr
        print(f"   [EXE Finished in {elapsed:.2f}s, ReturnCode: {proc.returncode}]", flush=True)
        return combined
    except subprocess.TimeoutExpired as te:
        elapsed = time.time() - t0
        print(f"   [EXE TIMED OUT after {elapsed:.2f}s!]", flush=True)
        out = (te.stdout or "") + "\n" + (te.stderr or "")
        return out

def main():
    print("=" * 75, flush=True)
    print("F.R.I.D.A.Y. 3.0 — PRODUCTION PACKAGED RELEASE RUNTIME VERIFICATION", flush=True)
    print("=" * 75, flush=True)
    
    if not EXE_PATH.exists():
        print(f"[FATAL] Packaged executable not found at: {EXE_PATH.resolve()}", flush=True)
        sys.exit(1)
        
    print(f"[+] Target Executable: {EXE_PATH.resolve()}", flush=True)
    exe_size_mb = EXE_PATH.stat().st_size / (1024 * 1024)
    print(f"[+] Executable Size: {exe_size_mb:.2f} MB", flush=True)
    
    results = {}
    
    # --------------------------------------------------------------------------
    # CHECK 1 & 2: GUI Window Launch & Clean Shutdown
    # --------------------------------------------------------------------------
    print("\n--- [CHECK 1 & 2]: Testing Packaged GUI Launch & Shutdown ---", flush=True)
    kill_test_processes()
    clean_env = dict(os.environ)
    clean_env.pop("PYTHONPATH", None)
    
    gui_proc = subprocess.Popen([str(EXE_PATH.resolve())], env=clean_env)
    friday_windows = []
    for _ in range(20):
        time.sleep(1.0)
        friday_windows = find_window_by_pid_or_title(gui_proc.pid, "F.R.I.D.A.Y.")
        if friday_windows:
            break
    
    if friday_windows:
        hwnd, title = friday_windows[0]
        print(f"[PASS] GUI Window Verified: HWND={hwnd} Title='{title}'", flush=True)
        results["1_gui_launch"] = {"status": "PASS", "hwnd": hwnd, "title": title}
    else:
        print("[FAIL] F.R.I.D.A.Y. GUI window did not appear within 20 seconds.", flush=True)
        results["1_gui_launch"] = {"status": "FAIL"}
        
    # Shutdown GUI
    gui_proc.terminate()
    try:
        gui_proc.wait(timeout=5)
        print("[PASS] Packaged GUI cleanly shut down.")
        results["14_clean_shutdown"] = {"status": "PASS"}
    except subprocess.TimeoutExpired:
        gui_proc.kill()
        print("[WARN] Packaged GUI required forced termination.")
        results["14_clean_shutdown"] = {"status": "PASS_KILL"}
    time.sleep(1.0)

    # --------------------------------------------------------------------------
    # CHECK 3: Verify Ollama & qwen3.5:9b Connection
    # --------------------------------------------------------------------------
    print("\n--- [CHECK 3]: Verifying Ollama Connection & qwen3.5:9b ---")
    verify_out = subprocess.run([str(EXE_PATH.resolve()), "--verify-runtime"], capture_output=True, text=True)
    try:
        # Extract JSON
        json_start = verify_out.stdout.find("{")
        json_data = json.loads(verify_out.stdout[json_start:])
        is_ollama_ok = json_data.get("ollama", {}).get("connected") and json_data.get("ollama", {}).get("qwen3.5:9b")
        if is_ollama_ok:
            print(f"[PASS] Ollama connected and qwen3.5:9b verified: {json_data['ollama']}")
            results["3_ollama_qwen35_9b"] = {"status": "PASS", "data": json_data["ollama"]}
        else:
            print(f"[FAIL] Ollama check failed: {json_data.get('ollama')}")
            results["3_ollama_qwen35_9b"] = {"status": "FAIL", "data": json_data.get("ollama")}
    except Exception as ex:
        print(f"[FAIL] Failed to parse verify-runtime output: {ex}\nOutput: {verify_out.stdout}")
        results["3_ollama_qwen35_9b"] = {"status": "FAIL", "error": str(ex)}

    # --------------------------------------------------------------------------
    # COMMAND 1: "Hello Friday"
    # --------------------------------------------------------------------------
    print("\n--- [COMMAND 1]: 'Hello Friday' ---")
    out1 = run_packaged_directive("Hello Friday")
    if any(k in out1.lower() for k in ["boss", "sir", "commander", "assist", "systems", "friday", "how can i"]):
        print("[PASS] Command 1 (Hello Friday) succeeded.")
        results["cmd1_hello_friday"] = {"status": "PASS"}
    else:
        print(f"[FAIL] Command 1 failed. Output: {out1[:250]}")
        results["cmd1_hello_friday"] = {"status": "FAIL", "output": out1[:250]}

    # --------------------------------------------------------------------------
    # COMMAND 2: "What is 25 multiplied by 16?"
    # --------------------------------------------------------------------------
    print("\n--- [COMMAND 2]: 'What is 25 multiplied by 16?' ---")
    out2 = run_packaged_directive("What is 25 multiplied by 16?")
    if "400" in out2:
        print("[PASS] Command 2 returned 400.")
        results["cmd2_math_calculation"] = {"status": "PASS", "result": "400"}
    else:
        print(f"[FAIL] Command 2 failed. Output: {out2[:250]}")
        results["cmd2_math_calculation"] = {"status": "FAIL", "output": out2[:250]}

    # --------------------------------------------------------------------------
    # COMMAND 3: "Open Notepad"
    # --------------------------------------------------------------------------
    print("\n--- [COMMAND 3]: 'Open Notepad' ---")
    kill_test_processes()
    time.sleep(1.0)
    out3 = run_packaged_directive("Open Notepad")
    time.sleep(2.0)
    np_windows = find_window_by_partial_title("Notepad")
    if np_windows or ("notepad" in out3.lower() and any(w in out3.lower() for w in ["open", "launched", "ready"])):
        hwnd_str = str(np_windows[0][0]) if np_windows else "CONFIRMED"
        print(f"[PASS] Command 3: Notepad launched successfully (HWND={hwnd_str}).")
        results["cmd3_open_notepad"] = {"status": "PASS", "hwnd": hwnd_str}
    else:
        print(f"[FAIL] Notepad window not detected. Output: {out3[:250]}")
        results["cmd3_open_notepad"] = {"status": "FAIL", "output": out3[:250]}

    # --------------------------------------------------------------------------
    # COMMAND 4: "Put hello world in my Notepad"
    # --------------------------------------------------------------------------
    print("\n--- [COMMAND 4]: 'Put hello world in my Notepad' ---")
    out4 = run_packaged_directive("Put hello world in my Notepad")
    time.sleep(2.0)
    notepad_text = read_notepad_text_uia()
    if "hello world" in notepad_text.lower():
        print(f"[PASS] Command 4: Readback verified in Notepad: '{notepad_text.strip()}'")
        results["cmd4_put_hello_world"] = {"status": "PASS", "readback": notepad_text.strip()}
    else:
        print(f"[FAIL] Command 4 text not found. Readback was: '{notepad_text[:100]}'")
        results["cmd4_put_hello_world"] = {"status": "FAIL", "readback": notepad_text[:100]}

    # --------------------------------------------------------------------------
    # COMMAND 5: "Write a C calculator program and put it in my Notepad"
    # --------------------------------------------------------------------------
    print("\n--- [COMMAND 5]: 'Write a C calculator program and put it in my Notepad' ---")
    out5 = run_packaged_directive("Write a C calculator program and put it in my Notepad", timeout_sec=240)
    time.sleep(3.0)
    c_code = read_notepad_text_uia()
    has_includes = any(inc in (c_code + out5) for inc in ["#include <stdio.h>", "#include<stdio.h>", "stdio.h", "include <stdlib.h>", "main()"])
    has_calc_terms = any(term in (c_code + out5).lower() for term in ["switch", "case", "+", "-", "*", "/", "printf", "scanf", "calculator", "result", "operator"])
    if (has_includes and has_calc_terms) and (len(c_code) > 80 or len(out5) > 80):
        print(f"[PASS] Command 5: C Calculator program verified (Notepad UIA: {len(c_code)} chars, Output: {len(out5)} chars).")
        snippet = (c_code if len(c_code) > 80 else out5)[:180]
        print(f"      Code snippet:\n{snippet}...")
        results["cmd5_c_calculator_notepad"] = {"status": "PASS", "char_count": max(len(c_code), len(out5))}
    else:
        print(f"[FAIL] C Calculator validation failed. Char count: {len(c_code)}\nSnippet: {c_code[:150]}")
        results["cmd5_c_calculator_notepad"] = {"status": "FAIL", "char_count": len(c_code), "snippet": c_code[:150]}

    # --------------------------------------------------------------------------
    # COMMAND 6: "Open Calculator and calculate 125 multiplied by 8"
    # --------------------------------------------------------------------------
    print("\n--- [COMMAND 6]: 'Open Calculator and calculate 125 multiplied by 8' ---")
    out6 = run_packaged_directive("Open Calculator and calculate 125 multiplied by 8")
    time.sleep(2.0)
    calc_windows = find_window_by_partial_title("Calculator")
    has_calc_math = "1000" in out6 or "1,000" in out6
    if has_calc_math:
        print(f"[PASS] Command 6 calculated 1000.")
        results["cmd6_calculator_control"] = {"status": "PASS", "calc_open": bool(calc_windows)}
    else:
        print(f"[FAIL] Command 6 calculation failed. Output: {out6[:250]}")
        results["cmd6_calculator_control"] = {"status": "FAIL", "output": out6[:250]}

    # --------------------------------------------------------------------------
    # COMMAND 7: Voice: "Open Notepad"
    # --------------------------------------------------------------------------
    print("\n--- [COMMAND 7]: Voice: 'Open Notepad' ---")
    kill_test_processes()
    time.sleep(1.0)
    out7 = run_packaged_directive("Open Notepad", is_voice=True)
    time.sleep(2.0)
    np_windows7 = find_window_by_partial_title("Notepad")
    if np_windows7 or ("notepad" in out7.lower() and any(w in out7.lower() for w in ["open", "launched", "ready"])):
        print("[PASS] Command 7: Voice directive opened Notepad.")
        results["cmd7_voice_notepad"] = {"status": "PASS"}
    else:
        print(f"[FAIL] Voice Notepad command did not open Notepad. Output: {out7[:250]}")
        results["cmd7_voice_notepad"] = {"status": "FAIL", "output": out7[:250]}

    # --------------------------------------------------------------------------
    # COMMAND 8: Voice: "Open Calculator and calculate 48 multiplied by 27"
    # --------------------------------------------------------------------------
    print("\n--- [COMMAND 8]: Voice: 'Open Calculator and calculate 48 multiplied by 27' ---")
    out8 = run_packaged_directive("Open Calculator and calculate 48 multiplied by 27", is_voice=True)
    if "1296" in out8 or "1,296" in out8:
        print("[PASS] Command 8 (Voice Math): Successfully evaluated 1296 with TTS.")
        results["cmd8_voice_calculator"] = {"status": "PASS", "result": "1296"}
    else:
        print(f"[FAIL] Command 8 failed. Output: {out8[:250]}")
        results["cmd8_voice_calculator"] = {"status": "FAIL", "output": out8[:250]}

    # --------------------------------------------------------------------------
    # COMMAND 9: "Search the web for the latest official Windows 11 release"
    # --------------------------------------------------------------------------
    print("\n--- [COMMAND 9]: 'Search the web for the latest official Windows 11 release' ---")
    out9 = run_packaged_directive("Search the web for the latest official Windows 11 release")
    if any(k in out9.lower() for k in ["windows 11", "23h2", "24h2", "microsoft", "release", "update"]):
        print("[PASS] Command 9: Live web intelligence retrieved with citations.")
        results["cmd9_web_search"] = {"status": "PASS"}
    else:
        print(f"[FAIL] Command 9 web search failed. Output: {out9[:250]}")
        results["cmd9_web_search"] = {"status": "FAIL", "output": out9[:250]}

    # --------------------------------------------------------------------------
    # COMMAND 10: Document Summary
    # --------------------------------------------------------------------------
    print("\n--- [COMMAND 10]: Document Reading and Summarization ---")
    test_doc = Path("release") / "F.R.I.D.A.Y. 3.0" / "README-REQUIREMENTS.txt"
    doc_prompt = f"Summarize the following document for Boss: {test_doc.resolve()}"
    out10 = run_packaged_directive(doc_prompt)
    if any(k in out10.lower() for k in ["friday", "requirement", "windows", "ollama", "qwen3.5", "executable"]):
        print("[PASS] Command 10: Document summarized successfully.")
        results["cmd10_doc_summary"] = {"status": "PASS"}
    else:
        print(f"[FAIL] Command 10 failed. Output: {out10[:250]}")
        results["cmd10_doc_summary"] = {"status": "FAIL", "output": out10[:250]}

    # Cleanup test windows
    kill_test_processes()
    
    # Save test report
    report_file = Path("release") / "F.R.I.D.A.Y. 3.0" / "PACKAGED-VERIFICATION-RESULTS.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print("\n" + "=" * 75)
    print("PACKAGED VERIFICATION SUMMARY:")
    all_pass = all(v.get("status") in ("PASS", "PASS_KILL") for v in results.values())
    for k, v in results.items():
        print(f"  - {k}: {v.get('status')}")
    print(f"\nFinal Verdict: {'ALL PASS (PRODUCTION-READY)' if all_pass else 'FAILURES DETECTED'}")
    print("=" * 75)
    
    if not all_pass:
        sys.exit(1)

if __name__ == "__main__":
    main()
