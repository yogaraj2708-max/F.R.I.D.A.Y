"""
Tests for F.R.I.D.A.Y. 3.0 UI Automation Security Gatekeeper.
Verifies protected process blocking, destructive payload rejection, and observe-only panic mode.
"""

import pytest
from friday_core.automation.security_guard import automation_security, PROTECTED_PROCESSES
from friday_core.settings import settings


def test_protected_processes_fencing():
    """Verify that targeting core OS processes is strictly prohibited."""
    for proc in ["csrss.exe", "lsass.exe", "services.exe", "winlogon.exe", "svchost.exe"]:
        ok, reason = automation_security.evaluate_launch(proc)
        assert ok is False, f"Process {proc} should have been blocked"
        assert "Protected" in reason or "Prohibited" in reason


def test_dangerous_command_injection_fencing():
    """Verify destructive shell commands are blocked from launch and typing."""
    dangerous_payloads = [
        "format C: /fs:ntfs",
        "rmdir /s /q C:\\Windows",
        "del /f /s /q *.*",
        "powershell -encodedcommand dGVzdA==",
        "shutdown /s /t 0"
    ]
    for cmd in dangerous_payloads:
        # Launch check
        ok_l, reason_l = automation_security.evaluate_launch(cmd)
        assert ok_l is False, f"Launch command '{cmd}' should have been blocked"

        # Type check
        ok_t, reason_t = automation_security.evaluate_typing(cmd)
        assert ok_t is False, f"Type payload '{cmd}' should have been blocked"


def test_destructive_click_fencing():
    """Verify destructive button labels are blocked."""
    destructive_clicks = [
        "format all",
        "delete partition",
        "uninstall windows",
        "erase drive"
    ]
    for btn in destructive_clicks:
        ok, reason = automation_security.evaluate_click(btn)
        assert ok is False, f"Destructive button '{btn}' should have been blocked"


def test_observe_only_mode_policy():
    """Verify observe-only panic mode blocks active mutations."""
    # Temporarily activate observe_only
    original_val = settings.get("observe_only", False)
    try:
        settings.set("observe_only", True)
        ok_l, _ = automation_security.evaluate_launch("notepad.exe")
        assert ok_l is False
        ok_c, _ = automation_security.evaluate_click("Button", "notepad")
        assert ok_c is False
        ok_t, _ = automation_security.evaluate_typing("Hello", "notepad")
        assert ok_t is False
    finally:
        settings.set("observe_only", original_val)
