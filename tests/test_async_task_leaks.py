"""
Tests for F.R.I.D.A.Y. 3.0 — Async Task Leaks & Event Loop Hygiene
Verifies that asyncio tasks, coroutines, and background watchers cleanly resolve
or cancel, leaving zero orphan or indefinitely pending tasks after terminal states.
"""

import sys
import asyncio
import unittest
from pathlib import Path

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_core.agent.task_lifecycle import (
    task_supervisor, TaskState, TaskStage
)


class TestAsyncTaskLeaks(unittest.IsolatedAsyncioTestCase):
    async def test_completed_async_task_cleans_up(self):
        """Verifies that completed asynchronous jobs are promptly purged from active event loop."""
        loop = asyncio.get_running_loop()
        initial_tasks = len([t for t in asyncio.all_tasks(loop) if not t.done()])

        async def sample_work():
            await asyncio.sleep(0.02)
            return "done"

        task = asyncio.create_task(sample_work())
        await task

        # Allow loop turn to process callbacks
        await asyncio.sleep(0.01)
        active_tasks = len([t for t in asyncio.all_tasks(loop) if not t.done()])

        print(f"\n[ASYNC AUDIT] Initial={initial_tasks}, After Completed={active_tasks}")
        self.assertEqual(initial_tasks, active_tasks, "Completed task lingered in active event loop")

    async def test_cancelled_async_task_leaves_no_orphans(self):
        """Verifies that cancelled coroutines do not linger in pending state."""
        loop = asyncio.get_running_loop()
        initial_tasks = len([t for t in asyncio.all_tasks(loop) if not t.done()])

        async def long_running():
            try:
                await asyncio.sleep(10.0)
            except asyncio.CancelledError:
                pass

        task = asyncio.create_task(long_running())
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        await asyncio.sleep(0.01)
        active_tasks = len([t for t in asyncio.all_tasks(loop) if not t.done()])

        print(f"[ASYNC AUDIT] Cancellation: Initial={initial_tasks}, After Cancel={active_tasks}")
        self.assertEqual(initial_tasks, active_tasks, "Cancelled task orphaned in event loop")

    async def test_task_supervisor_lifecycle_no_task_leak(self):
        """Verifies task_supervisor lifecycle tracking accurately records terminal states without task retention leaks."""
        task_rec = task_supervisor.create_task(query="Async watchdog lifecycle audit", session_id="leak_test_session")
        self.assertTrue(task_rec.is_active())

        # Transition to terminal state
        task_supervisor.transition(task_rec.task_id, TaskState.RUNNING, "Executing")
        task_supervisor.transition(task_rec.task_id, TaskState.COMPLETED, "Execution complete")

        self.assertTrue(task_rec.is_terminal())
        self.assertFalse(task_rec.is_active())


        # Ensure watchdog does not track completed tasks
        timed_out = task_supervisor.check_watchdogs()
        self.assertNotIn(task_rec, timed_out)


if __name__ == "__main__":
    unittest.main()
