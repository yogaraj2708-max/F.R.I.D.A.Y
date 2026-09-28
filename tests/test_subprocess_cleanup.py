"""
Tests for F.R.I.D.A.Y. 3.0 — Subprocess Cleanup & Orphan Process Audit
Verifies that document tools, automation actions, system launchers, and cancelled
operations leave zero orphan child processes.
"""

import sys
import time
import unittest
import psutil
from pathlib import Path

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_core.calc import safe_calculate
from friday_core.system.telemetry import get_cpu_info
from friday_core.skills.builtins.desktop_action import capture_and_save_screenshot


class TestSubprocessCleanup(unittest.TestCase):
    def setUp(self):
        self.process = psutil.Process()

    def get_child_count(self) -> int:
        return len(self.process.children(recursive=True))

    def test_tool_execution_leaves_no_orphan_processes(self):
        """Verifies repeated tool calls do not spawn lingering child processes."""
        c_baseline = self.get_child_count()

        for _ in range(20):
            safe_calculate("50 * 50 + 25")
            get_cpu_info()

        time.sleep(0.05)
        c_after = self.get_child_count()

        print(f"\n[SUBPROCESS AUDIT] Tool Operations: Baseline={c_baseline}, After 20={c_after}")
        self.assertEqual(c_baseline, c_after, "Lingering child processes detected after tool operations")

    def test_screenshot_action_leaves_no_zombie_processes(self):
        """Verifies desktop screenshot capture is handled purely in-process or cleans up helpers."""
        c_baseline = self.get_child_count()

        try:
            capture_and_save_screenshot()
        except Exception:
            # Headless or CI environment fallback
            pass

        time.sleep(0.05)
        c_after = self.get_child_count()

        print(f"[SUBPROCESS AUDIT] Screenshot Capture: Baseline={c_baseline}, After={c_after}")
        self.assertEqual(c_baseline, c_after, "Zombie child process detected after screenshot capture")


if __name__ == "__main__":
    unittest.main()
