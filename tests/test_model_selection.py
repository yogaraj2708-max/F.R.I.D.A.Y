"""
Tests for Model Selection and Resolution (Section 2, 7, 30, 31).
Verifies:
1. MAIN_AGENT_MODEL is resolved dynamically from settings.get("model").
2. No hard-coded deepseek-r1:8b or llama3.2:1b as fixed main model.
3. Model configuration changes update the active brain model immediately.
"""

import unittest
from unittest.mock import MagicMock
from friday_core.settings import settings
from friday_ui.core.engine import FridayBrain, FridaySignals


class TestModelSelection(unittest.TestCase):
    def setUp(self):
        self.original_model = settings.get("model")
        self.signals = FridaySignals()
        self.tts = MagicMock()

    def tearDown(self):
        if self.original_model:
            settings.set("model", self.original_model)

    def test_dynamic_model_resolution_from_settings(self):
        settings.set("model", "custom-agent-model:v1")
        brain = FridayBrain(self.signals, self.tts)
        self.assertEqual(brain.model, "custom-agent-model:v1")

    def test_model_not_hardcoded_to_specific_value(self):
        settings.set("model", "test-model-xyz:latest")
        brain = FridayBrain(self.signals, self.tts)
        self.assertNotEqual(brain.model, "deepseek-r1:8b")
        self.assertEqual(brain.model, "test-model-xyz:latest")

    def test_settings_listener_updates_brain_model(self):
        settings.set("model", "initial-model:1b")
        brain = FridayBrain(self.signals, self.tts)
        self.assertEqual(brain.model, "initial-model:1b")

        # Simulate user changing model in UI settings
        settings.set("model", "switched-model:9b")
        self.assertEqual(brain.model, "switched-model:9b")
        self.assertEqual(brain.semantic_router.ollama_model, "switched-model:9b")


if __name__ == "__main__":
    unittest.main()
