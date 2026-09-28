"""
Tests for F.R.I.D.A.Y. 3.0 UI Layout Architecture.
Verifies application shell, primary navigation containers, and view hierarchy.
"""

import sys
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from friday_ui.views.main_window import FridayMainWindow
from friday_ui.views.chat_view import ChatView
from friday_ui.views.research_view import ResearchView
from friday_ui.views.rag_view import DocumentsView
from friday_ui.views.settings_view import SettingsView


class TestUILayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)

    def setUp(self):
        self.window = FridayMainWindow()
        self.window.resize(1200, 800)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_main_window_shell_structure(self):
        """Verifies core window shell and containers exist."""
        self.assertEqual(self.window.objectName(), "FridayMainWindow")
        self.assertIn("F.R.I.D.A.Y.", self.window.windowTitle())
        self.assertIsNotNone(self.window.content_container)
        self.assertIsNotNone(self.window.workspace_container)
        self.assertIsNotNone(self.window.hud_dock)
        self.assertTrue(self.window.hud_dock.isVisible())

    def test_sub_interfaces_registered(self):
        """Verifies all four primary sub-interfaces are created and attached."""
        self.assertIsInstance(self.window.chat_view, ChatView)
        self.assertIsInstance(self.window.research_view, ResearchView)
        self.assertIsInstance(self.window.documents_view, DocumentsView)
        self.assertIsInstance(self.window.settings_view, SettingsView)

        # Check stacked widget contains 4 interfaces
        self.assertGreaterEqual(self.window.stackedWidget.count(), 4)

    def test_chat_view_layout_components(self):
        """Verifies ChatView contains header card, scroll area, and input frame."""
        cv = self.window.chat_view
        self.assertIsNotNone(cv.header_card)
        self.assertIsNotNone(cv.scroll_area)
        self.assertIsNotNone(cv.input_frame)
        self.assertIsNotNone(cv.prompt_input)
        self.assertIsNotNone(cv.send_btn)
        self.assertIsNotNone(cv.mic_btn)
        self.assertIsNotNone(cv.attach_btn)

    def test_research_view_layout_components(self):
        """Verifies ResearchView contains command bar, progress bar, and report viewer."""
        rv = self.window.research_view
        self.assertIsNotNone(rv.query_input)
        self.assertIsNotNone(rv.depth_combo)
        self.assertIsNotNone(rv.start_btn)
        self.assertIsNotNone(rv.progress_bar)
        self.assertIsNotNone(rv.report_browser)
        self.assertIsNotNone(rv.sources_container)

    def test_documents_view_layout_components(self):
        """Verifies DocumentsView contains left list card and right preview card."""
        dv = self.window.documents_view
        self.assertIsNotNone(dv.doc_search_input)
        self.assertIsNotNone(dv.doc_list)
        self.assertIsNotNone(dv.preview_browser)
        self.assertIsNotNone(dv.search_input)
        self.assertIsNotNone(dv.search_btn)
        self.assertIsNotNone(dv.ingest_btn)

    def test_settings_view_layout_components(self):
        """Verifies SettingsView contains category list and stacked panes."""
        sv = self.window.settings_view
        self.assertIsNotNone(sv.category_list)
        self.assertIsNotNone(sv.stacked_panes)
        self.assertGreaterEqual(sv.category_list.count(), 6)
        self.assertGreaterEqual(sv.stacked_panes.count(), 6)


if __name__ == "__main__":
    unittest.main()
