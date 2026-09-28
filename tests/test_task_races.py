"""
Tests for F.R.I.D.A.Y. 3.0 — Task Races & Concurrency Control
Verifies that rapid submissions, overlapping commands, and multi-session concurrency
maintain unique task IDs, strict session isolation, and clean state machine invariants.
"""

import sys
import unittest
import threading
from pathlib import Path

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_core.agent.task_lifecycle import task_supervisor, TaskState


class TestTaskRaces(unittest.TestCase):
    def test_rapid_task_creation_unique_ids(self):
        """Verifies that 100 concurrent rapid task submissions generate strictly unique IDs."""
        task_ids = set()
        lock = threading.Lock()

        def create_batch():
            for i in range(10):
                t = task_supervisor.create_task(query=f"Rapid race query {i}", session_id=f"sess_{threading.get_ident()}")
                with lock:
                    task_ids.add(t.task_id)

        threads = [threading.Thread(target=create_batch) for _ in range(10)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        print(f"\n[RACE AUDIT] Total generated unique task IDs: {len(task_ids)}")
        self.assertEqual(len(task_ids), 100, "Duplicate task IDs detected under concurrent creation")

    def test_same_session_superseding_race(self):
        """Verifies that rapid submissions in the SAME session cleanly supersede prior active tasks."""
        session_id = "race_supersede_session"

        t1 = task_supervisor.create_task(query="First directive", session_id=session_id)
        self.assertTrue(t1.is_active())

        # Second directive immediately arrives
        t2 = task_supervisor.create_task(query="Second directive", session_id=session_id)

        print(f"[RACE AUDIT] Task 1 state: {t1.current_state}, Task 2 state: {t2.current_state}")
        # t1 must be cancelled or cancel requested, t2 active
        self.assertTrue(t1.current_state in {TaskState.CANCEL_REQUESTED, TaskState.CANCELLED})
        self.assertTrue(t2.is_active())

    def test_cross_session_task_isolation(self):
        """Verifies concurrent tasks across different sessions execute without state contamination."""
        sess_a = "session_alpha"
        sess_b = "session_beta"

        t_a = task_supervisor.create_task(query="Alpha task", session_id=sess_a)
        t_b = task_supervisor.create_task(query="Beta task", session_id=sess_b)

        # Transition t_a to RUNNING
        task_supervisor.transition(t_a.task_id, TaskState.RUNNING, "Alpha started")

        # t_b state must NOT be impacted by t_a
        self.assertEqual(t_a.current_state, TaskState.RUNNING)
        self.assertEqual(t_b.current_state, TaskState.CREATED)


if __name__ == "__main__":
    unittest.main()
