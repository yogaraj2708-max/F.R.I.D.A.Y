"""
Tests for F.R.I.D.A.Y. 3.0 — Model Switch Races & Model Policy Verification
Verifies repeated model switches, capability cache purges, and verifies that switching
models during an active task never silently mutates or corrupts in-flight task parameters.
"""

import sys
import unittest
from pathlib import Path

root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from friday_core.settings import settings
from friday_core.agent.task_lifecycle import task_supervisor, TaskState
from friday_ui.core.engine import FridayBrain, FridaySignals


class TestModelSwitchRace(unittest.TestCase):
    def setUp(self):
        self.signals = FridaySignals()
        self.brain = FridayBrain(self.signals, tts_engine=None)

    def test_repeated_model_switching_stability(self):
        """Verifies 20 repeated model switches invalidate capability caches and update active settings cleanly."""
        models = ["qwen3.5:9b", "qwen2.5:0.5b", "llama3.2:1b", "deepseek-r1:8b"]

        for i in range(20):
            target_model = models[i % len(models)]
            # Seed dummy cache
            self.brain._tool_capability_cache[self.brain.model] = "VERIFIED"

            # Switch model
            self.brain._on_settings_change("model", target_model)

            self.assertEqual(self.brain.model, target_model)
            self.assertEqual(len(self.brain._tool_capability_cache), 0, "Capability cache failed to clear on switch")
            self.assertEqual(self.brain.semantic_router.ollama_model, target_model)

        print(f"\n[MODEL SWITCH AUDIT] 20 model switches completed with clean cache invalidation.")

    def test_model_switch_during_active_task_immutability(self):
        """
        Verifies policy: Active tasks retain their original launch model bound to TaskRecord.
        Model changes mid-flight apply to future tasks, preventing in-flight task corruption.
        """
        original_model = "qwen3.5:9b"
        self.brain.model = original_model

        # Launch active task under original model
        task = task_supervisor.create_task(
            query="Long running simulation directive",
            session_id="model_switch_sess",
            model=self.brain.model
        )
        task_supervisor.transition(task.task_id, TaskState.RUNNING, "Task running")

        self.assertEqual(task.model, original_model)
        self.assertTrue(task.is_active())

        # Switch global model mid-flight
        new_model = "qwen2.5:0.5b"
        self.brain._on_settings_change("model", new_model)

        # Invariant: Active task record remains bound to original model
        self.assertEqual(task.model, original_model, "Active task was silently mutated mid-stream")
        # Invariant: Brain has adopted the new model for next tasks
        self.assertEqual(self.brain.model, new_model)

        # Subsequent task created adopts new model
        task_next = task_supervisor.create_task(
            query="Next directive",
            session_id="model_switch_sess_2",
            model=self.brain.model
        )
        self.assertEqual(task_next.model, new_model)

        # Cleanup
        task_supervisor.cancel_task(task.task_id, reason="Test finish")
        task_supervisor.cancel_task(task_next.task_id, reason="Test finish")


if __name__ == "__main__":
    unittest.main()
