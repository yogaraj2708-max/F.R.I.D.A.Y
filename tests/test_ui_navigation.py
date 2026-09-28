"""
Tests for F.R.I.D.A.Y. 3.0 UI Navigation.
Verifies seamless switching across Chat, Research, Files & Documents, and Settings views.
"""

import sys
import unittest
from PySide6.QtWidgets import QApplication

from friday_ui.views.main_window import FridayMainWindow


class TestUINavigation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)

    def setUp(self):
        self.window = FridayMainWindow()
        self.window.resize(1100, 750)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_default_view_is_chat(self):
        """Verifies initial view defaults to ChatView."""
        self.assertTrue(self.window.chat_view.isVisible())

    def test_switch_to_research_view(self):
        """Verifies navigation to Deep Research view."""
        self.window.switchTo(self.window.research_view)
        self.app.processEvents()
        self.assertTrue(self.window.research_view.isVisible())

    def test_switch_to_documents_view(self):
        """Verifies navigation to Files & Documents view."""
        self.window.switchTo(self.window.documents_view)
        self.app.processEvents()
        self.assertTrue(self.window.documents_view.isVisible())

    def test_switch_to_settings_view(self):
        """Verifies navigation to Settings view."""
        self.window.switchTo(self.window.settings_view)
        self.app.processEvents()
        self.assertTrue(self.window.settings_view.isVisible())

    def test_full_navigation_cycle_preserves_state(self):
        """Verifies cycling across all views restores chat controls without conflict."""
        # 1. Chat
        self.assertTrue(self.window.chat_view.isVisible())

        # 2. Research
        self.window.switchTo(self.window.research_view)
        self.app.processEvents()
        self.assertTrue(self.window.research_view.isVisible())

        # 3. Documents
        self.window.switchTo(self.window.documents_view)
        self.app.processEvents()
        self.assertTrue(self.window.documents_view.isVisible())

        # 4. Settings
        self.window.switchTo(self.window.settings_view)
        self.app.processEvents()
        self.assertTrue(self.window.settings_view.isVisible())

        # 5. Back to Chat
        self.window.switchTo(self.window.chat_view)
        self.app.processEvents()
        self.assertTrue(self.window.chat_view.isVisible())
        self.assertIsNone(self.window.chat_view.graphicsEffect())


if __name__ == "__main__":
    unittest.main()
