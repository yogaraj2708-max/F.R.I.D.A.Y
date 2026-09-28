"""
F.R.I.D.A.Y. 3.0 — Adversarial Red-Team Security & Fence Verification
Tests:
1. Path traversal and Windows system root modification escapes.
2. Protection of critical Windows system processes against termination attacks.
3. Approval token single-use enforcement and replay attack prevention.
4. Destructive operation rate limiting exhaustion.
5. Panic mode observe-only mutation lockouts.
"""

import os
import pytest
from friday_core.security.gate import SecurityGate, PROTECTED_SYSTEM_PROCESSES
from friday_core.gatekeeper.gatekeeper import ActionGatekeeper, ActionIntent, ActionResult


def test_adversarial_path_traversal_fencing():
    gate = SecurityGate()
    gk = ActionGatekeeper()

    traversal_payloads = [
        r"C:\Windows\System32\drivers\etc\hosts",
        r"C:\Windows\explorer.exe",
        os.path.expandvars(r"%USERPROFILE%\Documents\..\..\..\..\Windows\System32\calc.exe"),
        r"C:\Program Files\Common Files\system.dll",
        r"C:\Program Files (x86)\test.exe",
    ]

    for payload in traversal_payloads:
        # 1. SecurityGate fence check
        allowed, err = gate.check_path_fence(payload)
        assert not allowed, f"SecurityGate failed to block traversal payload: {payload}"
        assert "protected by Windows system fence" in err

        # 2. Gatekeeper safe path check
        safe, gk_err = gk.is_path_safe(payload)
        assert not safe, f"Gatekeeper failed to block traversal payload: {payload}"


def test_protected_system_process_termination_attack():
    gate = SecurityGate()
    gk = ActionGatekeeper()

    critical_procs = ["csrss.exe", "lsass.exe", "services.exe", "smss.exe", "winlogon.exe", "explorer.exe", "system"]

    for proc_name in critical_procs:
        # 1. SecurityGate evaluation
        auth = gate.evaluate_authorization(
            action_name="kill_process",
            params={"process_name": proc_name},
            user_confirmed=True
        )
        assert not auth["authorized"], f"SecurityGate failed to block kill of critical process: {proc_name}"
        assert "protected Windows system process" in auth["reason"]

        # 2. Gatekeeper execution
        intent = ActionIntent(
            action="kill_process",
            target=proc_name,
            confirmed=True,
            reason="Adversarial attack"
        )
        res = gk.execute_action(intent)
        assert not res.success, f"Gatekeeper executed kill on critical process: {proc_name}"
        assert "protected Windows system process" in res.message


def test_approval_replay_attack_prevention():
    gate = SecurityGate()
    token = "clearance_token_xyz_999"

    # First authorization with user confirmation & approval token
    auth1 = gate.evaluate_authorization(
        action_name="recycle_file",
        params={"target_path": r"C:\Users\Admin\Documents\temp.txt", "approval_token": token},
        user_confirmed=True
    )
    assert auth1["authorized"] is True

    # Attacker attempts replay of the exact same approval token
    auth2 = gate.evaluate_authorization(
        action_name="recycle_file",
        params={"target_path": r"C:\Users\Admin\Documents\other.txt", "approval_token": token},
        user_confirmed=True
    )
    assert auth2["authorized"] is False
    assert "replay attack blocked" in auth2["reason"]


def test_destructive_rate_limit_exhaustion():
    gate = SecurityGate(max_destructive_per_minute=3)

    # Perform 3 authorized actions within 60s
    for i in range(3):
        auth = gate.evaluate_authorization(
            action_name="recycle_file",
            params={"target_path": rf"C:\Users\Admin\Documents\file_{i}.txt"},
            user_confirmed=True
        )
        assert auth["authorized"] is True

    # 4th action should be blocked by rate limiter
    auth_overflow = gate.evaluate_authorization(
        action_name="recycle_file",
        params={"target_path": r"C:\Users\Admin\Documents\file_overflow.txt"},
        user_confirmed=True
    )
    assert auth_overflow["authorized"] is False
    assert "rate limit exceeded" in auth_overflow["reason"].lower()


def test_panic_mode_mutation_lockout():
    gk = ActionGatekeeper()
    gk.enable_panic_mode()
    assert gk.panic_mode is True

    try:
        # Tier 1 action (open_app) should be blocked in panic mode
        intent_t1 = ActionIntent(action="open_app", target="notepad")
        res_t1 = gk.execute_action(intent_t1)
        assert not res_t1.success
        assert "Observe Only" in res_t1.message

        # Tier 2 action (delete_file) should be blocked in panic mode even if confirmed
        intent_t2 = ActionIntent(action="delete_file", target="dummy.txt", confirmed=True)
        res_t2 = gk.execute_action(intent_t2)
        assert not res_t2.success
        assert "Observe Only" in res_t2.message
    finally:
        gk.disable_panic_mode()
        assert gk.panic_mode is False
