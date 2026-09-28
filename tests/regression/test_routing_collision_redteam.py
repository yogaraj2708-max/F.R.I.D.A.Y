"""
Section L: ROUTING COLLISION RED TEAM
Adversarial pairs test matrix:
1. PDF Question vs Telemetry
2. Typing vs Informational Question
3. Mute vs Increase Volume (Opposite Action Safety)
4. Save File vs General Chat Question
5. Webpage Reading vs General Knowledge Question
6. App Command vs Historical/Conceptual Question
7. Deep Research vs Casual Chat
"""

import unittest
import asyncio
from unittest.mock import MagicMock, patch

from friday_ui.core.engine import FridayBrain, FridaySignals
from friday_core.router.semantic_router import SkillIntent


class TestRoutingCollisionRedTeam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signals = FridaySignals()
        cls.mock_tts = MagicMock()
        cls.mock_tts.is_available.return_value = False
        cls.mock_tts.cancel_event.is_set.return_value = False
        cls.mock_tts.stop_speaking = MagicMock()
        cls.brain = FridayBrain(cls.signals, cls.mock_tts)

    def test_pair1_pdf_vs_telemetry(self):
        """Document questions must NOT trigger hardware telemetry sensors."""
        # 1. Real PDF question
        pdf_q = "what is the first sentence of this pdf"
        res_pdf = asyncio.run(self.brain.execute_smart_skill(pdf_q))
        # Even without active PDF, should report PDF absence, never system battery
        self.assertIsNotNone(res_pdf)
        self.assertNotIn("Battery is holding", res_pdf)
        self.assertNotIn("System memory load", res_pdf)

        # 2. Real Telemetry question
        telem_q = "how much battery is left"
        res_telem = asyncio.run(self.brain.execute_smart_skill(telem_q))
        self.assertIsNotNone(res_telem)
        self.assertTrue(
            "battery" in res_telem.lower() or "power" in res_telem.lower() or "systems running" in res_telem.lower()
        )

    def test_pair2_typing_vs_informational_question(self):
        """Informational questions containing the word 'type' must NOT trigger UI typing."""
        info_questions = [
            "what type of file is a pdf",
            "what type of operating system is windows 11",
            "how do I type in python",
            "type of algorithm used in binary search?"
        ]
        for q in info_questions:
            res = asyncio.run(self.brain.execute_smart_skill(q))
            # Must return None (bypassing smart skills to reach general LLM)
            self.assertIsNone(res, f"Informational question '{q}' was incorrectly captured by typing skill!")

    def test_pair3_mute_vs_increase_opposite_safety(self):
        """Opposite action safety: 'mute' must NEVER increase volume; 'increase' must NEVER mute."""
        with patch("friday_core.gatekeeper.gatekeeper.gatekeeper.execute_action", return_value=MagicMock(success=True)) as mock_gk:
            # Test mute
            res_mute = asyncio.run(self.brain.execute_smart_skill("mute volume"))
            self.assertIsNotNone(res_mute)
            self.assertIn("muted", res_mute.lower())
            self.assertNotIn("increased", res_mute.lower())

            # Test increase
            res_up = asyncio.run(self.brain.execute_smart_skill("increase volume"))
            self.assertIsNotNone(res_up)
            self.assertIn("increased", res_up.lower())
            self.assertNotIn("muted", res_up.lower())

    def test_pair4_save_file_vs_general_chat(self):
        """Questions about saving must NOT execute file saving on physical disk."""
        chat_questions = [
            "how to save a file in python",
            "how do you save a file in notepad",
            "explain how to save data to a database"
        ]
        for q in chat_questions:
            res = asyncio.run(self.brain.execute_smart_skill(q))
            self.assertIsNone(res, f"Question '{q}' was falsely executed as save_file skill!")

    def test_pair5_webpage_reading_vs_general_knowledge(self):
        """Questions about the web without a URL must NOT trigger webpage fetch."""
        general_web_questions = [
            "who invented the world wide web",
            "how does http protocol work",
            "explain what a webpage is"
        ]
        for q in general_web_questions:
            res = asyncio.run(self.brain.execute_smart_skill(q))
            self.assertIsNone(res, f"General web question '{q}' was falsely executed as web reading!")

    def test_pair6_app_command_vs_conceptual_question(self):
        """Historical/conceptual questions using verbs like 'close' must NOT kill processes."""
        conceptual_questions = [
            "why did internet explorer close",
            "why did microsoft shut down windows mobile",
            "explain how to close a socket connection in c++"
        ]
        for q in conceptual_questions:
            res = asyncio.run(self.brain.execute_smart_skill(q))
            self.assertIsNone(res, f"Conceptual question '{q}' was falsely executed as close_app skill!")

    def test_pair7_research_vs_casual_chat(self):
        """Conversational banter mentioning research must NOT trigger full Deep Research."""
        chat_queries = [
            "what is your favorite topic to research",
            "tell me a joke about research scientists"
        ]
        for q in chat_queries:
            res = asyncio.run(self.brain.execute_smart_skill(q))
            self.assertIsNone(res, f"Casual chat '{q}' was falsely routed to deep research!")


if __name__ == "__main__":
    unittest.main()
