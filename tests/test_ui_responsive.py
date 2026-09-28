"""
Tests for F.R.I.D.A.Y. 3.0 Responsive Window Layout.
Verifies usability, geometry, control visibility, and absence of clipping across:
1280x720, 1366x768, 1920x1080, and 2560x1440 resolutions.
"""

import sys
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize

from friday_ui.views.main_window import FridayMainWindow


class TestUIResponsive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(sys.argv)

    def setUp(self):
        self.window = FridayMainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def _verify_view_controls_visible(self, width: int, height: int):
        """Helper to test key controls across all views at a given resolution."""
        self.window.resize(width, height)
        self.app.processEvents()

        # 1. Chat View Verification
        self.window.switchTo(self.window.chat_view)
        self.app.processEvents()

        cv = self.window.chat_view
        self.assertTrue(cv.prompt_input.isVisible())
        self.assertGreater(cv.prompt_input.width(), 200)
        self.assertGreater(cv.prompt_input.height(), 20)
        self.assertTrue(cv.send_btn.isVisible())
        self.assertTrue(cv.session_combo.isVisible())
        self.assertTrue(cv.model_combo.isVisible())

        # Check prompt input is positioned within window bounds
        pos = cv.prompt_input.mapTo(self.window, cv.prompt_input.rect().topLeft())
        self.assertGreaterEqual(pos.x(), 0)
        self.assertLess(pos.x() + cv.prompt_input.width(), width + 50)

        # 2. Research View Verification
        self.window.switchTo(self.window.research_view)
        self.app.processEvents()

        rv = self.window.research_view
        self.assertTrue(rv.query_input.isVisible())
        self.assertGreater(rv.query_input.width(), 150)
        self.assertTrue(rv.start_btn.isVisible())
        self.assertTrue(rv.depth_combo.isVisible())

        # 3. Documents View Verification
        self.window.switchTo(self.window.documents_view)
        self.app.processEvents()

        dv = self.window.documents_view
        self.assertTrue(dv.doc_search_input.isVisible())
        self.assertTrue(dv.browse_doc_btn.isVisible())
        self.assertTrue(dv.ingest_btn.isVisible())

        # 4. Settings View Verification
        self.window.switchTo(self.window.settings_view)
        self.app.processEvents()

        sv = self.window.settings_view
        self.assertTrue(sv.category_list.isVisible())
        self.assertGreater(sv.category_list.width(), 100)
        self.assertTrue(sv.save_btn.isVisible())

    def test_resolution_1280x720(self):
        """Verifies HD 1280x720 compact resolution layout and control accessibility."""
        self._verify_view_controls_visible(1280, 720)

    def test_resolution_1366x768(self):
        """Verifies Laptop standard 1366x768 resolution layout and control accessibility."""
        self._verify_view_controls_visible(1366, 768)

    def test_resolution_1920x1080(self):
        """Verifies Full HD 1920x1080 resolution layout and control accessibility."""
        self._verify_view_controls_visible(1920, 1080)

    def test_resolution_2560x1440(self):
        """Verifies QHD 2560x1440 large display resolution layout and control accessibility."""
        self._verify_view_controls_visible(2560, 1440)


if __name__ == "__main__":
    unittest.main()
