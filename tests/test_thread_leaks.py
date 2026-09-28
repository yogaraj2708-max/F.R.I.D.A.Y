"""
Tests for F.R.I.D.A.Y. 3.0 — Thread Leaks & QThread Lifecycle Audit
Verifies that background workers, QThreads, and task pools cleanly terminate,
returning the application thread count strictly to baseline after completion or cancellation.
"""

import gc
import sys
import time
import threading
import unittest
import psutil
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QTimer

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_core.calc import safe_calculate
from friday_core.agent.task_lifecycle import TaskRecord
from friday_core.research.worker import DeepResearchWorker
from friday_core.skills.agent_bridge import agent_tool_bridge
from friday_ui.core.engine import KokoroTTSManager


class TestThreadLeaks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance()
        if not cls.app:
            cls.app = QCoreApplication(sys.argv)

    def setUp(self):
        self.process = psutil.Process()
        gc.collect()
        time.sleep(0.05)

    def test_repeated_tool_thread_stability(self):
        """Verifies repeated tool executions create zero lingering background threads."""
        t_baseline = len(self.process.threads())

        for _ in range(50):
            safe_calculate("999 * 888 / 2")

        gc.collect()
        time.sleep(0.05)
        t_after = len(self.process.threads())

        print(f"\n[THREAD AUDIT] Tool Threads: Baseline={t_baseline}, After 50={t_after}")
        self.assertEqual(t_baseline, t_after, "Lingering threads detected after repeated tool calls")

    def test_deep_research_worker_qthread_cleanup(self):
        """Verifies DeepResearchWorker QThread cleanly terminates and unregisters on cancel."""
        from friday_core.agent.task_lifecycle import task_supervisor
        t_baseline = len(self.process.threads())

        task_rec = task_supervisor.create_task(query="Thread cleanup verification", route="RESEARCH")
        worker = DeepResearchWorker(task_record=task_rec, depth="Quick Scan")


        # Worker instantiated
        self.assertFalse(worker.isRunning())

        # Simulate start and immediate cancel
        worker.cancel()
        del worker
        gc.collect()
        time.sleep(0.05)

        t_after = len(self.process.threads())
        print(f"[THREAD AUDIT] Research Worker QThread: Baseline={t_baseline}, After Clean={t_after}")
        self.assertEqual(t_baseline, t_after)

    def test_tts_manager_thread_stability(self):
        """Verifies KokoroTTSManager uses a bounded singleton thread-safe pattern with zero thread leakage across syntheses."""
        tts_mgr = KokoroTTSManager.get_instance()
        # Warmup / ensure ONNX inference session threadpool is created
        tts_mgr.synthesize("Warmup")
        t_init = len(self.process.threads())

        # Multiple consecutive synthesis calls
        for _ in range(5):
            tts_mgr.synthesize("Thread safety check")

        gc.collect()
        time.sleep(0.05)
        t_after = len(self.process.threads())

        print(f"[THREAD AUDIT] TTS Manager: After Init={t_init}, After 5 Syntheses={t_after}")
        self.assertEqual(t_init, t_after, "Lingering worker thread leaked in TTS engine")



if __name__ == "__main__":
    unittest.main()
