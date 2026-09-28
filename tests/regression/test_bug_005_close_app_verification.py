"""
Regression test for Bug Fix #3: Close Application False-Success Elimination.
Verifies target location, termination request, wait/observe, and real process termination verification.
"""

import time
import subprocess
import psutil
from friday_core.gatekeeper.gatekeeper import gatekeeper
from friday_core.gatekeeper.models import ActionIntent


def test_close_app_idempotent_when_already_closed():
    """Closing an application that is not running must report already closed cleanly."""
    intent = ActionIntent(action="close_app", target="nonexistent_fake_app_xyz")
    res = gatekeeper.execute_action(intent)
    assert res.success is True
    assert "already closed" in res.message.lower()


def test_close_app_protected_system_process_rejection():
    """Attempting to close a protected Windows system process must be rejected with security violation."""
    intent = ActionIntent(action="close_app", target="csrss")
    res = gatekeeper.execute_action(intent)
    assert res.success is False
    assert "protected windows core process" in res.message.lower() or "security violation" in res.message.lower()


def test_close_app_real_process_termination_and_verification():
    """Spawns a real notepad process, closes it, and verifies it is physically terminated."""
    proc = subprocess.Popen(["notepad.exe"])
    pid = proc.pid
    time.sleep(0.5)

    try:
        assert psutil.pid_exists(pid), "Spawned notepad must be running before close test"

        intent = ActionIntent(action="close_app", target="notepad")
        res = gatekeeper.execute_action(intent)

        assert res.success is True, f"Close app failed: {res.message}"
        assert "verified terminated" in res.message.lower() or "closed" in res.message.lower()

        # Independently verify process PID is physically gone
        time.sleep(0.3)
        assert not psutil.pid_exists(pid), "Process must be terminated and gone from OS process table"
    finally:
        # Cleanup in case of assertion failure
        if psutil.pid_exists(pid):
            try:
                proc.kill()
            except Exception:
                pass
