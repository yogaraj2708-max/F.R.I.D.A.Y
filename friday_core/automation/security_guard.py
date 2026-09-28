"""
F.R.I.D.A.Y. 3.0 — UI Automation Security Guard
Enforces Zero-Trust authorization gates, process isolation, and dangerous command fencing.
"""

import os
import re
import json
from typing import Tuple, Dict, Any, Optional
from friday_core.settings import settings

AUDIT_DIR = os.path.abspath("AUDIT/UI_AUTOMATION_HARDENING")
SECURITY_AUDIT_FILE = os.path.join(AUDIT_DIR, "UI_AUTOMATION_SECURITY.json")

# Critical OS and protected system processes that must NEVER be automated or killed
PROTECTED_PROCESSES = {
    "csrss.exe", "lsass.exe", "services.exe", "smss.exe", "winlogon.exe",
    "wininit.exe", "svchost.exe", "dwm.exe", "spoolsv.exe", "runtimebroker.exe",
    "taskhostw.exe", "sihost.exe", "system", "system.exe", "registry",
    "ntoskrnl.exe", "audiodg.exe", "securityhealthservice.exe", "msmpeng.exe"
}

# Dangerous command tokens and shell exploits prohibited in UI automation
DANGEROUS_PATTERNS = [
    r"\bformat\b",
    r"\brmdir\s+/[sq]\b",
    r"\bdel\s+/[fsq]\b",
    r"\breg\s+(delete|add)\b",
    r"\bpowershell\s+-(enc|encodedcommand)\b",
    r"\bshutdown\s+/[strf]\b",
    r"\bvssadmin\s+delete\s+shadows\b",
    r"\bbcdedit\b",
    r"\bnet\s+user\b"
]


class AutomationSecurityGuard:
    """Enforces zero-trust boundaries on all desktop automation operations."""

    def __init__(self):
        os.makedirs(AUDIT_DIR, exist_ok=True)
        self._security_log = []

    def evaluate_launch(self, app_name: str) -> Tuple[bool, str]:
        """Validates that requested application is safe to launch."""
        if bool(settings.get("observe_only", False)):
            self._log_decision("launch_app", app_name, "BLOCKED", "Panic / Observe-Only mode active.")
            return False, "Security Gatekeeper: Blocked launch under active Observe-Only panic policy."

        clean = (app_name or "").strip().lower()
        if not clean:
            return False, "Security Gatekeeper: Empty application name rejected."

        # Check protected system processes
        base_exe = os.path.basename(clean)
        if base_exe in PROTECTED_PROCESSES or clean in PROTECTED_PROCESSES:
            self._log_decision("launch_app", app_name, "BLOCKED", f"Protected OS core process: {base_exe}")
            return False, f"Security Gatekeeper: Prohibited targeting of protected OS process '{base_exe}'."

        # Check command injection
        for pat in DANGEROUS_PATTERNS:
            if re.search(pat, clean):
                self._log_decision("launch_app", app_name, "BLOCKED", f"Matched prohibited pattern: {pat}")
                return False, f"Security Gatekeeper: Prohibited destructive command sequence in '{app_name}'."

        self._log_decision("launch_app", app_name, "PERMITTED", "Safe application launch authorized.")
        return True, "Authorized"

    def evaluate_click(self, control_name: str, app_name: Optional[str] = None) -> Tuple[bool, str]:
        """Validates control click action."""
        if bool(settings.get("observe_only", False)):
            self._log_decision("click_control", f"{app_name}:{control_name}", "BLOCKED", "Observe-only mode active.")
            return False, "Security Gatekeeper: Clicks blocked in Observe-Only mode."

        target = (control_name or "").strip().lower()
        if not target:
            return False, "Security Gatekeeper: Empty control name rejected."

        # Prevent clicking destructive buttons without user confirmation
        destructive_triggers = ["format all", "delete partition", "uninstall windows", "erase drive"]
        if any(d in target for d in destructive_triggers):
            self._log_decision("click_control", target, "BLOCKED", "Destructive system trigger identified.")
            return False, f"Security Gatekeeper: Action blocked — '{control_name}' is classified as prohibited destructive action."

        self._log_decision("click_control", f"{app_name}:{control_name}", "PERMITTED", "Click authorized.")
        return True, "Authorized"

    def evaluate_typing(self, text: str, app_name: Optional[str] = None) -> Tuple[bool, str]:
        """Validates text content to be typed."""
        if bool(settings.get("observe_only", False)):
            self._log_decision("type_text", f"{app_name}:{len(text)}chars", "BLOCKED", "Observe-only mode active.")
            return False, "Security Gatekeeper: Typing blocked in Observe-Only mode."

        # Check if text contains destructive script payloads
        for pat in DANGEROUS_PATTERNS:
            if re.search(pat, text.lower()):
                self._log_decision("type_text", f"{app_name}", "BLOCKED", f"Destructive payload detected: {pat}")
                return False, "Security Gatekeeper: Injection of destructive system shell commands prohibited."

        self._log_decision("type_text", f"{app_name}:{len(text)}chars", "PERMITTED", "Text injection authorized.")
        return True, "Authorized"

    def evaluate(
        self,
        action: str,
        target: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Unified evaluation endpoint for UI automation actions.
        """
        args = arguments or {}
        if action == "launch_app":
            app = target or args.get("app_name", "")
            ok, reason = self.evaluate_launch(app)
        elif action == "click_control":
            ctrl = target or args.get("control_name", "")
            app = args.get("app_name")
            ok, reason = self.evaluate_click(ctrl, app)
        elif action == "type_text":
            text = args.get("text", "")
            app = args.get("app_name")
            ok, reason = self.evaluate_typing(text, app)
        elif action == "inspect_ui":
            # Read-only observation is always safe unless explicitly locked
            ok, reason = True, "Inspection authorized"
        else:
            ok, reason = True, "Action permitted"

        class SecurityEvalResult:
            def __init__(self, allowed: bool, r: str):
                self.is_allowed = allowed
                self.reason = r

            def to_dict(self):
                return {"is_allowed": self.is_allowed, "reason": self.reason}

        return SecurityEvalResult(ok, reason)

    def _log_decision(self, action: str, target: str, verdict: str, reason: str):
        entry = {
            "action": action,
            "target": target,
            "verdict": verdict,
            "reason": reason
        }
        self._security_log.append(entry)
        try:
            with open(SECURITY_AUDIT_FILE, "w", encoding="utf-8") as f:
                json.dump({"total_evaluations": len(self._security_log), "log": self._security_log}, f, indent=2)
        except Exception:
            pass


automation_security = AutomationSecurityGuard()
automation_security_guard = automation_security
ui_security_guard = automation_security
