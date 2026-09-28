"""
Tests for F.R.I.D.A.Y. 3.0 Phase 6 — Windows UI Automation & Hierarchy (6A-6F)
Verifies:
1. Strict 5-tier automation priority hierarchy.
2. Phase 6A Semantic UIA pattern invocation and postcondition readback verification.
3. Phase 6B Application Shortcuts dispatch and key mapping.
4. Bounded input bounds validation and rejection of unverified coordinates.
5. AutomationDispatcher priority execution order and fallback chaining.
"""

import unittest
from unittest.mock import MagicMock, patch

from friday_core.automation.hierarchy import AutomationPriority, AutomationOutcome
from friday_core.automation.uia import UIAutomationDriver
from friday_core.automation.shortcuts import ShortcutDriver
from friday_core.automation.mouse_keyboard import BoundedInputDriver
from friday_core.automation.dispatcher import AutomationDispatcher


class TestUIAutomationHierarchy(unittest.TestCase):
    def setUp(self):
        self.mock_uia = MagicMock(spec=UIAutomationDriver)
        self.mock_shortcuts = MagicMock(spec=ShortcutDriver)
        self.mock_input = MagicMock(spec=BoundedInputDriver)

        self.dispatcher = AutomationDispatcher(
            uia=self.mock_uia,
            shortcuts=self.mock_shortcuts,
            input_drv=self.mock_input
        )

    # 1. Hierarchy Policy Verification
    def test_priority_ordering(self):
        """Enforces mandatory priority: Semantic UIA -> Shortcuts -> Bounded Input -> Vision -> Coordinates."""
        self.assertLess(AutomationPriority.SEMANTIC_UIA, AutomationPriority.APPLICATION_SHORTCUTS)
        self.assertLess(AutomationPriority.APPLICATION_SHORTCUTS, AutomationPriority.BOUNDED_INPUT)
        self.assertLess(AutomationPriority.BOUNDED_INPUT, AutomationPriority.VISION)
        self.assertLess(AutomationPriority.VISION, AutomationPriority.COORDINATES_FALLBACK)

    # 2. Phase 6A: Semantic UIA Verification
    def test_uia_postcondition_readback_verification(self):
        driver = UIAutomationDriver()
        driver.available = True

        # Mock control with ValuePattern
        mock_ctrl = MagicMock()
        mock_val_pattern = MagicMock()
        mock_val_pattern.Value = "Expected Text"
        mock_ctrl.GetValuePattern.return_value = mock_val_pattern

        with patch.object(driver, "find_control", return_value=mock_ctrl):
            # When readback matches
            success, msg = driver.set_control_value("SearchBox", "Expected Text")
            self.assertTrue(success)
            self.assertIn("verified readback", msg)

            # False-success detection: when readback diverges
            mock_val_pattern.Value = "Different Value"
            fail_success, fail_msg = driver.set_control_value("SearchBox", "Expected Text")
            self.assertFalse(fail_success)
            self.assertIn("Postcondition failed", fail_msg)

    # 3. Phase 6B: Shortcuts Verification
    def test_shortcuts_key_mapping(self):
        driver = ShortcutDriver()
        with patch("ctypes.windll.user32.keybd_event"):
            # Known shortcut
            success, msg = driver.send_shortcut("save")
            self.assertTrue(success)
            self.assertIn("Dispatched shortcut 'save'", msg)

            # Unknown shortcut
            fail_success, fail_msg = driver.send_shortcut("invalid_key_xyz")
            self.assertFalse(fail_success)
            self.assertIn("Unknown key", fail_msg)

    # 4. Bounded Input Validation
    def test_bounded_input_rejects_invalid_bounds(self):
        driver = BoundedInputDriver()
        # Invalid rect: right <= left
        success, msg = driver.click_within_bounds((100, 100, 50, 200))
        self.assertFalse(success)
        self.assertIn("Invalid bounding rectangle", msg)

        # Valid rect
        with patch("ctypes.windll.user32.SetCursorPos") as mock_set:
            with patch("ctypes.windll.user32.mouse_event") as mock_mouse:
                val_success, val_msg = driver.click_within_bounds((100, 100, 300, 200))
                self.assertTrue(val_success)
                mock_set.assert_called_with(200, 150)
                self.assertIn("Clicked within verified bounding rect", val_msg)

    # 5. Dispatcher Hierarchy Execution
    def test_dispatcher_favors_semantic_uia(self):
        """When Semantic UIA succeeds, dispatcher does not fall through to shortcuts or coordinates."""
        self.mock_uia.available = True
        self.mock_uia.click_control.return_value = (True, "Invoked via UIA")

        outcome = self.dispatcher.click("SubmitButton")
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.priority_level, AutomationPriority.SEMANTIC_UIA)
        self.assertEqual(outcome.level_name, "SEMANTIC_UIA")
        self.mock_shortcuts.send_shortcut.assert_not_called()
        self.mock_input.click_within_bounds.assert_not_called()

    def test_dispatcher_falls_back_to_shortcuts(self):
        """When UIA fails, dispatcher falls back to standard application shortcuts."""
        self.mock_uia.available = True
        self.mock_uia.click_control.return_value = (False, "Not found")
        self.mock_shortcuts.send_shortcut.return_value = (True, "Shortcut sent")

        outcome = self.dispatcher.click("save")
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.priority_level, AutomationPriority.APPLICATION_SHORTCUTS)
        self.mock_shortcuts.send_shortcut.assert_called_with("save")

    def test_dispatcher_exhausted_hierarchy(self):
        """When all layers fail, reports failure without blind coordinate clicking."""
        self.mock_uia.available = True
        self.mock_uia.click_control.return_value = (False, "Not found")
        self.mock_uia.find_control.return_value = None

        outcome = self.dispatcher.click("NonExistentButton")
        self.assertFalse(outcome.success)
        self.assertEqual(outcome.level_name, "EXHAUSTED_HIERARCHY")


if __name__ == "__main__":
    unittest.main()
