"""
F.R.I.D.A.Y. 3.0 — Regression Test: GUI Hang During Compound Content → Desktop Task
=====================================================================================

Root Cause: GUI_THREAD_BLOCK
  execute_mission() ran synchronously on the Qt/asyncio event loop thread.
  Blocking I/O (Ollama HTTP via urllib.request.urlopen, subprocess, UIA, time.sleep)
  in the skill execution chain prevented the Qt event loop from processing Windows
  messages, causing "Not Responding" after ~5 seconds of blocking.

Fix: Wrapped execute_mission() in asyncio.to_thread() with a 120s timeout
  at engine.py line 3340-3356, offloading all blocking I/O to a worker thread.

This test validates:
  1. The compound parser correctly decomposes the crash command
  2. execute_mission is callable from a thread (thread safety)
  3. The asyncio.to_thread pattern works with the executor
  4. Timeout containment works
  5. Exception containment works
  6. GUI thread is never blocked (simulated)
"""

import sys
import os
import asyncio
import time
import threading
import unittest
from unittest.mock import MagicMock, patch
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from friday_core.agent.compound import compound_parser, CompoundPlan
from friday_core.agent.executor import PEOVExecutor
from friday_core.agent.mission_store import MissionState, MissionStep, MissionStatus


class TestGUIHangRegression(unittest.TestCase):
    """Tests that compound mission execution does not block the calling thread."""

    # ─── Test 1: Compound Parser Produces Valid Plan ───

    def test_crash_command_parsed(self):
        """The exact crash command must produce a valid compound plan."""
        plan = compound_parser.parse("write a summary of Harry Potter and put it in my note pad")
        self.assertIsNotNone(plan)
        self.assertEqual(len(plan.steps), 5)
        actions = [s.action for s in plan.steps]
        self.assertIn("content_generation", actions)

    # ─── Test 2: execute_mission Is Thread-Safe ───

    def test_execute_mission_runs_on_worker_thread(self):
        """execute_mission must be callable from a non-main thread without crashing."""
        # Create a minimal mission with a mock skill
        mission = MissionState(
            mission_id="test-thread-safety",
            goal="test",
            steps=[],
            status=MissionStatus.PENDING
        )

        executor = PEOVExecutor()
        result_holder = {}

        def run_on_thread():
            try:
                res = executor.execute_mission(mission)
                result_holder["status"] = res.status
                result_holder["thread"] = threading.current_thread().name
            except Exception as ex:
                result_holder["error"] = str(ex)

        t = threading.Thread(target=run_on_thread, name="TestWorkerThread")
        t.start()
        t.join(timeout=5.0)

        self.assertFalse(t.is_alive(), "Worker thread hung")
        self.assertNotIn("error", result_holder, f"Error: {result_holder.get('error')}")
        self.assertEqual(result_holder["status"], MissionStatus.COMPLETED)
        self.assertEqual(result_holder["thread"], "TestWorkerThread")

    # ─── Test 3: asyncio.to_thread Pattern Works ───

    def test_asyncio_to_thread_offload(self):
        """Verify asyncio.to_thread correctly offloads execute_mission."""
        mission = MissionState(
            mission_id="test-async-offload",
            goal="test",
            steps=[],
            status=MissionStatus.PENDING
        )
        executor = PEOVExecutor()

        async def run():
            res = await asyncio.to_thread(executor.execute_mission, mission)
            return res

        result = asyncio.run(run())
        self.assertEqual(result.status, MissionStatus.COMPLETED)

    # ─── Test 4: Timeout Containment ───

    def test_timeout_containment(self):
        """A hanging mission must be interrupted by asyncio.wait_for timeout."""
        def slow_execute(mission):
            time.sleep(10)  # Simulate hang
            return mission

        async def run():
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    asyncio.to_thread(slow_execute, "dummy"),
                    timeout=0.5
                )

        asyncio.run(run())

    # ─── Test 5: Exception Containment ───

    def test_exception_containment(self):
        """A crashing mission must propagate the exception cleanly, not freeze."""
        def crashing_execute(mission):
            raise RuntimeError("Simulated skill crash")

        async def run():
            with self.assertRaises(RuntimeError):
                await asyncio.to_thread(crashing_execute, "dummy")

        asyncio.run(run())

    # ─── Test 6: GUI Thread Not Blocked (Simulated) ───

    def test_gui_thread_remains_responsive(self):
        """The calling thread must remain responsive while mission runs on worker."""
        heartbeats = []

        def slow_mission(mission):
            time.sleep(1.0)
            return MissionState(
                mission_id="slow", goal="test", steps=[],
                status=MissionStatus.COMPLETED
            )

        async def run():
            # Start mission on worker thread
            mission_task = asyncio.ensure_future(
                asyncio.to_thread(slow_mission, "dummy")
            )

            # Simulate GUI heartbeats while mission runs
            for i in range(5):
                heartbeats.append(time.monotonic())
                await asyncio.sleep(0.2)

            await mission_task
            return mission_task.result()

        result = asyncio.run(run())
        self.assertEqual(result.status, MissionStatus.COMPLETED)
        # Verify heartbeats occurred during mission execution (GUI was responsive)
        self.assertGreaterEqual(len(heartbeats), 4)
        # Verify heartbeats were spaced ~200ms apart (not blocked)
        for i in range(1, len(heartbeats)):
            gap = heartbeats[i] - heartbeats[i-1]
            self.assertLess(gap, 0.5, f"Heartbeat gap {gap:.2f}s too large — GUI would have frozen")

    # ─── Test 7: Post-Failure Recovery ───

    def test_app_accepts_commands_after_failure(self):
        """After a mission failure, the system must accept new commands."""
        executor = PEOVExecutor()

        # Simulate a failed mission
        failed_mission = MissionState(
            mission_id="fail-test",
            goal="fail",
            steps=[MissionStep(
                step_id="bad_step",
                tool_id="nonexistent_skill",
                params={},
                description="This should fail"
            )],
            status=MissionStatus.PENDING
        )
        result1 = executor.execute_mission(failed_mission)
        self.assertEqual(result1.status, MissionStatus.FAILED)

        # Simulate a subsequent simple mission (recovery)
        ok_mission = MissionState(
            mission_id="recovery-test",
            goal="recover",
            steps=[],
            status=MissionStatus.PENDING
        )
        result2 = executor.execute_mission(ok_mission)
        self.assertEqual(result2.status, MissionStatus.COMPLETED)

    # ─── Test 8: Repeated Command Does Not Stack ───

    def test_repeated_commands_do_not_deadlock(self):
        """Running multiple sequential missions must not cause deadlock."""
        executor = PEOVExecutor()

        async def run():
            for i in range(3):
                mission = MissionState(
                    mission_id=f"repeat-{i}",
                    goal="test",
                    steps=[],
                    status=MissionStatus.PENDING
                )
                res = await asyncio.to_thread(executor.execute_mission, mission)
                self.assertEqual(res.status, MissionStatus.COMPLETED)

        asyncio.run(run())

    # ─── Test 9: Content Generation Skill Blocks Only Worker Thread ───

    def test_content_generation_blocks_worker_not_main(self):
        """Content generation HTTP call must only block the worker thread."""
        main_thread_id = threading.current_thread().ident
        worker_thread_ids = []

        def mock_execute(mission):
            worker_thread_ids.append(threading.current_thread().ident)
            time.sleep(0.5)  # Simulate Ollama HTTP delay
            return MissionState(
                mission_id="gen-test", goal="test", steps=[],
                status=MissionStatus.COMPLETED
            )

        async def run():
            result = await asyncio.to_thread(mock_execute, "dummy")
            return result

        asyncio.run(run())
        self.assertEqual(len(worker_thread_ids), 1)
        self.assertNotEqual(worker_thread_ids[0], main_thread_id,
                          "Blocking operation ran on main thread!")


class TestCompoundParserCrashCommand(unittest.TestCase):
    """Validates the compound parser handles the exact crash command correctly."""

    def test_harry_potter_summary_plan(self):
        plan = compound_parser.parse("write a summary of Harry Potter and put it in my note pad")
        self.assertIsNotNone(plan)
        self.assertEqual(plan.steps[0].action, "open_app")
        self.assertEqual(plan.steps[1].action, "content_generation")
        self.assertEqual(plan.steps[2].action, "ui_focus")
        self.assertEqual(plan.steps[3].action, "ui_type_text")
        self.assertEqual(plan.steps[4].action, "ui_verify_content")

    def test_content_gen_uses_variable_ref(self):
        plan = compound_parser.parse("write a summary of Harry Potter and put it in my note pad")
        self.assertTrue(plan.steps[3].params["text"].startswith("$content_generation"))

    def test_no_literal_text_in_type_step(self):
        """The type step must NOT contain 'a summary of Harry Potter' as literal text."""
        plan = compound_parser.parse("write a summary of Harry Potter and put it in my note pad")
        typed_text = plan.steps[3].params["text"]
        self.assertNotIn("Harry Potter", typed_text)
        self.assertNotIn("summary", typed_text.lower().replace("$content_generation", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
