"""
Section M: FAILURE-INJECTION TESTING (Zero-Trust Truthful Failure)
Verifies that all subsystem failures result in truthful failure reports and NEVER fake recovery or fabricated success.
Failure injection points:
1. Save path unwritable/invalid
2. App termination on non-existent app
3. UI focus on non-existent window
4. UI typing on non-existent app
5. Screenshot on unwritable path
6. Corrupted PDF document extraction
7. Network connection refusal on dead port
"""

import unittest
import asyncio
import os
from unittest.mock import MagicMock

from friday_ui.core.engine import FridayBrain, FridaySignals
from friday_core.skills.registry import skill_registry


class TestFailureInjectionResilience(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signals = FridaySignals()
        cls.mock_tts = MagicMock()
        cls.mock_tts.is_available.return_value = False
        cls.mock_tts.cancel_event.is_set.return_value = False
        cls.mock_tts.stop_speaking = MagicMock()
        cls.brain = FridayBrain(cls.signals, cls.mock_tts)

    def test_failure1_invalid_save_path(self):
        """Save file to an impossible drive/path must report failure, not success."""
        res = skill_registry.execute_skill(
            tool_id="save_file",
            params={"app_name": "notepad", "filename": "Z:\\nonexistent_drive_999\\bad.txt"},
            operation_id="fail-save-001"
        )
        self.assertFalse(res.success, "Invalid drive save should fail.")
        self.assertIsNotNone(res.error)
        self.assertFalse(os.path.exists("Z:\\nonexistent_drive_999\\bad.txt"))

    def test_failure2_close_protected_system_process(self):
        """Attempting to close a protected Windows core process must be rejected with failure."""
        from friday_core.gatekeeper import gatekeeper, ActionIntent
        res = gatekeeper.execute_action(ActionIntent(action="close_app", target="csrss"))
        self.assertFalse(res.success, "Closing protected system process must fail.")
        self.assertTrue("protected windows core process" in res.message.lower() or "security violation" in res.message.lower())

    def test_failure3_ui_focus_nonexistent_window(self):
        """Focusing an unavailable window must fail precondition and postcondition verification."""
        res = skill_registry.execute_skill(
            tool_id="ui_focus",
            params={"app_name": "ghost_window_imaginary_xyz_999"},
            operation_id="fail-focus-001"
        )
        self.assertFalse(res.success, "Focusing non-existent window should fail.")
        self.assertTrue("precondition" in str(res.error).lower() or "not found" in str(res.error).lower())

    def test_failure4_ui_typing_nonexistent_app(self):
        """Typing into a non-existent app must report failure, not claim text was typed."""
        res = skill_registry.execute_skill(
            tool_id="ui_type_text",
            params={"app_name": "ghost_app_12345", "text": "hello ghost", "mode": "type"},
            operation_id="fail-type-001"
        )
        self.assertFalse(res.success, "Typing into non-existent app should fail.")
        self.assertTrue("precondition" in str(res.error).lower() or "not found" in str(res.error).lower())

    def test_failure5_screenshot_invalid_directory(self):
        """Screenshot to an uncreatable directory must report failure, not claim path exists."""
        res = skill_registry.execute_skill(
            tool_id="screenshot",
            params={"target_dir": "Z:\\completely_impossible_dir_999\\"},
            operation_id="fail-shot-001"
        )
        self.assertFalse(res.success, "Screenshot to impossible dir should fail.")
        self.assertIsNotNone(res.error)

    def test_failure6_corrupted_pdf_document(self):
        """Corrupted PDF must return a truthful read error, never hallucinate a title."""
        corrupt_path = os.path.abspath("scratch/corrupt_injection_test.pdf")
        os.makedirs(os.path.dirname(corrupt_path), exist_ok=True)
        with open(corrupt_path, "wb") as f:
            f.write(b"%PDF-1.4\n%Invalid Corrupted Garbage Bytes 0xDEADBEEF\n%%EOF")

        try:
            cmd = f"what is the title of the pdf at '{corrupt_path}'"
            res = asyncio.run(self.brain.execute_smart_skill(cmd))
            self.assertIsNotNone(res)
            # Must report read failure or inability to verify, NEVER fabricate a title
            self.assertTrue(
                "could not read pdf" in res.lower() or "couldn't verify" in res.lower() or "error" in res.lower(),
                f"Expected truthful error for corrupt PDF, got: {res}"
            )
            self.assertNotIn("Architecture Guide", res)
        finally:
            if os.path.exists(corrupt_path):
                os.remove(corrupt_path)

    def test_failure7_dead_network_port(self):
        """Connection to closed port must report retrieval failure, never pretend content exists."""
        cmd = "read http://127.0.0.1:59995"
        res = asyncio.run(self.brain.execute_smart_skill(cmd))
        self.assertIsNotNone(res)
        self.assertTrue(
            res.startswith("⚠️ Webpage retrieval failed"),
            f"Expected truthful network error, got: {res}"
        )


if __name__ == "__main__":
    unittest.main()
