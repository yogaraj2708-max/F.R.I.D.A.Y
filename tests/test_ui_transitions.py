import unittest
from PySide6.QtWidgets import QApplication
from friday_ui.views.main_window import FridayMainWindow

class TestUITransitions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication([])

    def test_view_switching_preserves_chat_controls(self):
        window = FridayMainWindow()
        window.resize(1100, 750)
        window.show()
        self.app.processEvents()

        # Verify initial presence
        header = window.chat_view.findChild(window.chat_view.__class__, "fridayHeader")
        input_box = window.chat_view.findChild(window.chat_view.__class__, "fridayInput")

        self.assertTrue(window.chat_view.isVisible())

        # Switch to Deep Research
        window.switchTo(window.research_view)
        self.app.processEvents()
        self.assertTrue(window.research_view.isVisible())

        # Switch back to Tactical Chat
        window.switchTo(window.chat_view)
        self.app.processEvents()
        self.assertTrue(window.chat_view.isVisible())

        # Verify header and input remain attached and properly visible
        self.assertIsNone(window.chat_view.graphicsEffect(), "ChatView should not retain conflicting QGraphicsOpacityEffect")
        window.close()

if __name__ == "__main__":
    unittest.main()
