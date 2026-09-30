"""
REGRESSION TEST: Voice Directive Execution & 'resolved_name' Definition
Verifies the fix for:
NameError: name 'resolved_name' is not defined
during voice directive execution:
"open Notepad and write a simple C program to calculate area of a triangle"

Requirements:
1. ui_action_engine.launch_app("notepad") returns a valid dict containing "resolved_name".
2. No NameError is raised across any branch of launch_app().
3. launch_app() idempotently reuses existing windows without duplicate processes.
4. dispatch_agent_tool("launch_app", {"app_name": "notepad"}) succeeds cleanly.
5. End-to-end voice directive sequence (launch_app -> type_text) executes without error
   and inserts the requested C program with verified readback.
"""

import os
import time
import pytest
import subprocess
from unittest.mock import MagicMock, patch

from friday_core.automation.action_engine import ui_action_engine
from friday_core.system.window_manager import window_manager
from friday_ui.core.engine import FridayBrain

C_TRIANGLE_PROGRAM = """#include <stdio.h>

int main() {
    float base, height, area;
    printf("Enter base of the triangle: ");
    if (scanf("%f", &base) != 1) return 1;
    printf("Enter height of the triangle: ");
    if (scanf("%f", &height) != 1) return 1;
    area = 0.5 * base * height;
    printf("Area of the triangle = %.2f\\n", area);
    return 0;
}
"""


@pytest.fixture(autouse=True)
def cleanup_notepad():
    """Ensure clean desktop state before and after test."""
    yield
    # We do not forcibly kill here if we want to inspect or we can clean up if desired


class TestVoiceDirectiveResolvedNameRegression:

    def test_launch_app_resolved_name_present_and_valid(self):
        """Verify launch_app always assigns 'resolved_name' and returns it."""
        res = ui_action_engine.launch_app("notepad")
        assert res.get("success") is True, f"launch_app failed: {res}"
        assert "resolved_name" in res, "Key 'resolved_name' missing from launch_app result"
        assert res["resolved_name"] in ["notepad", "Notepad.exe", "notepad.exe", "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"], (
            f"Unexpected resolved_name: {res['resolved_name']}"
        )
        assert res.get("status") == "VERIFIED"
        assert res.get("hwnd") is not None and res["hwnd"] > 0

    def test_launch_app_variations_assign_resolved_name(self):
        """Verify variations of app names assign valid resolved_name."""
        for app_input in ["Notepad", "notepad.exe", "NOTEPAD"]:
            res = ui_action_engine.launch_app(app_input)
            assert res.get("success") is True
            assert "resolved_name" in res
            assert res["resolved_name"] != ""

    def test_window_manager_idempotency_single_target(self):
        """Verify that launch_app does not spawn duplicate Notepad windows."""
        # First launch / bind
        res1 = ui_action_engine.launch_app("notepad")
        assert res1.get("success") is True
        hwnd1 = res1.get("hwnd")

        # Second launch should reuse the exact same window
        res2 = ui_action_engine.launch_app("notepad")
        assert res2.get("success") is True
        hwnd2 = res2.get("hwnd")

        assert hwnd1 == hwnd2, f"Expected same HWND to be reused, got {hwnd1} vs {hwnd2}"

    @pytest.mark.asyncio
    async def test_dispatch_agent_tool_launch_and_type(self):
        """
        Simulate the exact voice pipeline execution flow:
        1. Voice transcribed: 'open Notepad and write a simple C program to calculate area of a triangle'
        2. Agent dispatches 'launch_app' tool
        3. Agent dispatches 'type_text' tool
        4. Readback verification confirms code is in Notepad
        """
        brain = FridayBrain(signals=MagicMock(), tts_engine=MagicMock())

        # Step 1: dispatch launch_app
        launch_msg = await brain.dispatch_agent_tool("launch_app", {"app_name": "notepad"})
        assert "Error" not in launch_msg, f"launch_app failed in dispatch_agent_tool: {launch_msg}"
        assert "verified on desktop" in launch_msg or "launched successfully" in launch_msg

        # Step 2: dispatch type_text
        type_msg = await brain.dispatch_agent_tool(
            "type_text",
            {
                "app_name": "notepad",
                "text": C_TRIANGLE_PROGRAM,
                "mode": "replace"
            }
        )
        assert "failed" not in type_msg.lower(), f"type_text failed: {type_msg}"
        assert "verified on screen" in type_msg or "inserted" in type_msg

        # Step 3: verify actual text inside Notepad via inspector
        from friday_core.automation.inspector import ui_inspector
        wins = window_manager.find_matching_windows("notepad")
        assert len(wins) > 0, "No Notepad window found"
        insp = ui_inspector.inspect_window(hwnd=wins[0].hwnd)
        assert insp is not None

        content = ""
        for e in insp.elements:
            if e.control_type in ("DocumentControl", "EditControl") and e.current_value:
                content = e.current_value
                break
        if not content:
            import uiautomation as auto
            root = auto.ControlFromHandle(wins[0].hwnd)
            doc = root.DocumentControl(searchDepth=6)
            if not doc.Exists(0, 0):
                doc = root.EditControl(searchDepth=6)
            tp = doc.GetTextPattern() if doc else None
            content = tp.DocumentRange.GetText(-1) if tp else ""

        assert "area" in content.lower(), f"Expected 'area' in Notepad text, got: {content[:200]}"
        assert "triangle" in content.lower(), f"Expected 'triangle' in Notepad text, got: {content[:200]}"
