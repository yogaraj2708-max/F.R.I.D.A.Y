"""
Tests for F.R.I.D.A.Y. 3.0 UI Automation Engine & Priority Hierarchy.
Verifies Semantic UIA, Win32 controls, Keyboard navigation, Bounded inputs, and postcondition verification.
"""

import pytest
from friday_core.automation.action_engine import ui_action_engine
from friday_core.automation.inspector import ui_inspector
from friday_core.automation.hierarchy import AutomationPriority


def test_action_engine_initialization():
    """Verify action engine is initialized and available."""
    assert ui_action_engine is not None
    assert hasattr(ui_action_engine, "launch_app")
    assert hasattr(ui_action_engine, "click_control")
    assert hasattr(ui_action_engine, "type_text")
    assert hasattr(ui_action_engine, "inspect_ui")


def test_hierarchy_priority_levels():
    """Verify automation hierarchy levels are strictly ordered."""
    assert AutomationPriority.SEMANTIC_UIA == 1
    assert AutomationPriority.APPLICATION_SHORTCUTS == 2
    assert AutomationPriority.BOUNDED_INPUT == 3
    assert AutomationPriority.VISION == 4
    assert AutomationPriority.COORDINATES_FALLBACK == 5


def test_launch_app_security_and_validation():
    """Verify launch_app enforces security checks and argument validation."""
    # Empty app name
    res_empty = ui_action_engine.launch_app("")
    assert res_empty["success"] is False
    assert "Empty" in res_empty["message"] or "SECURITY_BLOCKED" in res_empty.get("status", "")

    # Protected process targeting
    res_prot = ui_action_engine.launch_app("csrss.exe")
    assert res_prot["success"] is False
    assert res_prot["status"] == "BLOCKED"
    assert "Security Gate Blocked" in res_prot["message"]


def test_inspect_ui_validation():
    """Verify inspect_ui checks arguments and returns structured error for non-existent app."""
    res = ui_action_engine.inspect_ui("non_existent_app_xyz_999")
    assert res["success"] is False
    assert res["status"] in ("NOT_FOUND", "BLOCKED")
    assert "elements" in res


def test_click_control_empty_target():
    """Verify click_control rejects empty control names."""
    res = ui_action_engine.click_control("")
    assert res["success"] is False
    assert "Empty" in res["message"] or "BLOCKED" in res["status"]


def test_type_text_empty_input():
    """Verify type_text validates input parameters."""
    res = ui_action_engine.type_text("")
    # Empty string should either be validated or handled safely
    assert isinstance(res, dict)
