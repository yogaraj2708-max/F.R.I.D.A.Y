"""
Tests for F.R.I.D.A.Y. 3.0 UI Automation Cancellation.
Verifies immediate task cancellation, terminal CANCELLED state, and prevention of late actions.
"""

import pytest
from friday_core.automation.action_engine import ui_action_engine


def test_cancellation_before_launch():
    """Verify cancelled task is aborted before launching application."""
    task_id = "test_cancel_launch_001"
    ui_action_engine.cancel_task(task_id)
    assert ui_action_engine.is_cancelled(task_id) is True

    res = ui_action_engine.launch_app("notepad", task_id=task_id)
    assert res["success"] is False
    assert res["status"] == "CANCELLED"
    assert "cancelled" in res["message"].lower()


def test_cancellation_before_click():
    """Verify cancelled task is aborted before executing click."""
    task_id = "test_cancel_click_002"
    ui_action_engine.cancel_task(task_id)

    res = ui_action_engine.click_control("Button", app_name="calculator", task_id=task_id)
    assert res["success"] is False
    assert res["status"] == "CANCELLED"
    assert "cancelled" in res["message"].lower()


def test_cancellation_before_type():
    """Verify cancelled task is aborted before typing."""
    task_id = "test_cancel_type_003"
    ui_action_engine.cancel_task(task_id)

    res = ui_action_engine.type_text("Secret Text", app_name="notepad", task_id=task_id)
    assert res["success"] is False
    assert res["status"] == "CANCELLED"
    assert "cancelled" in res["message"].lower()


def test_cancellation_before_inspection():
    """Verify cancelled task aborts inspection."""
    task_id = "test_cancel_insp_004"
    ui_action_engine.cancel_task(task_id)

    res = ui_action_engine.inspect_ui("calculator", task_id=task_id)
    assert res["success"] is False
    assert res["status"] == "CANCELLED"
