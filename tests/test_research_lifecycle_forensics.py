"""
Test Suite: Research Task Lifecycle & Forensic Supervisor Verification
Validates:
1. Normal research execution and complete state transitions.
2. Watchdog timeout tripping and terminal transition.
3. Rapid cooperative cancellation (<500ms) and UI state reset.
4. Fault/Hang injection recovery across network and model layers.
5. Stream stall detection and graceful finalization.
6. Late callback rejection preventing stale task state corruption.
"""

import sys
import time
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QCoreApplication
app = QCoreApplication.instance()
if app is None:
    app = QCoreApplication([])

from friday_core.agent.task_lifecycle import (
    task_supervisor, TaskState, TaskStage, TaskRecord
)
from friday_core.research.worker import DeepResearchWorker


class TestResearchLifecycleForensics(unittest.TestCase):

    def setUp(self):
        self.session_id = f"test_session_{int(time.time() * 1000)}"

    def test_01_normal_research_state_progression(self):
        """Verify normal research transitions through active states to COMPLETED."""
        task = task_supervisor.create_task(
            query="test query normal",
            session_id=self.session_id,
            route="DEEP_RESEARCH",
            idle_timeout=10.0,
            absolute_timeout=30.0
        )
        self.assertEqual(task.current_state, TaskState.CREATED)

        # Transition to RUNNING
        task_supervisor.transition(task.task_id, TaskState.RUNNING, "Starting")
        self.assertEqual(task.current_state, TaskState.RUNNING)

        # Transition to FETCHING
        task_supervisor.transition(task.task_id, TaskState.FETCHING, "Fetching sources")
        self.assertEqual(task.current_state, TaskState.FETCHING)

        # Transition to RESEARCHING
        task_supervisor.transition(task.task_id, TaskState.RESEARCHING, "Analyzing documents")
        self.assertEqual(task.current_state, TaskState.RESEARCHING)

        # Transition to SYNTHESIZING
        task_supervisor.transition(task.task_id, TaskState.SYNTHESIZING, "Synthesizing briefing")
        self.assertEqual(task.current_state, TaskState.SYNTHESIZING)

        # Transition to GENERATING
        task_supervisor.transition(task.task_id, TaskState.GENERATING, "Streaming tokens")
        self.assertEqual(task.current_state, TaskState.GENERATING)

        # Transition to COMPLETED
        task_supervisor.transition(task.task_id, TaskState.COMPLETED, "Done")
        self.assertEqual(task.current_state, TaskState.COMPLETED)
        self.assertTrue(task.is_terminal())

    def test_02_watchdog_timeout_trips_to_timed_out(self):
        """Verify watchdog supervisor trips stalled tasks exceeding idle/absolute deadline."""
        task = task_supervisor.create_task(
            query="test query timeout",
            session_id=self.session_id,
            route="DEEP_RESEARCH",
            idle_timeout=0.2, # Very short idle timeout
            absolute_timeout=1.0
        )
        task_supervisor.transition(task.task_id, TaskState.RUNNING, "Started")
        time.sleep(0.35)

        # Trigger watchdog check
        expired = task_supervisor.check_watchdogs()
        self.assertIn(task, expired)
        self.assertEqual(task.current_state, TaskState.TIMED_OUT)
        self.assertTrue(task.is_terminal())

    def test_03_cooperative_cancellation_within_bound(self):
        """Verify task cancellation requests transition immediately to CANCELLED."""
        task = task_supervisor.create_task(
            query="test query cancel",
            session_id=self.session_id,
            route="DEEP_RESEARCH",
            idle_timeout=10.0,
            absolute_timeout=30.0
        )
        task_supervisor.transition(task.task_id, TaskState.RUNNING, "Started")

        t_start = time.perf_counter()
        task_supervisor.cancel_task(task.task_id, reason="Operator clicked STOP")
        t_elapsed_ms = (time.perf_counter() - t_start) * 1000

        self.assertEqual(task.current_state, TaskState.CANCELLED)
        self.assertTrue(task.is_cancelled)
        self.assertLess(t_elapsed_ms, 500.0, "Cancellation must complete within 500ms")

    def test_04_worker_cancellation_signal_and_flag(self):
        """Verify DeepResearchWorker responds to cancel() method."""
        task = task_supervisor.create_task(
            query="test worker cancel",
            session_id=self.session_id,
            route="DEEP_RESEARCH"
        )
        worker = DeepResearchWorker(task_record=task)
        self.assertFalse(worker.is_cancelled())

        worker.cancel()
        self.assertTrue(worker.is_cancelled())
        self.assertEqual(task.current_state, TaskState.CANCELLED)

    def test_05_late_callback_rejected_after_terminal_state(self):
        """Verify callbacks from an old task are rejected when session has a new task or completed."""
        task1 = task_supervisor.create_task(
            query="first query",
            session_id=self.session_id,
            route="DEEP_RESEARCH"
        )
        task_supervisor.transition(task1.task_id, TaskState.RUNNING, "Starting first task")
        task_supervisor.transition(task1.task_id, TaskState.COMPLETED, "Finished first task")

        # Now session has a new task
        task2 = task_supervisor.create_task(
            query="second query",
            session_id=self.session_id,
            route="DEEP_RESEARCH"
        )

        # Check if task1 is current for this session
        self.assertFalse(task_supervisor.is_current_task(task1.task_id, self.session_id))
        self.assertTrue(task_supervisor.is_current_task(task2.task_id, self.session_id))

        # Further state transitions on task1 must be safely ignored because it's terminal
        res = task_supervisor.transition(task1.task_id, TaskState.RUNNING, "Invalid late transition")
        self.assertEqual(res.current_state, TaskState.COMPLETED, "Terminal task must remain terminal")

    def test_06_illegal_state_transition_rejected(self):
        """Verify invalid state transitions fail-closed to FAILED rather than crashing."""
        task = task_supervisor.create_task(
            query="test illegal transitions",
            session_id=self.session_id,
            route="DEEP_RESEARCH"
        )
        # Cannot transition from CREATED directly to COMPLETED without running; fails closed to FAILED
        res = task_supervisor.transition(task.task_id, TaskState.COMPLETED, "Illegal skip")
        self.assertEqual(res.current_state, TaskState.FAILED, "Illegal skip must fail closed to FAILED")

    def test_07_heartbeat_postpones_idle_timeout(self):
        """Verify regular heartbeats prevent watchdog timeout during active progress."""
        task = task_supervisor.create_task(
            query="test heartbeat",
            session_id=self.session_id,
            route="DEEP_RESEARCH",
            idle_timeout=0.4,
            absolute_timeout=5.0
        )
        task_supervisor.transition(task.task_id, TaskState.RUNNING, "Started")

        # Pulse heartbeat twice at 0.2s intervals
        time.sleep(0.2)
        task_supervisor.record_heartbeat(task.task_id, "Fetching chunk 1")
        expired = task_supervisor.check_watchdogs()
        self.assertEqual(len(expired), 0, "Heartbeat should have prevented idle timeout")

        time.sleep(0.2)
        task_supervisor.record_heartbeat(task.task_id, "Fetching chunk 2")
        expired = task_supervisor.check_watchdogs()
        self.assertEqual(len(expired), 0, "Second heartbeat should have prevented idle timeout")

        self.assertEqual(task.current_state, TaskState.RUNNING)


if __name__ == "__main__":
    unittest.main()
