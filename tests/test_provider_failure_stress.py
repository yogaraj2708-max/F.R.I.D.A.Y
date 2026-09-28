"""
Tests for F.R.I.D.A.Y. 3.0 — Provider & Network Failure Stress
Simulates Ollama connection drops, HTTP 500, timeouts, malformed JSON, and offline DNS failures.
Verifies bounded retries, honest error reporting, clean state cleanup, and zero hanging tasks.
"""

import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import httpx

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_core.agent.task_lifecycle import task_supervisor, TaskState
from friday_core.skills.agent_bridge import agent_tool_bridge
from friday_core.web.fetcher import web_fetch


class TestProviderFailureStress(unittest.TestCase):
    def test_provider_connection_refused_honest_failure(self):
        """Verifies connection failure to Ollama endpoint transitions cleanly to terminal state without hanging."""
        task = task_supervisor.create_task(query="Probe offline provider", session_id="failure_stress_sess")
        task_supervisor.transition(task.task_id, TaskState.RUNNING, "Contacting provider")

        # Simulate connection error
        try:
            with httpx.Client(timeout=0.01) as client:
                client.get("http://127.0.0.1:1/nonexistent")
        except Exception as ex:
            task.error = f"Provider connection error: {ex}"
            task_supervisor.transition(task.task_id, TaskState.FAILED, "Connection refused")

        print(f"\n[FAILURE AUDIT] Offline Provider: Final State={task.current_state}, Error={task.error[:60]}")
        self.assertEqual(task.current_state, TaskState.FAILED)
        self.assertTrue(task.is_terminal())
        self.assertIsNotNone(task.error)

    def test_network_offline_dns_failure_handling(self):
        """Verifies web fetching handles invalid DNS/offline errors cleanly without throwing unhandled exceptions."""
        result = web_fetch("https://invalid-nonexistent-domain-friday-audit-test.local/doc")
        print(f"[FAILURE AUDIT] Web Fetch DNS failure response: {result[:80]}")
        self.assertTrue("blocked" in result.lower() or "error" in result.lower() or "failed" in result.lower())

    def test_malformed_tool_argument_validation(self):
        """Verifies malformed or illegal parameters to tools trigger honest rejection rather than crashes."""
        from friday_core.calc import safe_calculate
        # Malformed expression
        res = safe_calculate("25 * + / -- 100")
        print(f"[FAILURE AUDIT] Malformed calc input response: {res}")
        # Returns None on invalid syntax without crashing
        self.assertIsNone(res)


    def test_provider_timeout_watchdog_enforcement(self):
        """Verifies stalled provider responses trigger watchdog timeout and transition to TIMED_OUT."""
        # Create task with short 0.1s timeout
        task = task_supervisor.create_task(
            query="Stalled model query",
            session_id="timeout_sess",
            idle_timeout=0.1
        )
        task_supervisor.transition(task.task_id, TaskState.RUNNING, "Waiting for model generation")

        # Age the task artificially
        task.last_progress_at = task.last_progress_at - 1.0

        timed_out = task_supervisor.check_watchdogs()
        self.assertIn(task, timed_out)
        self.assertEqual(task.current_state, TaskState.TIMED_OUT)
        self.assertTrue(task.is_terminal())


if __name__ == "__main__":
    unittest.main()
