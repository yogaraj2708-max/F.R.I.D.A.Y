"""
Tests for F.R.I.D.A.Y. 3.0 Accessibility & Automation Identifiers.
Verifies stable objectNames and accessibleNames on all primary interactive controls.
"""

import sys
import unittest
from PySide6.QtWidgets import QApplication

from friday_ui.views.main_window import FridayMainWindow


class TestUIAccessibility(unittest.TestCase):
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

    def test_chat_controls_accessibility(self):
        """Verifies stable identifiers and accessible names on ChatView controls."""
        cv = self.window.chat_view

        self.assertEqual(cv.prompt_input.objectName(), "chat_input")
        self.assertTrue(bool(cv.prompt_input.accessibleName()))

        self.assertEqual(cv.send_btn.objectName(), "send_button")
        self.assertTrue(bool(cv.send_btn.accessibleName()))

        self.assertEqual(cv.stop_btn.objectName(), "stop_button")
        self.assertTrue(bool(cv.stop_btn.accessibleName()))

        self.assertEqual(cv.mic_btn.objectName(), "mic_button")
        self.assertTrue(bool(cv.mic_btn.accessibleName()))

        self.assertEqual(cv.attach_btn.objectName(), "attachment_button")
        self.assertTrue(bool(cv.attach_btn.accessibleName()))

        self.assertEqual(cv.model_combo.objectName(), "model_selector")
        self.assertTrue(bool(cv.model_combo.accessibleName()))

        self.assertEqual(cv.session_combo.objectName(), "session_selector")
        self.assertTrue(bool(cv.session_combo.accessibleName()))

    def test_research_controls_accessibility(self):
        """Verifies stable identifiers and accessible names on ResearchView controls."""
        rv = self.window.research_view

        self.assertEqual(rv.query_input.objectName(), "research_input")
        self.assertTrue(bool(rv.query_input.accessibleName()))

        self.assertEqual(rv.start_btn.objectName(), "research_start_button")
        self.assertTrue(bool(rv.start_btn.accessibleName()))

        self.assertEqual(rv.stop_btn.objectName(), "research_stop_button")
        self.assertTrue(bool(rv.stop_btn.accessibleName()))

        self.assertEqual(rv.depth_combo.objectName(), "research_depth_combo")
        self.assertTrue(bool(rv.depth_combo.accessibleName()))

    def test_documents_controls_accessibility(self):
        """Verifies stable identifiers and accessible names on DocumentsView controls."""
        dv = self.window.documents_view

        self.assertEqual(dv.doc_search_input.objectName(), "doc_search_input")
        self.assertTrue(bool(dv.doc_search_input.accessibleName()))

        self.assertEqual(dv.browse_btn.objectName(), "browse_doc_btn")
        self.assertTrue(bool(dv.browse_btn.accessibleName()))

        self.assertEqual(dv.ingest_btn.objectName(), "ingest_btn")
        self.assertTrue(bool(dv.ingest_btn.accessibleName()))

        self.assertEqual(dv.search_btn.objectName(), "search_btn")
        self.assertTrue(bool(dv.search_btn.accessibleName()))

    def test_settings_controls_accessibility(self):
        """Verifies stable identifiers and accessible names on SettingsView controls."""
        sv = self.window.settings_view

        self.assertEqual(sv.owner_name_input.objectName(), "owner_name_input")
        self.assertTrue(bool(sv.owner_name_input.accessibleName()))

        self.assertEqual(sv.title_combo.objectName(), "title_combo")
        self.assertTrue(bool(sv.title_combo.accessibleName()))

        self.assertEqual(sv.model_combo.objectName(), "model_selector_settings")
        self.assertTrue(bool(sv.model_combo.accessibleName()))

        self.assertEqual(sv.save_btn.objectName(), "save_settings_btn")
        self.assertTrue(bool(sv.save_btn.accessibleName()))

    def test_hud_dock_accessibility(self):
        """Verifies stable identifiers and accessible names on HUD dock controls."""
        hud = self.window.hud_dock

        self.assertEqual(hud.hud_state_label.objectName(), "hudStateLabel")
        self.assertTrue(bool(hud.hud_state_label.accessibleName()))

        self.assertEqual(hud.telemetry_label.objectName(), "hudTelemetryLabel")
        self.assertTrue(bool(hud.telemetry_label.accessibleName()))

        self.assertEqual(hud.stop_voice_btn.objectName(), "stop_voice_button")
        self.assertTrue(bool(hud.stop_voice_btn.accessibleName()))


if __name__ == "__main__":
    unittest.main()
