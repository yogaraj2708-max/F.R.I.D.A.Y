"""
REGRESSION TEST: Notepad Real Keystroke Typing & Exact Readback Verification
Verifies the Second Regression Fix:
1. Small text ('hello world') typed via real User32 SendInput keystrokes.
2. Multiline text ('line one\\nline two\\nline three') typed with actual Enter key events.
3. C code with braces typed literally via SendInput without virtual-key syntax parsing.
4. Large multiline code (scientific calculator) typed progressively with exact readback.
5. Conversation anaphora: 'Write a C calculator program' -> 'put that code in my notepad'.
6. Special characters ('{}[]()<>"\\'\\|&%^$') typed literally without SendKeys error.
7. Independent readback verification requiring exact equality (ACTUAL == EXPECTED).
8. Security gates remain fully active (SecurityGatekeeper & PEOV lifecycle).
9. Verify clipboard is NOT used in normal Notepad typing path (clipboard preserved).
10. Verify ValuePattern.SetValue is NOT used for insertion in normal Notepad typing.
"""

import os
import re
import sys
import time
import subprocess
import pytest
from unittest.mock import MagicMock, patch

from friday_ui.core.engine import FridayBrain
from friday_core.skills.registry import skill_registry
from friday_core.skills.builtins.ui_automation import (
    UITypeTextSkill,
    choose_insertion_mode,
    INSERTION_MODE_REAL_KEYSTROKE,
    INSERTION_MODE_PROGRAMMATIC_SETVALUE,
    INSERTION_MODE_CLIPBOARD_FALLBACK
)
from friday_core.automation.action_engine import ui_action_engine
from friday_core.automation.security_guard import automation_security_guard
from friday_core.automation.mouse_keyboard import type_real_keystrokes

SMALL_TEXT = "hello world"
MULTILINE_TEXT = "line one\nline two\nline three"
C_CODE_SAMPLE = """#include <stdio.h>

int main() {
    return 0;
}"""
SPECIAL_CHARACTERS = '{}[]()<>"\'\\|&%^$'

LARGE_C_CALCULATOR_CODE = """#include <stdio.h>
#include <math.h>
#include <stdlib.h>

#define PI 3.14159265358979323846

int main() {
    double num1, num2, result;
    char choice;

    printf("=== SIMPLE SCIENTIFIC CALCULATOR ===\\n");
    printf("Choose operation:\\n");
    printf("1. Addition (+)\\n");
    printf("2. Subtraction (-)\\n");
    printf("3. Multiplication (*)\\n");
    printf("4. Division (/)\\n");
    printf("5. Square Root (sqrt)\\n");
    printf("6. Power (^)\\n");
    printf("7. Sine (sin) - Radians\\n");
    printf("8. Cosine (cos) - Radians\\n");
    printf("9. Tangent (tan) - Radians\\n");
    printf("10. Logarithm (log) - Base 10\\n");
    printf("11. Natural Log (ln)\\n");
    printf("12. Exponential (exp)\\n");
    printf("Enter choice: ");

    scanf("%c", &choice);
    getchar();

    switch(choice) {
        case '1':
            printf("Enter two numbers: ");
            scanf("%lf %lf", &num1, &num2);
            result = num1 + num2;
            printf("%.6f + %.6f = %.6f\\n", num1, num2, result);
            break;
        case '2':
            printf("Enter two numbers: ");
            scanf("%lf %lf", &num1, &num2);
            result = num1 - num2;
            printf("%.6f - %.6f = %.6f\\n", num1, num2, result);
            break;
        case '3':
            printf("Enter two numbers: ");
            scanf("%lf %lf", &num1, &num2);
            result = num1 * num2;
            printf("%.6f * %.6f = %.6f\\n", num1, num2, result);
            break;
        case '4':
            printf("Enter two numbers: ");
            scanf("%lf %lf", &num1, &num2);
            if (num2 != 0) {
                result = num1 / num2;
                printf("%.6f / %.6f = %.6f\\n", num1, num2, result);
            } else {
                printf("Error: Division by zero!\\n");
            }
            break;
        case '5':
            printf("Enter a number: ");
            scanf("%lf", &num1);
            if (num1 >= 0) {
                result = sqrt(num1);
                printf("sqrt(%.6f) = %.6f\\n", num1, result);
            } else {
                printf("Error: Cannot take square root of negative number!\\n");
            }
            break;
        default:
            printf("Invalid choice.\\n");
    }
    return 0;
}"""


def _close_notepad_windows():
    """Helper to clean up any open Notepad instances."""
    try:
        if sys.platform == "win32":
            chk = subprocess.run(["tasklist", "/FI", "IMAGENAME eq notepad.exe"], capture_output=True, text=True)
            if "notepad.exe" in chk.stdout.lower():
                subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
                time.sleep(1.0)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def clean_notepad_environment():
    """Ensures clean desktop environment before and after each test."""
    _close_notepad_windows()
    yield
    _close_notepad_windows()


# =====================================================================
# TEST 1: SMALL TEXT ("hello world" — REAL KEYSTROKES)
# =====================================================================
@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop automation required")
def test_regression_test_1_small_text():
    """TEST 1: Small text 'hello world' injected via real keystrokes."""
    mode_selected = choose_insertion_mode(SMALL_TEXT, {"has_value_pattern": True})
    assert mode_selected == INSERTION_MODE_REAL_KEYSTROKE, f"Expected REAL_KEYSTROKE, got {mode_selected}"

    skill = UITypeTextSkill()
    res = skill.execute({"app_name": "notepad", "text": SMALL_TEXT, "mode": "replace", "typing_delay_ms": 2.0}, "test_op_small")
    assert res.get("injected") is True, f"Failed to inject: {res.get('message')}"
    assert res.get("insertion_mode") == INSERTION_MODE_REAL_KEYSTROKE

    obs = skill.observe("test_op_small", {"app_name": "notepad"})
    ver = skill.verify(obs, {"app_name": "notepad", "text": SMALL_TEXT})
    assert ver.verified is True, f"Verification failed: {ver.message}"

    actual = obs.observed_state.get("actual_content", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    assert actual == SMALL_TEXT, f"Readback mismatch: '{actual}' != '{SMALL_TEXT}'"


# =====================================================================
# TEST 2: MULTILINE TEXT ("line one\nline two\nline three")
# =====================================================================
@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop automation required")
def test_regression_test_2_multiline():
    """TEST 2: Multiline text typed with actual Enter key events."""
    mode_selected = choose_insertion_mode(MULTILINE_TEXT, {"has_value_pattern": True})
    assert mode_selected == INSERTION_MODE_REAL_KEYSTROKE

    skill = UITypeTextSkill()
    res = skill.execute({"app_name": "notepad", "text": MULTILINE_TEXT, "mode": "replace", "typing_delay_ms": 2.0}, "test_op_multi")
    assert res.get("injected") is True
    assert res.get("insertion_mode") == INSERTION_MODE_REAL_KEYSTROKE

    obs = skill.observe("test_op_multi", {"app_name": "notepad"})
    actual = obs.observed_state.get("actual_content", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    assert actual == MULTILINE_TEXT, f"Readback mismatch: '{actual}' != '{MULTILINE_TEXT}'"


# =====================================================================
# TEST 3: C CODE WITH BRACES (#include <stdio.h>\n\nint main() {\n    return 0;\n})
# =====================================================================
@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop automation required")
def test_regression_test_3_c_code_with_braces():
    """TEST 3: C code with braces typed character-by-character without SendKeys parser."""
    mode_selected = choose_insertion_mode(C_CODE_SAMPLE, {"has_value_pattern": True})
    assert mode_selected == INSERTION_MODE_REAL_KEYSTROKE

    skill = UITypeTextSkill()
    res = skill.execute({"app_name": "notepad", "text": C_CODE_SAMPLE, "mode": "replace", "typing_delay_ms": 2.0}, "test_op_c_braces")
    assert res.get("injected") is True
    assert res.get("insertion_mode") == INSERTION_MODE_REAL_KEYSTROKE

    obs = skill.observe("test_op_c_braces", {"app_name": "notepad"})
    ver = skill.verify(obs, {"app_name": "notepad", "text": C_CODE_SAMPLE})
    assert ver.verified is True

    actual = obs.observed_state.get("actual_content", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    expected = C_CODE_SAMPLE.replace("\r\n", "\n").replace("\r", "\n").strip()
    assert actual == expected, f"Readback mismatch:\nACTUAL:\n{actual}\nEXPECTED:\n{expected}"


# =====================================================================
# TEST 4: LARGE MULTILINE CODE (CALCULATOR PROGRAM)
# =====================================================================
@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop automation required")
def test_regression_test_4_large_multiline_code():
    """TEST 4: Large multiline C calculator code typed via real SendInput keystrokes."""
    mode_selected = choose_insertion_mode(LARGE_C_CALCULATOR_CODE, {"has_value_pattern": True})
    assert mode_selected == INSERTION_MODE_REAL_KEYSTROKE

    skill = UITypeTextSkill()
    res = skill.execute({
        "app_name": "notepad",
        "text": LARGE_C_CALCULATOR_CODE,
        "mode": "replace",
        "typing_delay_ms": 1.0  # Fast real keystroke mode for large file
    }, "test_op_calc")
    assert res.get("injected") is True, f"Failed: {res.get('message')}"
    assert res.get("insertion_mode") == INSERTION_MODE_REAL_KEYSTROKE

    obs = skill.observe("test_op_calc", {"app_name": "notepad"})
    actual = obs.observed_state.get("actual_content", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    expected = LARGE_C_CALCULATOR_CODE.replace("\r\n", "\n").replace("\r", "\n").strip()
    assert actual == expected


# =====================================================================
# TEST 5: CONVERSATION ANAPHORA RESOLUTION ("put that code in my notepad")
# =====================================================================
@pytest.mark.asyncio
async def test_regression_test_5_conversation_anaphora():
    """TEST 5: 'put that code in my notepad' extracts previous turn code, never types 'that code'."""
    engine = FridayBrain.__new__(FridayBrain)
    engine.signals = MagicMock()
    engine.conversation_history = [
        {"role": "user", "content": "Write a C calculator program."},
        {
            "role": "assistant",
            "content": f"Here is the complete C calculator program, Boss:\n\n```c\n{C_CODE_SAMPLE}\n```\nLet me know if you need anything else."
        }
    ]

    with patch.object(skill_registry, "execute_skill") as mock_exec:
        mock_exec.return_value = MagicMock(success=True, data={"insertion_mode": INSERTION_MODE_REAL_KEYSTROKE}, error=None)
        res = await engine.execute_smart_skill("put that code in my notepad")

        assert res is not None, "Failed to match fast path for 'put that code in my notepad'"
        mock_exec.assert_called_once()

        call_params = mock_exec.call_args[1]["params"]
        assert call_params["app_name"] == "notepad"
        assert call_params["text"] == C_CODE_SAMPLE.strip()
        assert call_params["text"] != "that code"
        assert call_params["mode"] == "replace"


# =====================================================================
# TEST 6: SPECIAL CHARACTERS ({}[]()<>"'\|&%^$)
# =====================================================================
@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop automation required")
def test_regression_test_6_special_characters():
    """TEST 6: Literal special characters typed directly with KEYEVENTF_UNICODE."""
    skill = UITypeTextSkill()
    res = skill.execute({"app_name": "notepad", "text": SPECIAL_CHARACTERS, "mode": "replace", "typing_delay_ms": 2.0}, "test_op_spec")
    assert res.get("injected") is True
    assert res.get("insertion_mode") == INSERTION_MODE_REAL_KEYSTROKE

    obs = skill.observe("test_op_spec", {"app_name": "notepad"})
    actual = obs.observed_state.get("actual_content", "").strip()
    assert actual == SPECIAL_CHARACTERS, f"Special characters mismatch: '{actual}' != '{SPECIAL_CHARACTERS}'"


# =====================================================================
# TEST 7: READBACK EXACT EQUALITY (ACTUAL == EXPECTED)
# =====================================================================
@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop automation required")
def test_regression_test_7_readback_exact_equality():
    """TEST 7: Invariant check requiring exact equality after CRLF normalization."""
    test_phrase = "Exact Readback Equality Invariant 2026: printf(\"%d\\n\", 42);"
    skill = UITypeTextSkill()
    res = skill.execute({"app_name": "notepad", "text": test_phrase, "mode": "replace", "typing_delay_ms": 2.0}, "test_op_exact")
    assert res.get("injected") is True

    obs = skill.observe("test_op_exact", {"app_name": "notepad"})
    actual = obs.observed_state.get("actual_content", "").replace("\r\n", "\n").replace("\r", "\n").strip()
    expected = test_phrase.strip()
    assert actual == expected, f"ACTUAL != EXPECTED: '{actual}' != '{expected}'"


# =====================================================================
# TEST 8: SECURITY GATES REMAIN ACTIVE
# =====================================================================
def test_regression_test_8_security_gates_active():
    """TEST 8: SecurityGatekeeper verifies safe typing while rejecting malicious commands."""
    safe_eval = automation_security_guard.evaluate(
        action="type_text",
        target="notepad",
        arguments={"text": C_CODE_SAMPLE, "app_name": "notepad", "mode": "replace"}
    )
    assert safe_eval.is_allowed is True

    malicious_eval = automation_security_guard.evaluate(
        action="type_text",
        target="notepad",
        arguments={"text": "format C: /y", "app_name": "notepad", "mode": "type"}
    )
    assert malicious_eval.is_allowed is False


# =====================================================================
# TEST 9: VERIFY CLIPBOARD IS NOT USED IN NORMAL NOTEPAD TYPING PATH
# =====================================================================
@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop automation required")
def test_regression_test_9_no_clipboard_used_for_typing():
    """TEST 9: Verifies that clipboard is NEVER touched in normal Notepad typing."""
    import uiautomation as auto
    SENTINEL_CLIPBOARD = "PRESERVED_USER_CLIPBOARD_SECRET_98765"
    auto.SetClipboardText(SENTINEL_CLIPBOARD)
    time.sleep(0.05)

    with patch.object(auto, "SetClipboardText", wraps=auto.SetClipboardText) as mock_clip:
        skill = UITypeTextSkill()
        res = skill.execute({
            "app_name": "notepad",
            "text": "Keystroke typing without clipboard",
            "mode": "replace",
            "typing_delay_ms": 2.0
        }, "test_op_no_clip")

        assert res.get("injected") is True
        assert res.get("insertion_mode") == INSERTION_MODE_REAL_KEYSTROKE
        # Verify auto.SetClipboardText was NEVER called during typing
        mock_clip.assert_not_called()

    # Verify clipboard content remains completely unaltered
    clipboard_after = auto.GetClipboardText()
    assert clipboard_after == SENTINEL_CLIPBOARD, f"Clipboard was modified: '{clipboard_after}' != '{SENTINEL_CLIPBOARD}'"


# =====================================================================
# TEST 10: VERIFY VALUEPATTERN.SETVALUE IS NOT USED FOR INSERTION IN NORMAL TYPING
# =====================================================================
@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop automation required")
def test_regression_test_10_no_valuepattern_setvalue_for_insertion():
    """TEST 10: Verifies that ValuePattern.SetValue is NEVER used for insertion in normal typing."""
    import uiautomation as auto
    with patch.object(auto.ValuePattern, "SetValue") as mock_setvalue:
        skill = UITypeTextSkill()
        res = skill.execute({
            "app_name": "notepad",
            "text": "True SendInput typing without SetValue",
            "mode": "replace",
            "typing_delay_ms": 2.0
        }, "test_op_no_setvalue")

        assert res.get("injected") is True
        assert res.get("insertion_mode") == INSERTION_MODE_REAL_KEYSTROKE
        # Verify ValuePattern.SetValue was NEVER called for insertion
        mock_setvalue.assert_not_called()

    obs = skill.observe("test_op_no_setvalue", {"app_name": "notepad"})
    actual = obs.observed_state.get("actual_content", "").strip()
    assert "True SendInput typing without SetValue" in actual

