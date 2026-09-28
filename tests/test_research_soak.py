"""
Tests for F.R.I.D.A.Y. 3.0 — Deep Research Soak & Cancellation Stress
Verifies repeated research task lifecycles, cancellation at diverse stages
(CREATED, STARTING, FETCHING, SYNTHESIZING), thread cleanup, and zero permanent ACTIVE states.
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

from friday_core.agent.task_lifecycle import (
    task_supervisor, TaskState, TaskStage
)
from friday_core.research.worker import DeepResearchWorker


class TestResearchSoak(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance()
        if not cls.app:
            cls.app = QCoreApplication(sys.argv)

    def setUp(self):
        self.process = psutil.Process()
        gc.collect()

    def test_repeated_research_worker_lifecycle_cleanup(self):
        """Verifies 10 consecutive research worker instantiations cleanly finalize and release resources."""
        t_baseline = len(self.process.threads())

        for i in range(1, 11):
            task = task_supervisor.create_task(
                query=f"Autonomous research soak iteration {i}",
                session_id=f"research_soak_sess_{i}",
                route="RESEARCH"
            )
            worker = DeepResearchWorker(task_record=task, depth="Quick Scan")
            # Simulate worker finishing
            worker.cancel()
            task_supervisor.transition(task.task_id, TaskState.CANCELLED, "Soak loop cleanup")
            del worker
            del task

        gc.collect()
        time.sleep(0.05)
        t_after = len(self.process.threads())

        print(f"\n[RESEARCH SOAK] 10 Consecutive Worker Runs: Baseline Threads={t_baseline}, After={t_after}")
        self.assertEqual(t_baseline, t_after, "Worker thread leakage detected across research soak runs")

    def test_deep_research_cancellation_at_multiple_stages(self):
        """Verifies cancelling research tasks at various stages guarantees 100% terminal CANCELLED state."""
        stages_to_test = [
            (TaskState.CREATED, TaskStage.TASK_CREATION),
            (TaskState.STARTING, TaskStage.SOURCE_DISCOVERY),
            (TaskState.FETCHING, TaskStage.SOURCE_FETCH),
            (TaskState.RESEARCHING, TaskStage.EVIDENCE_COLLECTION),
            (TaskState.SYNTHESIZING, TaskStage.SYNTHESIS),
        ]

        for idx, (state, stage) in enumerate(stages_to_test * 4):  # 20 cancellations
            task = task_supervisor.create_task(
                query=f"Cancellation stress test {idx}",
                session_id=f"cancel_stage_sess_{idx}",
                route="RESEARCH"
            )
            # Advance to targeted stage linearly through state machine
            sequence = [TaskState.STARTING, TaskState.RUNNING, TaskState.FETCHING, TaskState.RESEARCHING, TaskState.SYNTHESIZING]
            for s in sequence:
                if task.current_state == state:
                    break
                task_supervisor.transition(task.task_id, s, f"Advancing to {s.value}")
            task_supervisor.update_stage(task.task_id, stage, f"At {stage.value}")

            # Cancel
            task_supervisor.cancel_task(task.task_id, reason=f"Aborted at {state.value}")

            self.assertEqual(task.current_state, TaskState.CANCELLED)


            self.assertTrue(task.is_terminal())
            self.assertFalse(task.is_active())

        # Verify zero active research tasks remain
        timed_out = task_supervisor.check_watchdogs()
        for t in timed_out:
            self.assertNotEqual(t.route, "RESEARCH")


if __name__ == "__main__":
    unittest.main()
