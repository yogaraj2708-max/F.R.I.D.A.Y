"""
F.R.I.D.A.Y. 3.0 — Voice Security & Integrity Guard
Enforces zero-trust authorization gating on spoken transcripts, prevents prompt injection,
and strictly separates transcript success from execution success (anti-false-success).
"""

import re
import logging
from typing import Dict, Any, Tuple, Optional
from friday_core.automation.security_guard import automation_security_guard

logger = logging.getLogger("FRIDAY.VoiceSecurity")


class VoiceSecurityGate:
    """
    Zero-trust boundary for spoken input:
    - Voice transcript is UNTRUSTED USER INPUT.
    - Evaluates dangerous instructions through system security gate.
    - Intercepts prompt injections and destructive OS commands.
    - Segregates lifecycle statuses:
      TRANSCRIPT_SUCCESS vs TOOL_SUCCESS vs VERIFICATION_SUCCESS vs FINAL_RESPONSE_SUCCESS.
    """

    DANGEROUS_PATTERNS = [
        r"\bformat\s+(?:drive\s+)?[a-z]:?",
        r"\bdelete\s+all\b",
        r"\bdrop\s+database\b",
        r"\bshutdown\b",
        r"\brm\s+-rf\b",
        r"\bdel\s+/[sfdq]\b",
        r"\bformat\s+disk\b"
    ]

    INJECTION_PATTERNS = [
        r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions",
        r"disregard\s+(?:all\s+)?(?:previous|prior)\s+rules",
        r"you\s+are\s+now\s+dan\b",
        r"bypass\s+(?:all\s+)?safety",
        r"output\s+system\s+prompt"
    ]

    def evaluate_transcript(self, transcript: str) -> Dict[str, Any]:
        """
        Validates spoken transcript against zero-trust dangerous command policies.
        Returns evaluation result dictionary.
        """
        if not transcript or not transcript.strip():
            return {"allowed": False, "reason": "EMPTY_TRANSCRIPT", "risk_level": "high"}

        text = transcript.strip().lower()

        # 1. Prompt Injection Checks
        for pat in self.INJECTION_PATTERNS:
            if re.search(pat, text):
                logger.warning("🚨 [Voice Security] Prompt injection blocked: '%s'", transcript)
                return {
                    "allowed": False,
                    "reason": "Prompt injection detected in transcript",
                    "risk_level": "high",
                    "transcript": transcript
                }

        # 2. Destructive System Commands Checks
        for pat in self.DANGEROUS_PATTERNS:
            if re.search(pat, text):
                logger.warning("🚨 [Voice Security] Destructive command blocked: '%s'", transcript)
                return {
                    "allowed": False,
                    "reason": "Blocked: Destructive operating system directive",
                    "risk_level": "high",
                    "transcript": transcript
                }

        # 3. Automation Security Guard Check
        sec_eval = automation_security_guard.evaluate(
            action="voice_transcript",
            target="system",
            arguments={"transcript": transcript}
        )

        return {
            "allowed": sec_eval.is_allowed,
            "reason": sec_eval.reason if not sec_eval.is_allowed else "NOMINAL_USER_INPUT",
            "risk_level": "high" if not sec_eval.is_allowed else "low",
            "transcript": transcript
        }

    def validate_action_evidence(
        self,
        transcript: str,
        tool_called: Optional[str] = None,
        tool_result: Optional[Dict[str, Any]] = None,
        verified: bool = False
    ) -> Dict[str, Any]:
        """
        Anti-False-Success Defense:
        Ensures the assistant NEVER announces successful action without hard evidence.
        """
        if not tool_called or not tool_result:
            return {"action_succeeded": False, "reason": "No tool execution evidence"}

        if isinstance(tool_result, dict):
            if "error" in tool_result or tool_result.get("success") is False:
                return {
                    "action_succeeded": False,
                    "reason": f"Tool returned error: {tool_result.get('error', 'Execution failure')}"
                }
            if verified or tool_result.get("success", False) or tool_result.get("pid"):
                return {"action_succeeded": True, "reason": "Evidence verified"}

        return {"action_succeeded": False, "reason": "Action unverified"}

    verify_action_evidence = validate_action_evidence


# Global Singleton Voice Security Gate
voice_security_gate = VoiceSecurityGate()
