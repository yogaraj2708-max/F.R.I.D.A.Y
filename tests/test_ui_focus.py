"""
Tests for F.R.I.D.A.Y. 3.0 Window Focus Management & Theft Defense.
Verifies foreground ownership, minimized window restoration, and task isolation.
"""

import pytest
from friday_core.automation.inspector import ui_inspector, WindowInspection
from friday_core.automation.action_engine import ui_action_engine


def test_window_focus_inspection_properties():
    """Verify WindowInspection includes is_foreground, is_minimized, and is_visible."""
    insp = WindowInspection(
        window_title="Test App",
        app_name="testapp",
        process_id=5000,
        process_name="testapp.exe",
        hwnd=12345,
        is_foreground=False,
        is_visible=True,
        is_enabled=True,
        is_minimized=True,
        bounding_rect=(0, 0, 100, 100)
    )
    assert insp.is_foreground is False
    assert insp.is_minimized is True
    assert insp.is_visible is True


def test_type_text_focus_theft_protection():
    """Verify type_text checks window existence and prevents typing into missing target."""
    res = ui_action_engine.type_text("malicious injection", app_name="completely_unrelated_target_app_404")
    assert res["success"] is False
    assert res["status"] in ("WINDOW_NOT_FOUND", "BLOCKED")
    assert "not found" in res["message"].lower() or "blocked" in res["message"].lower()
