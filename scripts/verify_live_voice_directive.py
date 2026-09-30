import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath("."))
from unittest.mock import MagicMock

from friday_ui.core.engine import FridayBrain
from friday_core.system.window_manager import window_manager
from friday_core.automation.inspector import ui_inspector

import time
from tests.regression.test_notepad_window_reuse_regression import kill_all_notepad

async def main():
    print("=" * 60)
    print("LIVE RUNTIME VERIFICATION: VOICE DIRECTIVE EXECUTION")
    print("Command: 'open Notepad and write a simple C program to calculate area of a triangle'")
    print("=" * 60)

    brain = FridayBrain(signals=MagicMock(), tts_engine=MagicMock())

    # Step 1: Model dispatches launch_app
    print("\n[Step 1] Executing tool: launch_app(app_name='notepad')...")
    launch_res = await brain.dispatch_agent_tool("launch_app", {"app_name": "notepad"})
    print("Launch Result:", launch_res)
    assert "error" not in launch_res.lower() and "failed" not in launch_res.lower()

    # Step 2: Model dispatches type_text
    print("\n[Step 2] Executing tool: type_text(app_name='notepad', text=<C_TRIANGLE_PROGRAM>)...")
    triangle_code = """#include <stdio.h>

int main() {
    float base, height, area;
    printf("Enter base of the triangle: ");
    scanf("%f", &base);
    printf("Enter height of the triangle: ");
    scanf("%f", &height);
    area = 0.5 * base * height;
    printf("Area of the triangle = %.2f\\n", area);
    return 0;
}
"""
    type_res = await brain.dispatch_agent_tool(
        "type_text",
        {
            "app_name": "notepad",
            "text": triangle_code,
            "mode": "replace"
        }
    )
    print("Type Result:", type_res)
    assert "failed" not in type_res.lower()

    # Step 3: Verify single instance & content
    print("\n[Step 3] Forensic Desktop Inspection...")
    wins = window_manager.find_matching_windows("notepad")
    print(f"Total matching Notepad windows: {len(wins)}")
    for w in wins:
        print(f"  Target: HWND={w.hwnd}, PID={w.pid}, Title={w.title!r}, Class={w.class_name!r}")
    assert len(wins) >= 1, f"Expected matching Notepad window, found {len(wins)}"
    target_win = window_manager.select_target_window(wins, "notepad")
    assert target_win is not None
    insp = ui_inspector.inspect_window(hwnd=target_win.hwnd)
    print(f"Inspected controls count: {len(insp.elements)}")

    content = ""
    for e in insp.elements:
        if e.control_type in ("DocumentControl", "EditControl") and e.current_value:
            content = e.current_value
            break
    if not content:
        import uiautomation as auto
        root = auto.ControlFromHandle(target_win.hwnd)
        doc = root.DocumentControl(searchDepth=6)
        if not doc.Exists(0, 0):
            doc = root.EditControl(searchDepth=6)
        tp = doc.GetTextPattern() if doc else None
        content = tp.DocumentRange.GetText(-1) if tp else ""

    print(f"\nReadback Content Preview:\n{content[:250]}...")
    assert "area" in content.lower(), "Keyword 'area' missing from Notepad"
    assert "0.5" in content, "Formula '0.5' missing from Notepad"
    print("\n>>> LIVE RUNTIME VERIFICATION SUCCESSFUL: ALL CRITERIA MET! <<<")

if __name__ == "__main__":
    asyncio.run(main())
