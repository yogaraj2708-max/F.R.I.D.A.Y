"""
F.R.I.D.A.Y. 3.0 — Hardened Security Gate & Policy Enforcement
Enforces confirmation gates on irreversible operations, path fencing, rate limiting,
and records all authorization decisions to the structured audit log.
"""

import os
import time
import logging
from typing import Dict, Any, Optional, List, Tuple, Set
from friday_core.security.taxonomy import SecurityRiskLevel, get_action_risk_level
from friday_core.observability.event_logger import structured_event_logger

logger = logging.getLogger("FRIDAY.SecurityGate")

FORBIDDEN_PATH_ROOTS = [
    os.path.expandvars(r"%SYSTEMROOT%"),
    os.path.expandvars(r"%WINDIR%"),
    os.path.expandvars(r"%PROGRAMFILES%"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%"),
]


PROTECTED_SYSTEM_PROCESSES = {
    "csrss.exe", "lsass.exe", "services.exe", "smss.exe", "winlogon.exe",
    "wininit.exe", "explorer.exe", "svchost.exe", "dwm.exe", "spoolsv.exe",
    "runtimebroker.exe", "taskhostw.exe", "sihost.exe", "system.exe", "system"
}


class SecurityGate:
    """
    Choke point for all security-sensitive actions in F.R.I.D.A.Y. 3.0.
    """
    def __init__(self, max_destructive_per_minute: int = 5):
        self.max_destructive = max_destructive_per_minute
        self._destructive_timestamps: List[float] = []
        self._consumed_approval_tokens: Set[str] = set()

    def _check_rate_limit(self) -> bool:
        now = time.time()
        # Clean older than 60 seconds
        self._destructive_timestamps = [t for t in self._destructive_timestamps if now - t < 60.0]
        if len(self._destructive_timestamps) >= self.max_destructive:
            return False
        self._destructive_timestamps.append(now)
        return True

    def check_path_fence(self, target_path: str) -> Tuple[bool, Optional[str]]:
        """Ensures actions do not modify critical Windows system directories."""
        if not target_path:
            return False, "Target path is empty."
        try:
            real_path = os.path.realpath(os.path.abspath(target_path))
        except OSError:
            return False, "Target path could not be resolved."

        for forbidden in FORBIDDEN_PATH_ROOTS:
            if forbidden:
                try:
                    real_forbidden = os.path.realpath(os.path.abspath(forbidden))
                    if os.path.commonpath([real_path, real_forbidden]).lower() == real_forbidden.lower():
                        return False, f"Target path '{target_path}' is protected by Windows system fence."
                except (ValueError, OSError):
                    continue
        return True, None

    def check_process_fence(self, process_name: str) -> Tuple[bool, Optional[str]]:
        """Ensures critical Windows operating system processes cannot be terminated."""
        if not process_name:
            return False, "Target process name is empty."
        norm = process_name.lower().strip()
        norm_exe = norm if norm.endswith(".exe") else norm + ".exe"
        if norm in PROTECTED_SYSTEM_PROCESSES or norm_exe in PROTECTED_SYSTEM_PROCESSES:
            return False, f"Process '{process_name}' is a protected Windows system process and cannot be terminated."
        return True, None

    def evaluate_authorization(
        self,
        action_name: str,
        params: Dict[str, Any],
        user_confirmed: bool = False,
        mission_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluates authorization against 5-tier risk taxonomy, path fencing, process protection,
        single-use approval token verification, and confirmation gates.
        Logs decision to structured event stream.
        """
        risk = get_action_risk_level(action_name)

        # 1. Approval token replay protection
        approval_token = params.get("approval_token")
        if approval_token:
            if approval_token in self._consumed_approval_tokens:
                err_msg = f"Security Violation: Approval token '{approval_token}' has already been consumed (replay attack blocked)."
                logger.error(f"Security Gate REPLAY BLOCKED: {err_msg}")
                return {
                    "authorized": False,
                    "reason": err_msg,
                    "risk_level": risk.value
                }

        # 2. Path fencing check if path parameter is present
        target_path = params.get("path") or params.get("target_path") or params.get("file_path")
        if target_path:
            allowed, fence_err = self.check_path_fence(target_path)
            if not allowed:
                structured_event_logger.create_and_log(
                    tool="security_gate",
                    action=action_name,
                    parameters=params,
                    status="BLOCKED",
                    error=fence_err,
                    mission_id=mission_id
                )
                return {
                    "authorized": False,
                    "reason": fence_err,
                    "risk_level": risk.value
                }

        # 3. Process protection check if kill_process
        if action_name.lower() in ("kill_process", "terminate_process"):
            proc_target = str(params.get("process_name") or params.get("target") or params.get("name") or "")
            allowed, proc_err = self.check_process_fence(proc_target)
            if not allowed:
                structured_event_logger.create_and_log(
                    tool="security_gate",
                    action=action_name,
                    parameters=params,
                    status="BLOCKED",
                    error=proc_err,
                    mission_id=mission_id
                )
                return {
                    "authorized": False,
                    "reason": proc_err,
                    "risk_level": risk.value
                }

        # 4. Risk Tier Confirmation Gate
        if risk in (SecurityRiskLevel.HIGH_RISK, SecurityRiskLevel.RESTRICTED):
            if not user_confirmed:
                err_msg = f"Operation '{action_name}' is {risk.value} and requires explicit user confirmation."
                logger.warning(f"Security Gate BLOCKED: {err_msg}")
                structured_event_logger.create_and_log(
                    tool="security_gate",
                    action=action_name,
                    parameters=params,
                    status="BLOCKED",
                    error=err_msg,
                    mission_id=mission_id
                )
                return {
                    "authorized": False,
                    "reason": err_msg,
                    "risk_level": risk.value,
                    "confirmation_required": True
                }

            # 5. Rate limiting for confirmed destructive operations
            if not self._check_rate_limit():
                err_msg = "Security Gate rate limit exceeded for destructive operations."
                structured_event_logger.create_and_log(
                    tool="security_gate",
                    action=action_name,
                    parameters=params,
                    status="BLOCKED",
                    error=err_msg,
                    mission_id=mission_id
                )
                return {
                    "authorized": False,
                    "reason": err_msg,
                    "risk_level": risk.value
                }

        # Consume approval token if provided and authorized
        if approval_token:
            self._consumed_approval_tokens.add(approval_token)

        # Authorized
        return {
            "authorized": True,
            "reason": "Authorized",
            "risk_level": risk.value
        }


# Global Singleton Security Gate
security_gate = SecurityGate()
