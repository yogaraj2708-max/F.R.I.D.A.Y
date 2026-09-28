"""
Tests for F.R.I.D.A.Y. 3.0 — Section 11 & 12: Research Cancellation & Timeouts
Validates:
1. Cancellation during search vector processing.
2. Cancellation during deep page fetching / extraction.
3. Cancellation during neural synthesis streaming.
4. Late callbacks and duplicate transitions rejected after cancellation.
5. TaskSupervisor watchdog trips stalled tasks into TIMED_OUT.
"""

import unittest
from unittest.mock import MagicMock, patch
import time

from PySide6.QtCore import QCoreApplication
app = QCoreApplication.instance()
if app is None:
    app = QCoreApplication([])

from friday_core.agent.task_lifecycle import task_supervisor, TaskState, TaskStage
from friday_core.research.worker import DeepResearchWorker
from friday_core.agent.emergency_stop import emergency_stop


class TestResearchCancellationAndTimeouts(unittest.TestCase):

    def setUp(self):
        emergency_stop.reset()
        self.session_id = f"test_cancel_sess_{int(time.time() * 1000)}"

    def tearDown(self):
        emergency_stop.reset()

    def test_01_cancel_during_search_aborts_immediately(self):
        """Verify cancelling task during search phase halts worker immediately without fetching pages."""
        task = task_supervisor.create_task(
            query="test cancel during search",
            session_id=self.session_id,
            route="DEEP_RESEARCH"
        )
        worker = DeepResearchWorker(task_record=task)

        def mock_search_with_cancel(query, max_results=4):
            # Operator clicks stop while search is executing
            worker.cancel()
            return [{"title": "Test", "href": "https://example.com", "body": "Snippet"}]

        page_fetch_mock = MagicMock()

        with patch("friday_core.research.worker.fetch_web_results", side_effect=mock_search_with_cancel), \
             patch("friday_core.research.worker.fetch_page_content_detailed", page_fetch_mock):
            worker.run()

        self.assertEqual(task.current_state, TaskState.CANCELLED)
        self.assertTrue(task.is_cancelled)
        # Page fetch must not have been called because worker halted immediately
        self.assertFalse(page_fetch_mock.called)

    def test_02_cancel_during_page_fetch_aborts_before_synthesis(self):
        """Verify cancelling task during page reading halts before neural synthesis."""
        task = task_supervisor.create_task(
            query="test cancel during fetch",
            session_id=self.session_id,
            route="DEEP_RESEARCH"
        )
        worker = DeepResearchWorker(task_record=task)

        sample_hits = [
            {"title": "Src 1", "href": "https://example.com/1", "body": "Snippet 1"},
            {"title": "Src 2", "href": "https://example.com/2", "body": "Snippet 2"},
        ]

        def mock_page_fetch(url, max_chars=1800):
            # Cancel during reading of first page
            worker.cancel()
            return {"extracted_text": "Some text", "parser_status": "SUCCESS"}

        synth_mock = MagicMock()

        with patch("friday_core.research.worker.fetch_web_results", return_value=sample_hits), \
             patch("friday_core.research.worker.fetch_page_content_detailed", side_effect=mock_page_fetch), \
             patch.object(worker, "_stream_synthesis", synth_mock):
            worker.run()

        self.assertEqual(task.current_state, TaskState.CANCELLED)
        # Synthesis must not have started
        self.assertFalse(synth_mock.called)

    def test_03_cancel_during_synthesis_stream_aborts_token_emission(self):
        """Verify cancelling during Ollama streaming terminates HTTP connection and marks CANCELLED."""
        task = task_supervisor.create_task(
            query="test cancel during synthesis",
            session_id=self.session_id,
            route="DEEP_RESEARCH"
        )
        worker = DeepResearchWorker(task_record=task)

        # Mock an active HTTP client
        mock_http_client = MagicMock()
        worker._active_http_client = mock_http_client

        # Trigger cancel
        worker.cancel()
        self.assertTrue(worker.is_cancelled())
        self.assertTrue(mock_http_client.close.called)
        self.assertEqual(task.current_state, TaskState.CANCELLED)

    def test_04_watchdog_timeout_enforces_bounded_execution(self):
        """Verify task exceeding execution deadline is forcefully terminated by watchdog supervisor."""
        task = task_supervisor.create_task(
            query="test watchdog timeout",
            session_id=self.session_id,
            route="DEEP_RESEARCH",
            idle_timeout=0.1,
            absolute_timeout=0.2
        )
        task_supervisor.transition(task.task_id, TaskState.RUNNING, "Started")
        time.sleep(0.25)

        expired = task_supervisor.check_watchdogs()
        self.assertIn(task, expired)
        self.assertEqual(task.current_state, TaskState.TIMED_OUT)
        self.assertTrue(task.is_terminal())

    def test_05_late_state_mutations_rejected_on_cancelled_task(self):
        """Verify terminal CANCELLED task refuses subsequent state transitions."""
        task = task_supervisor.create_task(
            query="test late transitions",
            session_id=self.session_id,
            route="DEEP_RESEARCH"
        )
        task_supervisor.transition(task.task_id, TaskState.RUNNING, "Running")
        task_supervisor.cancel_task(task.task_id, "User stop")
        self.assertEqual(task.current_state, TaskState.CANCELLED)

        # Attempt to transition back to RUNNING or COMPLETED
        t_after = task_supervisor.transition(task.task_id, TaskState.COMPLETED, "Late complete")
        self.assertEqual(t_after.current_state, TaskState.CANCELLED)
        self.assertTrue(task.is_terminal())


if __name__ == "__main__":
    unittest.main()
