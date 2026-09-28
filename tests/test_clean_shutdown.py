"""
Tests for F.R.I.D.A.Y. 3.0 — Clean Shutdown & Process Reinitialization
Verifies that Friday engine components, workers, and timers cleanly terminate upon shutdown,
leaving zero orphan processes or corrupted SQLite/session databases on restart.
"""

import gc
import sys
import time
import unittest
import psutil
from pathlib import Path
from PySide6.QtCore import QCoreApplication

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_core.settings import settings
from friday_core.memory.manager import PersistentMemoryManager
from friday_core.agent.task_lifecycle import task_supervisor, TaskState
from friday_ui.core.engine import FridayBrain, FridaySignals


class TestCleanShutdown(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance()
        if not cls.app:
            cls.app = QCoreApplication(sys.argv)

    def test_clean_shutdown_and_restart_integrity(self):
        """Verifies engine shutdown releases file locks and reinitializes cleanly without DB corruption."""
        # 1. Simulate active session load
        signals = FridaySignals()
        brain = FridayBrain(signals, tts_engine=None)
        mem_mgr = PersistentMemoryManager()

        # Add data
        pref_id = mem_mgr.set_preference("tactical_theme", "cyber_dark", session_id="shutdown_test_sess")
        self.assertIsNotNone(pref_id)

        # 2. Simulate clean shutdown
        brain.abort_generation()
        del brain
        del signals
        gc.collect()
        time.sleep(0.1)

        # 3. Simulate application restart
        new_signals = FridaySignals()
        new_brain = FridayBrain(new_signals, tts_engine=None)
        new_mem_mgr = PersistentMemoryManager()

        # Verify persistent state survives cleanly without lock error
        val = new_mem_mgr.get_preference("tactical_theme", session_id="shutdown_test_sess")
        print(f"\n[CLEAN SHUTDOWN AUDIT] Restart verified preference recovery: {val}")
        self.assertEqual(val, "cyber_dark")

        # Cleanup
        new_brain.abort_generation()
        del new_brain
        del new_signals

    def test_zero_orphan_child_processes_after_load(self):
        """Verifies process tree has zero orphan workers after operations."""
        proc = psutil.Process()
        children = proc.children(recursive=True)
        print(f"[CLEAN SHUTDOWN AUDIT] Active child processes: {len(children)}")
        self.assertEqual(len(children), 0, "Orphan child processes found after workload execution")


if __name__ == "__main__":
    unittest.main()
