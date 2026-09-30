"""
F.R.I.D.A.Y. 3.0 — Comprehensive Desktop Automation Integrity Regression Suite
Covers the 8 mandatory desktop automation integrity scenarios:

- Test 1: Single window launch (1 Notepad instance/tab created).
- Test 2: Window reuse (subsequent calls target existing window without new launch).
- Test 3: Minimized window reuse (restores and reuses minimized Notepad).
- Test 4: Real multiline typing with special characters ({}[]()<>"'\\|&%^$@#;:).
- Test 5: Exact equality readback verification (EXPECTED == ACTUAL).
- Test 6: Authoritative application selection (Notepad requested -> Word/VS Code rejected).
- Test 7: Idempotent operation deduplication (duplicate calls in same task return cached result without duplicate typing/launching).
- Test 8: Failure injection & honest reporting (closed window/invalid target reported cleanly without fake success).
"""

import os
import sys
import time
import glob
import ctypes
from ctypes import wintypes
import subprocess
import pytest
from typing import List, Dict, Any

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import psutil
from friday_core.platform_guard import IS_WINDOWS
from friday_core.system.window_manager import window_manager, WindowTarget
from friday_core.automation.action_engine import ui_action_engine
from friday_core.automation.inspector import ui_inspector
from friday_core.skills.agent_bridge import agent_tool_bridge
from friday_core.skills.builtins.ui_automation import INSERTION_MODE_REAL_KEYSTROKE

user32 = ctypes.windll.user32 if IS_WINDOWS else None


def kill_all_notepad():
    """Helper to ensure clean slate before/after tests."""
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
        time.sleep(0.5)
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
    """Returns all active Notepad processes with PID and name."""
    procs = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if "notepad" in p.info["name"].lower():
                procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return procs


def get_notepad_gui_windows() -> List[WindowTarget]:
    """Returns all visible/iconic top-level Notepad GUI windows."""
    return window_manager.find_matching_windows("notepad")


@pytest.fixture(scope="module", autouse=True)
def setup_teardown_suite():
    """Module-level setup and teardown ensuring Notepad slate is clean."""
    if not IS_WINDOWS:
        pytest.skip("Desktop automation integrity tests require Windows runtime.")
    kill_all_notepad()
    yield
    kill_all_notepad()


class TestDesktopAutomationIntegrity:

    def test_01_single_window_launch(self):
        """Test 1: Notepad closed. Launch creates exactly ONE instance and window."""
        kill_all_notepad()
        assert len(get_notepad_gui_windows()) == 0, "Notepad should be closed at start"

        tid = "test_integrity_t1_single_launch"
        res = ui_action_engine.launch_app("notepad", task_id=tid)

        assert res.get("success") is True, f"launch_app failed: {res}"
        assert res.get("hwnd") is not None
        assert res.get("pid") is not None

        time.sleep(0.5)
        wins = get_notepad_gui_windows()
        assert len(wins) == 1, f"Expected exactly 1 Notepad window, found {len(wins)}"
        assert wins[0].hwnd == res["hwnd"]

    def test_02_window_reuse(self):
        """Test 2: Notepad already open. Subsequent launch targets existing window without new process."""
        wins_before = get_notepad_gui_windows()
        assert len(wins_before) == 1, "Expected existing Notepad window from test 1"
        bound_hwnd = wins_before[0].hwnd
        pids_before = {p["pid"] for p in get_notepad_processes()}

        tid = "test_integrity_t2_reuse"
        res = ui_action_engine.launch_app("notepad", task_id=tid)

        assert res.get("success") is True
        assert res.get("hwnd") == bound_hwnd

        wins_after = get_notepad_gui_windows()
        pids_after = {p["pid"] for p in get_notepad_processes()}

        assert len(wins_after) == 1, f"Expected exactly 1 window after reuse, found {len(wins_after)}"
        assert wins_after[0].hwnd == bound_hwnd
        new_pids = pids_after - pids_before
        assert len(new_pids) == 0, f"Expected 0 new processes spawned, found: {new_pids}"

    def test_03_minimized_window_reuse(self):
        """Test 3: Minimized window reuse restores and reuses existing Notepad."""
        wins = get_notepad_gui_windows()
        assert len(wins) == 1
        hwnd = wins[0].hwnd

        # Minimize the window (SW_MINIMIZE = 6)
        user32.ShowWindow(hwnd, 6)
        time.sleep(0.3)
        assert user32.IsIconic(hwnd), "Window should be iconic (minimized)"

        tid = "test_integrity_t3_minimized"
        ok, target, reused, msg = window_manager.get_or_launch_window("notepad", operation_id=tid)

        assert ok is True, f"Failed to get_or_launch_window: {msg}"
        assert reused is True, "Window should have been reused, not newly launched"
        assert target.hwnd == hwnd, f"Expected HWND {hwnd}, got {target.hwnd}"

        # Verify window is restored from minimized state
        time.sleep(0.3)
        is_iconic = bool(user32.IsIconic(hwnd))
        assert not is_iconic, "Window should be restored (not minimized)"

        # Verify only 1 window remains
        wins_after = get_notepad_gui_windows()
        assert len(wins_after) == 1, f"Expected 1 window, found {len(wins_after)}"

    def test_04_real_multiline_typing_with_special_characters(self):
        """Test 4: Real multiline typing with special characters ({}[]()<>"'\\|&%^$@#;:)."""
        wins = get_notepad_gui_windows()
        assert len(wins) == 1
        hwnd = wins[0].hwnd

        special_code = (
            "#include <stdio.h>\n"
            "// Special symbols: {}[]()<>'\"\\|&%^$@#;:\n"
            "int main() {\n"
            "    int val[2] = {10, 20};\n"
            "    char *s = \"<demo>\";\n"
            "    if (val[0] < val[1] && (val[1] > 0)) {\n"
            "        printf(\"%s: $#@%^\\n\", s);\n"
            "    }\n"
            "    return 0;\n"
            "}"
        )

        tid = "test_integrity_t4_typing"
        res = ui_action_engine.type_text(
            text=special_code,
            app_name="notepad",
            mode="replace",
            task_id=tid
        )

        assert res.get("success") is True, f"type_text failed: {res}"
        assert res.get("status") == "VERIFIED"
        assert res.get("method") == INSERTION_MODE_REAL_KEYSTROKE, f"Expected {INSERTION_MODE_REAL_KEYSTROKE}, got {res.get('method')}"

        # Verify no extra windows spawned during typing
        wins_after = get_notepad_gui_windows()
        assert len(wins_after) == 1, f"Expected 1 window, found {len(wins_after)}"
        assert wins_after[0].hwnd == hwnd

    def test_05_exact_equality_readback_verification(self):
        """Test 5: Exact equality readback verification (EXPECTED == ACTUAL)."""
        wins = get_notepad_gui_windows()
        assert len(wins) == 1
        hwnd = wins[0].hwnd

        expected_text = (
            "#include <stdio.h>\n"
            "int main() {\n"
            "    printf(\"Area = %lf\\n\", 0.5 * 10.0 * 5.0);\n"
            "    return 0;\n"
            "}"
        )

        tid = "test_integrity_t5_readback"
        res = ui_action_engine.type_text(
            text=expected_text,
            app_name="notepad",
            mode="replace",
            task_id=tid
        )

        assert res.get("success") is True, f"type_text failed: {res.get('message')}"
        assert res.get("status") == "VERIFIED"

        # Direct inspection readback
        insp = ui_inspector.inspect_window(hwnd=hwnd, wake_window=False)
        assert insp is not None

        readback_content = ""
        for elem in insp.elements:
            if elem.control_type in ("DocumentControl", "EditControl") and elem.current_value:
                readback_content = elem.current_value
                break

        assert readback_content, "Inspection failed to retrieve current value from editor control"

        clean_expected = expected_text.strip().replace("\r\n", "\n").replace("\r", "\n")
        clean_actual = readback_content.strip().replace("\r\n", "\n").replace("\r", "\n")

        assert clean_actual == clean_expected, f"Readback mismatch!\nExpected:\n{clean_expected}\nActual:\n{clean_actual}"

    def test_06_authoritative_application_selection(self):
        """Test 6: Authoritative application selection (Notepad requested -> Word/VS Code rejected)."""
        user_query = "Open Notepad and write a C program to calculate area of triangle"

        # Attempt 1: Tool call targets Word when user requested Notepad -> MUST BE BLOCKED
        allowed_word, reason_word = agent_tool_bridge.risk_gate(
            tool_name="launch_app",
            arguments={"app_name": "word"},
            user_query=user_query
        )
        assert allowed_word is False, "Targeting Word when user requested Notepad MUST be blocked"
        assert "not requested by user" in reason_word.lower()

        # Attempt 2: Tool call targets VS Code when user requested Notepad -> MUST BE BLOCKED
        allowed_vscode, reason_vscode = agent_tool_bridge.risk_gate(
            tool_name="type_text",
            arguments={"app_name": "vscode", "text": "int main() {}"},
            user_query=user_query
        )
        assert allowed_vscode is False, "Targeting VS Code when user requested Notepad MUST be blocked"
        assert "not requested by user" in reason_vscode.lower()

        # Attempt 3: Tool call targets Notepad when user requested Notepad -> MUST BE ALLOWED
        allowed_notepad, reason_notepad = agent_tool_bridge.risk_gate(
            tool_name="launch_app",
            arguments={"app_name": "notepad"},
            user_query=user_query
        )
        assert allowed_notepad is True, f"Targeting Notepad should be allowed: {reason_notepad}"

    def test_07_idempotent_operation_deduplication(self):
        """Test 7: Idempotent operation deduplication returns cached result without duplicate execution."""
        task_id = "test_integrity_t7_dedup"

        # First launch_app call
        r1 = ui_action_engine.launch_app("notepad", task_id=task_id)
        assert r1.get("success") is True
        hwnd1 = r1["hwnd"]

        # Duplicate launch_app call with same task_id
        r2 = ui_action_engine.launch_app("notepad", task_id=task_id)
        assert r2.get("success") is True
        assert r2 == r1, "Duplicate launch_app call should return identical cached result"

        # First type_text call
        text = "// Idempotent verification token 42\nint x = 42;"
        t1 = ui_action_engine.type_text(text=text, app_name="notepad", mode="replace", task_id=task_id)
        assert t1.get("success") is True

        # Duplicate type_text call with same task_id
        t2 = ui_action_engine.type_text(text=text, app_name="notepad", mode="replace", task_id=task_id)
        assert t2.get("success") is True
        assert t2 == t1, "Duplicate type_text call should return identical cached result without re-typing"

        # Verify only 1 window and process remains
        wins = get_notepad_gui_windows()
        assert len(wins) == 1
        assert wins[0].hwnd == hwnd1

    def test_08_failure_injection_and_honest_reporting(self):
        """Test 8: Failure injection & honest reporting (closed window/invalid target reported cleanly)."""
        invalid_hwnd = 0x7FFFFFFF  # Non-existent HWND

        insp_res = ui_action_engine.inspect_ui(hwnd=invalid_hwnd, task_id="test_integrity_t8_inv_insp")
        assert insp_res.get("success") is False
        assert insp_res.get("status") == "NOT_FOUND"
        msg = insp_res.get("message", "").lower()
        assert "could not find" in msg or "not found" in msg

        # launch_app anti-duplication threshold test
        limit_op_id = "test_integrity_t8_limit"
        window_manager._operation_launches[limit_op_id] = 1

        # Second launch attempt under same operation_id with force_new=True must fail honestly
        ok, target, reused, msg = window_manager.get_or_launch_window(
            "notepad",
            operation_id=limit_op_id,
            force_new=True
        )
        assert ok is False
        assert target is None
        assert "LIMIT_EXCEEDED" in msg
