"""
Tests for Folder Organization Target Resolution and Microphone Control & Optimization.
"""

import unittest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from PySide6.QtWidgets import QApplication
import sys

from friday_ui.core.engine import FridayBrain, FridaySignals, FridayVoiceLoop
from friday_core.settings import settings


class TestFolderOrganizeAndMic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QApplication.instance():
            cls.app = QApplication(sys.argv)
        else:
            cls.app = QApplication.instance()

    def setUp(self):
        self.signals = FridaySignals()
        self.tts = MagicMock()
        self.tts.speak = AsyncMock()
        self.tts.is_speaking = False
        self.brain = FridayBrain(self.signals, self.tts)
        self.voice_loop = FridayVoiceLoop(self.signals, self.brain, self.tts)

    def test_resolve_target_directory(self):
        # Documents
        doc_dir = self.brain._resolve_target_directory("documents")
        self.assertIsNotNone(doc_dir)
        self.assertTrue(doc_dir.exists())
        self.assertEqual(doc_dir.name, "Documents")

        # Desktop
        desktop_dir = self.brain._resolve_target_directory("desktop")
        self.assertIsNotNone(desktop_dir)
        self.assertTrue(desktop_dir.exists())
        self.assertEqual(desktop_dir.name, "Desktop")

        # Downloads
        dl_dir = self.brain._resolve_target_directory("downloads")
        self.assertIsNotNone(dl_dir)
        self.assertTrue(dl_dir.exists())
        self.assertEqual(dl_dir.name, "Downloads")

    def test_arrange_documents_skill_targeting(self):
        # User prompt: "arrange my documents folder"
        executed_skills = []
        self.signals.skill_executed.connect(lambda name, detail: executed_skills.append((name, detail)))

        res = asyncio.run(self.brain.execute_smart_skill("arrange my documents folder"))
        self.assertIsNotNone(res)
        # Verify it specifically targeted Documents, NOT Downloads!
        self.assertIn("Documents", res)
        self.assertNotIn("Directory 'Downloads'", res)

        # Verify the emitted skill telemetry specifies Documents
        self.assertTrue(any("Documents" in detail for _, detail in executed_skills))

    def test_mic_loop_stop_and_reset(self):
        self.voice_loop.running = True
        self.voice_loop.force_listen = True

        levels = []
        states = []
        self.signals.speech_level_changed.connect(lambda lvl: levels.append(lvl))
        self.signals.state_changed.connect(lambda st: states.append(st))

        self.voice_loop.stop()

        self.assertFalse(self.voice_loop.running)
        self.assertFalse(self.voice_loop.force_listen)
        self.assertIn("idle", states)
        self.assertIn(0.0, levels)

    def test_chat_view_and_command_bar_mic_active_state(self):
        from friday_ui.views.chat_view import ChatView
        from friday_ui.widgets.command_bar import FloatingCommandBar

        chat_view = ChatView()
        command_bar = FloatingCommandBar()

        # Test initial / muted state
        chat_view.set_mic_active(False)
        self.assertIn("Unmute", chat_view.mic_btn.toolTip())

        command_bar.set_mic_active(False)
        self.assertIn("Unmute", command_bar.mic_btn.toolTip())

        # Test active / unmuted state
        chat_view.set_mic_active(True)
        self.assertIn("Mute", chat_view.mic_btn.toolTip())

        command_bar.set_mic_active(True)
        self.assertIn("Mute", command_bar.mic_btn.toolTip())

    def test_attached_document_bypasses_smart_skills(self):
        # When a document is attached (like README.md with 'organize' mentioned inside)
        prompt_with_attachment = (
            "[Attached Document: README.md]\n```md\n### 📂 Autonomous File Organizer & Desktop Copilot\n"
            "Sorts loose desktop files into clean categories\n```\n\nBoss Directive:\nexplain this project"
        )
        res = asyncio.run(self.brain.execute_smart_skill(prompt_with_attachment))
        # Must be None so it flows directly to the LLM
        self.assertIsNone(res)

    def test_questions_do_not_trigger_organize(self):
        # Plain question about organizing should NOT trigger the file organizer skill
        queries = [
            "explain this project",
            "how to organize files",
            "how do I sort a list in python",
            "what is the best way to clean my code",
            "describe how to arrange folders"
        ]
        for q in queries:
            res = asyncio.run(self.brain.execute_smart_skill(q))
            self.assertIsNone(res, f"Query '{q}' should not trigger smart skills")

    def test_actual_organize_commands_trigger_correctly(self):
        res1 = asyncio.run(self.brain.execute_smart_skill("arrange my document folders"))
        self.assertIsNotNone(res1)
        self.assertIn("Documents", res1)

        res2 = asyncio.run(self.brain.execute_smart_skill("clean my desktop"))
        self.assertIsNotNone(res2)
        self.assertTrue("Desktop" in res2 or "clean" in res2)

    def test_command_bar_hotkey_filter_and_safe_toggle(self):
        from friday_ui.widgets.command_bar import FloatingCommandBar, GlobalHotKeyFilter, HOTKEY_ID, WM_HOTKEY
        import ctypes
        from ctypes import wintypes

        bar = FloatingCommandBar()
        bar.hide()
        self.assertFalse(bar.isVisible())

        # Test toggle_visibility
        bar.toggle_visibility()
        self.assertTrue(bar.isVisible())
        bar.toggle_visibility()
        self.assertFalse(bar.isVisible())

        # Test _setup_position resiliency when primaryScreen() is mocked as None
        with patch("PySide6.QtWidgets.QApplication.primaryScreen", return_value=None):
            bar._setup_position()
            self.assertGreaterEqual(bar.x(), 0)
            self.assertGreaterEqual(bar.y(), 0)

        # Test GlobalHotKeyFilter with invalid / null message
        filter_instance = GlobalHotKeyFilter(bar.toggle_visibility)
        handled, ret = filter_instance.nativeEventFilter(b"other_event", None)
        self.assertFalse(handled)

        handled, ret = filter_instance.nativeEventFilter(b"windows_generic_MSG", 0)
        self.assertFalse(handled)

        # Test GlobalHotKeyFilter with simulated WM_HOTKEY message
        fake_msg = wintypes.MSG()
        fake_msg.message = WM_HOTKEY
        fake_msg.wParam = HOTKEY_ID
        msg_ptr = ctypes.addressof(fake_msg)

        with patch("PySide6.QtCore.QTimer.singleShot") as mock_timer:
            handled, ret = filter_instance.nativeEventFilter(b"windows_generic_MSG", msg_ptr)
            self.assertTrue(handled)
            mock_timer.assert_called_once()

    def test_organize_directory_comprehensive_categorization(self):
        import tempfile
        import shutil

        temp_root = Path(tempfile.mkdtemp(prefix="friday_test_root_"))
        temp_dir = temp_root / "Documents"
        temp_dir.mkdir()
        try:
            # Create files
            pdf_file = temp_dir / "research_paper.pdf"
            pdf_file.write_text("sample pdf content")

            doc_file = temp_dir / "report.docx"
            doc_file.write_text("sample docx content")

            shortcut_file = temp_dir / "Recycle Bin.lnk"
            shortcut_file.write_text("sample lnk content")

            misc_file = temp_dir / "data.xyz"
            misc_file.write_text("unknown extension data")

            # Create mock project folder
            proj_folder = temp_dir / "smart-library-system"
            proj_folder.mkdir()
            (proj_folder / ".git").mkdir()
            (proj_folder / "main.py").write_text("print('hello')")

            # Create protected folder
            protected_folder = temp_dir / "jarvis voice"
            protected_folder.mkdir()
            (protected_folder / "workspace.txt").write_text("workspace")

            # Patch _resolve_target_directory to return this temp_dir named "Documents"
            with patch.object(self.brain, "_resolve_target_directory", return_value=temp_dir), \
                 patch("friday_ui.core.engine.gatekeeper.execute_action", return_value=MagicMock(success=True)):
                res = asyncio.run(self.brain.organize_directory("documents"))

            self.assertIn("Successfully organized", res)

            # Check moved files
            self.assertTrue((temp_dir / "PDFs & Text" / "research_paper.pdf").exists())
            self.assertTrue((temp_dir / "Word" / "report.docx").exists())
            self.assertTrue((temp_dir / "Shortcuts" / "Recycle Bin.lnk").exists())
            self.assertTrue((temp_dir / "Miscellaneous" / "data.xyz").exists())

            # Check moved project folder
            self.assertTrue((temp_dir / "Projects" / "smart-library-system").exists())

            # Check protected folder was NOT moved
            self.assertTrue((temp_dir / "jarvis voice").exists())
            self.assertFalse((temp_dir / "Projects" / "jarvis voice").exists())

        finally:
            shutil.rmtree(str(temp_root), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
