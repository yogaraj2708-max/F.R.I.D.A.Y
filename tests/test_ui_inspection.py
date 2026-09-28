"""
Tests for F.R.I.D.A.Y. 3.0 UI Inspection & Accessibility Hierarchy.
Verifies window metadata extraction, control types, bounding rects, and values.
"""

import pytest
from friday_core.automation.inspector import ui_inspector, UIElementInfo, WindowInspection


def test_inspector_initialization():
    """Verify inspector is available with required methods."""
    assert ui_inspector is not None
    assert hasattr(ui_inspector, "inspect_window")
    assert hasattr(ui_inspector, "search_control")
    assert hasattr(ui_inspector, "verify_content")
    assert hasattr(ui_inspector, "is_control_stale")
    assert hasattr(ui_inspector, "is_hwnd_valid")


def test_ui_element_info_dataclass():
    """Verify UIElementInfo contains all Section 3 required attributes."""
    elem = UIElementInfo(
        control_type="ButtonControl",
        name="Submit",
        automation_id="submitBtn",
        bounding_rect=(10, 20, 110, 60),
        is_enabled=True,
        is_visible=True,
        current_value="OK",
        hwnd=12345,
        depth=1
    )
    d = elem.to_dict()
    assert d["control_type"] == "ButtonControl"
    assert d["name"] == "Submit"
    assert d["automation_id"] == "submitBtn"
    assert d["bounding_rect"] == [10, 20, 110, 60]
    assert d["is_enabled"] is True
    assert d["is_visible"] is True
    assert d["current_value"] == "OK"
    assert d["hwnd"] == 12345


def test_window_inspection_dataclass():
    """Verify WindowInspection structured metadata and summary."""
    insp = WindowInspection(
        window_title="Calculator",
        app_name="calculator",
        process_id=1024,
        process_name="calc.exe",
        hwnd=54321,
        is_foreground=True,
        is_visible=True,
        is_enabled=True,
        is_minimized=False,
        bounding_rect=(0, 0, 500, 600)
    )
    d = insp.to_dict()
    assert d["window_title"] == "Calculator"
    assert d["hwnd"] == 54321
    assert d["process_id"] == 1024
    assert d["is_foreground"] is True
    summary = insp.summary()
    assert "Calculator" in summary
    assert "54321" in summary


def test_search_control_by_auto_id_and_name():
    """Verify search_control priority matching."""
    e1 = UIElementInfo("ButtonControl", "Seven", "num7Button", (0, 0, 10, 10), True, True)
    e2 = UIElementInfo("EditControl", "Input", "txtBox", (0, 0, 50, 20), True, True)
    insp = WindowInspection("Test", "test", 1, "test.exe", 1, True, True, True, False, (0, 0, 100, 100), [e1, e2])

    # Search by automation_id
    res1 = ui_inspector.search_control(insp, automation_id="num7Button")
    assert res1 is not None
    assert res1.name == "Seven"

    # Search by Name
    res2 = ui_inspector.search_control(insp, name="Input")
    assert res2 is not None
    assert res2.automation_id == "txtBox"

    # Search non-existent
    res3 = ui_inspector.search_control(insp, name="NonExistent")
    assert res3 is None


def test_verify_content_matching():
    """Verify verify_content inspects values, names, and titles."""
    e1 = UIElementInfo("TextControl", "Display is 12", "res", (0, 0, 10, 10), True, True, current_value="12")
    insp = WindowInspection("Calculator", "calc", 1, "calc.exe", 1, True, True, True, False, (0, 0, 100, 100), [e1])

    ok1, msg1 = ui_inspector.verify_content(insp, "12")
    assert ok1 is True
    assert "12" in msg1

    ok2, msg2 = ui_inspector.verify_content(insp, "99999")
    assert ok2 is False
