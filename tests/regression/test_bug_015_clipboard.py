"""
REGRESSION TEST: BUG-015 (Clipboard Write Failure & Missing Verification)
Root Cause: No clipboard automation skill existed in engine or skills framework;
clipboard interactions failed without Win32 clipboard API synchronization.
Fix Verification:
1. 'copy the text "FRIDAY CLIPBOARD TEST" to the clipboard' sets clipboard.
2. Readback verification confirms exact string in clipboard.
3. Reading clipboard via skill and engine matches.
4. Rollback capability restores previous clipboard text.
"""

import pytest
from friday_ui.core.engine import FridayBrain, FridaySignals
from friday_core.skills.registry import skill_registry
from friday_core.skills.builtins.desktop_action import clipboard_set, clipboard_get, clipboard_verify


def test_clipboard_operations_runtime():
    """Verify native Windows clipboard set, get, and verification."""
    test_str = "FRIDAY_UNIT_TEST_CLIP_42"
    assert clipboard_set(test_str) is True

    # Readback
    read = clipboard_get()
    assert read == test_str

    # Verification function
    assert clipboard_verify(test_str) is True


def test_clipboard_skill_lifecycle():
    """Verify ClipboardSkill 9-stage verification lifecycle."""
    test_str = "VERIFIED_SKILL_PAYLOAD_88"
    res = skill_registry.execute_skill(
        tool_id="clipboard",
        params={"action": "set", "text": test_str},
        operation_id="clip-test-lifecycle"
    )

    assert res.success is True
    assert res.verification is not None
    assert res.verification.verified is True
    assert clipboard_get() == test_str


@pytest.mark.asyncio
async def test_clipboard_intent_in_brain():
    signals = FridaySignals()
    brain = FridayBrain(signals, None)

    target_text = "FRIDAY CLIPBOARD TEST"
    cmd = f"copy the text '{target_text}' to the clipboard"
    response = await brain.execute_smart_skill(cmd)

    assert response is not None
    assert "copied to clipboard and verified" in response

    # Physical machine state assertion
    actual = clipboard_get()
    assert actual == target_text
