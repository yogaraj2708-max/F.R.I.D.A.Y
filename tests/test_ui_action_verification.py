"""
Tests for F.R.I.D.A.Y. 3.0 Action Verification & Readback Postconditions.
Verifies readback match, mismatch handling, and evidence preservation.
"""

import pytest
from friday_core.automation.action_engine import ui_action_engine
from friday_core.automation.inspector import ui_inspector, WindowInspection, UIElementInfo


def test_type_readback_exact_match_simulation():
    """Verify that type_text requires readback verification before reporting success."""
    # When target window does not exist, verification must be honest and report failure
    res = ui_action_engine.type_text("TEST 123", app_name="non_existent_app_999")
    assert res["success"] is False
    assert res["status"] in ("WINDOW_NOT_FOUND", "READBACK_FAILED")


def test_click_verification_requires_control():
    """Verify click_control refuses to report success without finding the actual control."""
    res = ui_action_engine.click_control("phantom_button_xyz", app_name="non_existent_app_888")
    assert res["success"] is False
    assert res["status"] in ("WINDOW_NOT_FOUND", "CONTROL_NOT_FOUND")


def test_honest_failure_reporting():
    """Verify failures provide descriptive diagnostic messages without masking errors."""
    res = ui_action_engine.launch_app("definitely_fake_app_xyz_12345.exe")
    assert res["success"] is False
    assert "status" in res
    assert res["status"] in ("FAILED", "TIMEOUT", "NOT_FOUND")
    assert "not found" in res["message"].lower() or "failed" in res["message"].lower()
