"""
F.R.I.D.A.Y. 3.0 — Structured Event Observability Logger
Maintains append-only audit trail and provides factual, non-hallucinated explanations
for "What did you do?", "What failed?", and "Why did that happen?".
"""

import os
import json
import uuid
import threading
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from friday_ui.core.config import APP_DATA_DIR
from friday_core.observability.models import StructuredEvent

logger = logging.getLogger("FRIDAY.Observability")

SENSITIVE_KEYS = {"password", "token", "secret", "api_key", "authorization", "key", "access_token"}


class StructuredEventLogger:
    """
    Audit-grade structured event logger.
    """
    def __init__(self, log_path: Optional[str] = None):
        if log_path is None:
            log_path = os.path.join(APP_DATA_DIR, "logs", "structured_events.jsonl")
        self.log_path = log_path
        self._lock = threading.Lock()
        self._in_memory_recent: List[StructuredEvent] = []

        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)

    @staticmethod
    def redact_params(params: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively masks sensitive tokens and credentials."""
        redacted = {}
        for k, v in params.items():
            if any(s in k.lower() for s in SENSITIVE_KEYS):
                redacted[k] = "********"
            elif isinstance(v, dict):
                redacted[k] = StructuredEventLogger.redact_params(v)
            else:
                redacted[k] = v
        return redacted

    def log_event(self, event: StructuredEvent) -> None:
        """Appends event to disk log and in-memory cache."""
        event.parameters = self.redact_params(event.parameters)

        line = event.model_dump_json() + "\n"
        with self._lock:
            self._in_memory_recent.append(event)
            if len(self._in_memory_recent) > 200:
                self._in_memory_recent.pop(0)

            try:
                with open(self.log_path, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception as e:
                logger.error(f"Failed writing structured event to {self.log_path}: {e}")

    def create_and_log(
        self,
        tool: str,
        action: str,
        parameters: Dict[str, Any],
        result: Optional[Any] = None,
        mission_id: Optional[str] = None,
        step_id: Optional[str] = None,
        status: str = "SUCCESS",
        error: Optional[str] = None,
        duration_ms: float = 0.0,
        verification_result: Optional[Dict[str, Any]] = None
    ) -> StructuredEvent:
        """Helper to create and log an event in one atomic call."""
        event = StructuredEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            mission_id=mission_id,
            step_id=step_id,
            tool=tool,
            action=action,
            parameters=parameters,
            result=result,
            duration_ms=round(duration_ms, 2),
            status=status,
            error=error,
            verification_result=verification_result
        )
        self.log_event(event)
        return event

    def get_events(self, mission_id: Optional[str] = None, limit: int = 50) -> List[StructuredEvent]:
        with self._lock:
            if mission_id:
                events = [e for e in self._in_memory_recent if e.mission_id == mission_id]
            else:
                events = list(self._in_memory_recent)
        return events[-limit:]

    def explain_what_happened(self, mission_id: Optional[str] = None) -> str:
        """
        Answers 'What did you do?' strictly from factual recorded event logs.
        """
        events = self.get_events(mission_id=mission_id, limit=20)
        if not events:
            return "No recent operations recorded in the audit event log."

        lines = ["Factual activity log derived from structured event telemetry:"]
        for idx, e in enumerate(events, 1):
            status_indicator = "✅" if e.status == "SUCCESS" else ("🛑" if e.status == "BLOCKED" else "❌")
            lines.append(
                f"{idx}. {status_indicator} [{e.timestamp}] Tool: '{e.tool}' | Action: '{e.action}' | Status: {e.status} ({e.duration_ms}ms)"
            )
            if e.error:
                lines.append(f"   Error: {e.error}")
            if e.verification_result:
                lines.append(f"   Verification: {e.verification_result.get('message', 'Verified')}")
        return "\n".join(lines)

    def explain_failures(self, mission_id: Optional[str] = None) -> str:
        """
        Answers 'What failed?' and 'Why did that happen?' directly from error traces.
        """
        events = self.get_events(mission_id=mission_id, limit=50)
        failed_events = [e for e in events if e.status in ("FAILED", "BLOCKED")]
        if not failed_events:
            return "No failures or blocked operations recorded in recent telemetry."

        lines = ["Factual root-cause failure diagnosis:"]
        for idx, e in enumerate(failed_events, 1):
            lines.append(f"{idx}. Operation '{e.tool}.{e.action}' was {e.status}:")
            lines.append(f"   Reason: {e.error or 'Unspecified failure'}")
            if e.verification_result:
                lines.append(f"   Postcondition Audit: {e.verification_result.get('details', {})}")
        return "\n".join(lines)


# Global Singleton Event Logger
structured_event_logger = StructuredEventLogger()
