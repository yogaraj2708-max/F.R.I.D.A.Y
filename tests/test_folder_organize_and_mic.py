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


if __name__ == "__main__":
    unittest.main()
