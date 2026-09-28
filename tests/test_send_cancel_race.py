"""
Tests for F.R.I.D.A.Y. 3.0 — Send / Cancel Race & False Success Prevention
Verifies tight START -> CANCEL and START -> CANCEL -> START race conditions,
ensuring old tasks cannot complete into new tasks and never falsely claim COMPLETED.
"""

import sys
import unittest
from pathlib import Path

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_core.agent.task_lifecycle import (
    task_supervisor, TaskState, TaskStage
)


class TestSendCancelRace(unittest.TestCase):
    def test_immediate_cancel_race(self):
        """Verifies START -> immediately CANCEL transitions cleanly to CANCELLED without false completion."""
        session_id = "send_cancel_race_sess"

        for i in range(20):
            task = task_supervisor.create_task(query=f"Immediate cancel test {i}", session_id=session_id)
            self.assertTrue(task.is_active())

            # Immediate cancel request
            task_supervisor.cancel_task(task.task_id, reason="User clicked stop immediately")

            # Must reach terminal CANCELLED state, NEVER COMPLETED
            self.assertEqual(task.current_state, TaskState.CANCELLED)
            self.assertNotEqual(task.current_state, TaskState.COMPLETED)
            self.assertTrue(task.is_cancelled)

    def test_start_cancel_start_interleaved_race(self):
        """Verifies repeated START -> CANCEL -> START cycles never allow stale task callbacks to overwrite new tasks."""
        session_id = "interleaved_race_sess"

        for i in range(10):
            # 1. Start Task A
            task_a = task_supervisor.create_task(query=f"Task A iteration {i}", session_id=session_id)
            # 2. Cancel Task A
            task_supervisor.cancel_task(task_a.task_id, reason="Rapid cancellation")
            # 3. Start Task B immediately in same session
            task_b = task_supervisor.create_task(query=f"Task B iteration {i}", session_id=session_id)

            self.assertNotEqual(task_a.task_id, task_b.task_id)
            self.assertEqual(task_a.current_state, TaskState.CANCELLED)
            self.assertTrue(task_b.is_active())

            # Simulate delayed callback from Task A trying to claim completion
            task_supervisor.transition(task_a.task_id, TaskState.COMPLETED, "Delayed stale callback")

            # Invariant: Terminal state CANCELLED must NOT be overridden by late COMPLETED
            self.assertEqual(task_a.current_state, TaskState.CANCELLED)
            # Invariant: Task B remains the active task for session
            self.assertEqual(task_supervisor.get_active_task_for_session(session_id).task_id, task_b.task_id)

            # Clean up task B
            task_supervisor.cancel_task(task_b.task_id, reason="Cleanup")


if __name__ == "__main__":
    unittest.main()
