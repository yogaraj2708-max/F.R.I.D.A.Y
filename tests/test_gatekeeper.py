"""
Tests for friday_core.gatekeeper (Security Action Gatekeeper)
Verifies 4-tier security, panic switch, path fencing, rate limiting, and confirmation workflows.
"""

import os
import unittest
from pathlib import Path
from friday_core.gatekeeper.models import ActionIntent, ActionResult
from friday_core.gatekeeper.gatekeeper import ActionGatekeeper
from friday_core.settings import settings, APP_DATA_DIR

class TestActionGatekeeper(unittest.TestCase):
    def setUp(self):
        self.gk = ActionGatekeeper()
        # Reset panic switch
        settings.set("observe_only", False)

    def tearDown(self):
        settings.set("observe_only", False)

    def test_tier_classification(self):
        self.assertEqual(self.gk.classify_tier(ActionIntent("get_telemetry")), 0)
        self.assertEqual(self.gk.classify_tier(ActionIntent("calculate")), 0)
        self.assertEqual(self.gk.classify_tier(ActionIntent("open_app", target="notepad")), 1)
        self.assertEqual(self.gk.classify_tier(ActionIntent("adjust_volume", target="up")), 1)
        self.assertEqual(self.gk.classify_tier(ActionIntent("delete_file", target="test.txt")), 2)
        self.assertEqual(self.gk.classify_tier(ActionIntent("kill_process", target="calc")), 2)
        self.assertEqual(self.gk.classify_tier(ActionIntent("format_drive")), 3)

    def test_tier2_requires_confirmation_unconfirmed(self):
        intent = ActionIntent(action="delete_file", target="C:/some/file.txt", confirmed=False)
        result = self.gk.execute_action(intent)
        self.assertFalse(result.success)
        self.assertTrue(result.requires_confirmation)
        self.assertIn("Recycle Bin", result.dry_run_text)

    def test_panic_switch_blocks_tier1_and_above(self):
        settings.set("observe_only", True)

        # Tier 0 should still pass
        t0_intent = ActionIntent(action="get_telemetry")
        t0_res = self.gk.execute_action(t0_intent)
        self.assertTrue(t0_res.success)

        # Tier 1 should be blocked
        t1_intent = ActionIntent(action="open_app", target="notepad")
        t1_res = self.gk.execute_action(t1_intent)
        self.assertFalse(t1_res.success)
        self.assertIn("Observe Only", t1_res.message)

        # Tier 2 should be blocked
        t2_intent = ActionIntent(action="delete_file", target="test.txt", confirmed=True)
        t2_res = self.gk.execute_action(t2_intent)
        self.assertFalse(t2_res.success)
        self.assertIn("Observe Only", t2_res.message)

    def test_path_fencing_rejects_traversal(self):
        safe, msg = self.gk.is_path_safe("C:/Users/Admin/Desktop/../Windows/System32/cmd.exe")
        self.assertFalse(safe)
        self.assertIn("traversal", msg.lower())

    def test_path_fencing_safe_desktop_path(self):
        desktop = os.path.expandvars(r"%USERPROFILE%\Desktop")
        test_file = os.path.join(desktop, "friday_safe_test.txt")
        safe, _ = self.gk.is_path_safe(test_file)
        self.assertTrue(safe)

    def test_rate_limiting_destructive_actions(self):
        # 3 actions in 60s is allowed, 4th must be rejected
        self.gk._action_history.clear()
        self.assertTrue(self.gk.check_rate_limit())
        self.assertTrue(self.gk.check_rate_limit())
        self.assertTrue(self.gk.check_rate_limit())
        self.assertFalse(self.gk.check_rate_limit())

    def test_tier3_denied_without_allowlist(self):
        intent = ActionIntent(action="format_drive")
        res = self.gk.execute_action(intent)
        self.assertFalse(res.success)
        self.assertIn("Access Denied", res.message)

if __name__ == "__main__":
    unittest.main()
