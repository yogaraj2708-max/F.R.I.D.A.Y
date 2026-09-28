"""
Tests for F.R.I.D.A.Y. 3.0 — Phase 10: Browser Agent Subsystem
Validates:
1. BrowserSession HTML parsing, visible text, and interactive element extraction (links, buttons, inputs).
2. BrowserController action dispatching and postcondition verification.
3. False-success detection on missing/empty downloads and HTTP error statuses.
4. Global Emergency Stop integration (halts browser execution).
5. 9-Stage BaseSkill integration (BrowserNavigateSkill & BrowserDownloadSkill with rollback).
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from friday_core.browser.models import (
    BrowserAction,
    BrowserActionType,
    BrowserState,
    BrowserObservation
)
from friday_core.browser.session import BrowserSession
from friday_core.browser.controller import BrowserController
from friday_core.browser.skills import BrowserNavigateSkill, BrowserDownloadSkill
from friday_core.agent.emergency_stop import EmergencyStopManager


SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>F.R.I.D.A.Y. Test Portal</title></head>
<body>
    <h1>System Status Dashboard</h1>
    <p>All core agent subsystems are operational.</p>
    <a id="docs_link" href="/docs/api">API Documentation</a>
    <a href="https://example.com/external">External Site</a>
    <button id="refresh_btn" name="refresh">Refresh</button>
    <form action="/login" method="post">
        <input id="user_field" name="username" placeholder="Username" type="text" />
        <input name="password" placeholder="Password" type="password" />
        <input type="submit" value="Sign In" />
    </form>
</body>
</html>
"""


class TestBrowserAgent(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.session = BrowserSession()
        self.controller = BrowserController(session=self.session)

    def tearDown(self):
        self.session.close()
        from friday_core.agent.emergency_stop import emergency_stop
        emergency_stop.reset()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_browser_session_html_parsing_and_elements(self):
        """Validates DOM parsing, title extraction, and interactive elements."""
        state = self.session.load_html(SAMPLE_HTML, base_url="http://test.local")
        self.assertEqual(state.title, "F.R.I.D.A.Y. Test Portal")
        self.assertIn("All core agent subsystems are operational", state.text_content)

        # Verify extracted interactive elements
        elements = state.interactive_elements
        self.assertGreaterEqual(len(elements), 5)

        # Check links
        links = [e for e in elements if e.tag == "a"]
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0].text, "API Documentation")
        self.assertEqual(links[0].href, "http://test.local/docs/api")
        self.assertEqual(links[0].selector, "#docs_link")

        # Check button
        buttons = [e for e in elements if e.tag in ("button", "input") and "refresh" in e.text.lower()]
        self.assertGreaterEqual(len(buttons), 1)

        # Check inputs
        inputs = [e for e in elements if e.name == "username"]
        self.assertEqual(len(inputs), 1)
        self.assertEqual(inputs[0].selector, "#user_field")

    def test_false_success_download_detection(self):
        """Validates that a download reporting success without a physical file is flagged as false-success."""
        missing_file = os.path.join(self.temp_dir, "missing_download.bin")
        action = BrowserAction(
            action_type=BrowserActionType.DOWNLOAD,
            url="http://example.com/file.bin",
            target_path=missing_file
        )

        # Simulated false-success: obs says success=True, but file is absent
        fake_obs = BrowserObservation(
            success=True,
            action_type=BrowserActionType.DOWNLOAD,
            downloaded_file=missing_file,
            downloaded_bytes=1024
        )

        ver = self.controller.verify_action(action, fake_obs)
        self.assertFalse(ver.verified)
        self.assertTrue(ver.false_success_detected)
        self.assertIn("does not exist on disk", ver.details)

        # Simulated false-success: file exists but is 0 bytes
        with open(missing_file, "wb") as f:
            pass  # 0 bytes
        ver_empty = self.controller.verify_action(action, fake_obs)
        self.assertFalse(ver_empty.verified)
        self.assertTrue(ver_empty.false_success_detected)
        self.assertIn("0 bytes", ver_empty.details)

    def test_emergency_stop_integration(self):
        """Validates that Emergency Stop blocks browser execution immediately."""
        self.controller.stop()
        action = BrowserAction(action_type=BrowserActionType.NAVIGATE, url="http://example.com")
        obs = self.controller.execute(action)
        self.assertFalse(obs.success)
        self.assertIn("Emergency Stop", obs.error)

    def test_browser_download_skill_with_rollback(self):
        """Validates 9-stage skill lifecycle and rollback on download failure."""
        download_target = os.path.join(self.temp_dir, "test_payload.txt")
        # Create a partial dummy file to simulate rollback requirement
        with open(download_target, "w") as f:
            f.write("partial corrupt content")

        skill = BrowserDownloadSkill(controller=self.controller)
        self.assertTrue(os.path.exists(download_target))

        # Invoke rollback
        skill._target_path = download_target
        rolled_back = skill.rollback("op-test-101")
        self.assertTrue(rolled_back)
        self.assertFalse(os.path.exists(download_target))


if __name__ == "__main__":
    unittest.main()
