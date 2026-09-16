"""
Tests for Dynamic Owner Identity & AI Model Management in F.R.I.D.A.Y. 2.0
Verifies dynamic username resolution, title customization, custom model addition, and dynamic persona.
"""

import sys
import unittest
from PySide6.QtWidgets import QApplication
from friday_core.settings import settings, get_default_owner_name
from friday_ui.widgets.chat_bubble import ChatBubble

app = QApplication.instance() or QApplication(sys.argv)

class TestIdentityAndModels(unittest.TestCase):
    def setUp(self):
        self.orig_name = settings.get("user_name")
        self.orig_title = settings.get("user_title")
        self.orig_model = settings.get("model")
        self.orig_custom = settings.get("custom_models", [])

    def tearDown(self):
        settings.set("user_name", self.orig_name, auto_save=False)
        settings.set("user_title", self.orig_title, auto_save=False)
        settings.set("model", self.orig_model, auto_save=False)
        settings.set("custom_models", self.orig_custom, auto_save=False)

    def test_default_owner_name_detection(self):
        name = get_default_owner_name()
        self.assertIsInstance(name, str)
        self.assertGreater(len(name), 0)

    def test_owner_identity_persistence(self):
        settings.set("user_name", "Alphin Andrew", auto_save=False)
        settings.set("user_title", "Commander", auto_save=False)
        self.assertEqual(settings.get("user_name"), "Alphin Andrew")
        self.assertEqual(settings.get("user_title"), "Commander")

    def test_chat_bubble_dynamic_badge(self):
        # Case 1: Title Commander, Name Renit
        settings.set("user_name", "Renit", auto_save=False)
        settings.set("user_title", "Commander", auto_save=False)
        bubble = ChatBubble("user", "System status report.")
        self.assertIn("COMMANDER (RENIT)", bubble.badge.text())

        # Case 2: Title None, Name Alex
        settings.set("user_name", "Alex", auto_save=False)
        settings.set("user_title", "None", auto_save=False)
        bubble2 = ChatBubble("user", "Hello Friday.")
        self.assertEqual(bubble2.badge.text(), "ALEX")

    def test_get_available_models(self):
        models = settings.get_available_models()
        self.assertIsInstance(models, list)
        self.assertGreater(len(models), 0)
        # Should include common fallback models if Ollama offline
        self.assertTrue(any("llama3" in m or "qwen" in m or "friday" in m for m in models))

    def test_add_custom_model(self):
        test_model = "test-neural-model:3b"
        added = settings.add_custom_model(test_model)
        self.assertTrue(added or test_model in settings.get("custom_models"))
        models = settings.get_available_models()
        self.assertIn(test_model, models)

if __name__ == "__main__":
    unittest.main()
