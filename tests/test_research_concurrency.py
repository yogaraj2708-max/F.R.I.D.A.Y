"""
Tests for F.R.I.D.A.Y. 3.0 — Section 32 & 33: Research Concurrency & Session Isolation
Validates:
1. Two concurrent research tasks maintain isolated task IDs, contexts, and source lists.
2. Cancelling Task A does NOT cancel or impact running Task B.
3. Sequential tasks in the same session do not leak sources or findings (no state pollution).
"""

import unittest
from unittest.mock import MagicMock, patch
import time

from PySide6.QtCore import QCoreApplication
app = QCoreApplication.instance()
if app is None:
    app = QCoreApplication([])

from friday_core.agent.task_lifecycle import task_supervisor, TaskState
from friday_core.research.worker import DeepResearchWorker
from friday_core.research.models import ResearchSource


class TestResearchConcurrency(unittest.TestCase):

    def setUp(self):
        self.session_a = f"session_a_{int(time.time() * 1000)}"
        self.session_b = f"session_b_{int(time.time() * 1000)}"

    def test_01_concurrent_tasks_maintain_isolated_states(self):
        """Verify two simultaneous tasks have isolated records, queries, and states."""
        task_a = task_supervisor.create_task(
            query="Research Topic A: Solid State Batteries",
            session_id=self.session_a,
            route="DEEP_RESEARCH"
        )
        task_b = task_supervisor.create_task(
            query="Research Topic B: Photonic Interconnects",
            session_id=self.session_b,
            route="DEEP_RESEARCH"
        )

        self.assertNotEqual(task_a.task_id, task_b.task_id)
        self.assertEqual(task_a.query, "Research Topic A: Solid State Batteries")
        self.assertEqual(task_b.query, "Research Topic B: Photonic Interconnects")

        # Advance Task A to FETCHING, Task B to RUNNING
        task_supervisor.transition(task_a.task_id, TaskState.RUNNING, "Starting A")
        task_supervisor.transition(task_a.task_id, TaskState.FETCHING, "Fetching A")

        task_supervisor.transition(task_b.task_id, TaskState.RUNNING, "Starting B")

        self.assertEqual(task_a.current_state, TaskState.FETCHING)
        self.assertEqual(task_b.current_state, TaskState.RUNNING)

    def test_02_cancellation_of_task_a_does_not_cancel_task_b(self):
        """Verify cancelling Task A leaves Task B unaffected and running."""
        task_a = task_supervisor.create_task(
            query="Cancelable Task A",
            session_id=self.session_a,
            route="DEEP_RESEARCH"
        )
        task_b = task_supervisor.create_task(
            query="Independent Task B",
            session_id=self.session_b,
            route="DEEP_RESEARCH"
        )

        worker_a = DeepResearchWorker(task_record=task_a)
        worker_b = DeepResearchWorker(task_record=task_b)

        # Cancel worker A
        worker_a.cancel()

        self.assertTrue(worker_a.is_cancelled())
        self.assertEqual(task_a.current_state, TaskState.CANCELLED)

        # Worker B must remain untouched
        self.assertFalse(worker_b.is_cancelled())
        self.assertNotEqual(task_b.current_state, TaskState.CANCELLED)

    def test_03_same_session_sequential_isolation(self):
        """Verify sequential tasks in the same session do not inherit sources from previous runs."""
        same_session = "shared_session_123"

        # Task 1
        task_1 = task_supervisor.create_task(
            query="Quantum Computing Qubits",
            session_id=same_session,
            route="DEEP_RESEARCH"
        )
        worker_1 = DeepResearchWorker(task_record=task_1)

        hits_1 = [{"title": "Quantum Hit", "href": "https://quantum.org/1", "body": "Qubit coherence."}]
        with patch("friday_core.research.worker.fetch_web_results", return_value=hits_1), \
             patch("friday_core.research.worker.fetch_page_content_detailed", return_value={"extracted_text": "Qubit coherence data " * 10, "parser_status": "SUCCESS"}), \
             patch.object(worker_1, "_stream_synthesis", return_value="Quantum Report"):
            worker_1.run()

        self.assertEqual(task_1.current_state, TaskState.COMPLETED)

        # Task 2 in the same session
        task_2 = task_supervisor.create_task(
            query="Aerospace Titanium Alloys",
            session_id=same_session,
            route="DEEP_RESEARCH"
        )
        worker_2 = DeepResearchWorker(task_record=task_2)

        hits_2 = [{"title": "Aero Hit", "href": "https://aero.org/1", "body": "Titanium alloy strength."}]
        captured_prompt_2 = []

        def mock_stream_2(prompt):
            captured_prompt_2.append(prompt)
            return "Aero Report"

        with patch("friday_core.research.worker.fetch_web_results", return_value=hits_2), \
             patch("friday_core.research.worker.fetch_page_content_detailed", return_value={"extracted_text": "Titanium alloy data " * 10, "parser_status": "SUCCESS"}), \
             patch.object(worker_2, "_stream_synthesis", side_effect=mock_stream_2):
            worker_2.run()

        self.assertEqual(task_2.current_state, TaskState.COMPLETED)
        self.assertEqual(len(captured_prompt_2), 1)

        # Verify prompt for task 2 does NOT contain task 1's URLs or content
        self.assertNotIn("https://quantum.org/1", captured_prompt_2[0])
        self.assertNotIn("Qubit coherence", captured_prompt_2[0])
        self.assertIn("https://aero.org/1", captured_prompt_2[0])


if __name__ == "__main__":
    unittest.main()
