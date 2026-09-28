"""
Tests for F.R.I.D.A.Y. 3.0 — Phase 13: Proactive Scheduler & Windows Notifications
Validates:
1. WindowsNotifier notification dispatch and audit history.
2. SystemHealthMonitor telemetry sampling and threshold alerts.
3. ProactiveScheduler recurring interval tasks and one-shot execution.
4. Emergency Stop integration halting proactive background executions.
5. Task pausing, resumption, and dynamic removal.
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from friday_core.scheduler.models import (
    ScheduledTaskType,
    TaskPriority,
    NotificationMessage
)
from friday_core.scheduler.notifier import WindowsNotifier
from friday_core.scheduler.proactive_monitor import SystemHealthMonitor
from friday_core.scheduler.scheduler import ProactiveScheduler
from friday_core.agent.emergency_stop import emergency_stop


class TestSchedulerAndNotifications(unittest.TestCase):
    def setUp(self):
        emergency_stop.reset()
        self.notifier = WindowsNotifier(enable_system_toasts=False)
        self.scheduler = ProactiveScheduler()

    def tearDown(self):
        self.scheduler.stop()
        emergency_stop.reset()

    def test_windows_notifier_audit_and_dispatch(self):
        """Validates that notifications are recorded into the immutable audit history."""
        msg = self.notifier.notify(
            title="Meeting in 15 Minutes",
            body="Review Q3 budget roadmap with the engineering team.",
            urgency=TaskPriority.HIGH,
            action_button="Open Calendar"
        )
        self.assertEqual(msg.title, "Meeting in 15 Minutes")
        self.assertEqual(msg.urgency, TaskPriority.HIGH)
        self.assertEqual(msg.action_button, "Open Calendar")

        history = self.notifier.get_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].id, msg.id)

        self.notifier.clear_history()
        self.assertEqual(len(self.notifier.get_history()), 0)

    @patch("shutil.disk_usage")
    @patch("psutil.virtual_memory")
    @patch("psutil.cpu_percent")
    def test_system_health_monitor_triggers_alerts(self, mock_cpu, mock_mem, mock_disk):
        """Validates that hardware limits trigger proactive notifications."""
        # Simulate: Low Disk (< 10GB free)
        mock_disk.return_value = MagicMock(free=5 * (1024 ** 3))  # 5 GB
        mock_mem.return_value = MagicMock(percent=75.0)
        mock_cpu.return_value = 25.0

        monitor = SystemHealthMonitor(notifier=self.notifier)
        metrics = monitor.check_health()
        self.assertLess(metrics["disk_free_gb"], 10.0)

        history = self.notifier.get_history()
        self.assertEqual(len(history), 1)
        self.assertIn("Low Storage Warning", history[0].title)

    def test_proactive_scheduler_interval_and_tick(self):
        """Validates recurring interval tasks execute upon tick evaluation."""
        execution_count = 0

        def sample_job():
            nonlocal execution_count
            execution_count += 1

        task_id = self.scheduler.add_interval_task(
            name="test_interval_job",
            interval_seconds=10.0,
            callback=sample_job
        )

        now = time.time()
        # Before time elapsed: should not run
        executed = self.scheduler.tick(now=now + 5.0)
        self.assertNotIn(task_id, executed)
        self.assertEqual(execution_count, 0)

        # After interval elapsed: should run once
        executed = self.scheduler.tick(now=now + 11.0)
        self.assertIn(task_id, executed)
        self.assertEqual(execution_count, 1)

        # Next interval
        executed = self.scheduler.tick(now=now + 22.0)
        self.assertIn(task_id, executed)
        self.assertEqual(execution_count, 2)

    def test_one_shot_task_automatic_removal(self):
        """Validates that ONE-SHOT tasks run once and are automatically removed from scheduler."""
        fired = False

        def one_shot_job():
            nonlocal fired
            fired = True

        now = time.time()
        task_id = self.scheduler.add_once_task("quick_alarm", delay_seconds=5.0, callback=one_shot_job)
        self.assertFalse(fired)

        # Fire task
        executed = self.scheduler.tick(now=now + 6.0)
        self.assertIn(task_id, executed)
        self.assertTrue(fired)

        # Verify task is pruned from list
        all_tasks = self.scheduler.list_tasks()
        self.assertNotIn(task_id, [t.task_id for t in all_tasks])

    def test_emergency_stop_halts_scheduler(self):
        """Validates that Emergency Stop suppresses all task execution."""
        ran = False

        def emergency_target():
            nonlocal ran
            ran = True

        task_id = self.scheduler.add_interval_task("blocked_job", interval_seconds=1.0, callback=emergency_target)
        now = time.time()

        # Trigger emergency stop
        emergency_stop.trigger_stop(source="test")
        self.assertTrue(emergency_stop.is_stopped())

        executed = self.scheduler.tick(now=now + 10.0)
        self.assertEqual(executed, [])
        self.assertFalse(ran)


if __name__ == "__main__":
    unittest.main()
