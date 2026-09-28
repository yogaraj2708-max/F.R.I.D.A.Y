"""
F.R.I.D.A.Y. 3.0 — UI Automation Audit Tracer
Records forensic traces for all UI inspections, actions, verifications, and security checks.
"""

import os
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List


AUDIT_DIR = os.path.abspath("AUDIT/UI_AUTOMATION_HARDENING")
ACTION_TRACE_FILE = os.path.join(AUDIT_DIR, "UI_ACTION_TRACE.json")
INSPECTION_TRACE_FILE = os.path.join(AUDIT_DIR, "UI_INSPECTION_TRACE.json")
FAILURES_FILE = os.path.join(AUDIT_DIR, "UI_AUTOMATION_FAILURES.json")


class UIAutomationTracer:
    """Thread-safe forensic tracer for desktop UI automation."""

    def __init__(self):
        os.makedirs(AUDIT_DIR, exist_ok=True)
        self._action_traces: List[Dict[str, Any]] = []
        self._inspection_traces: List[Dict[str, Any]] = []
        self._failures: List[Dict[str, Any]] = []

    def record_action(
        self,
        task_id: str,
        action: str,
        application: str,
        arguments: Dict[str, Any],
        security_status: str,
        execution_status: str,
        verification_status: str,
        before_state: Dict[str, Any],
        after_state: Dict[str, Any],
        control: Optional[str] = None,
        process: Optional[Dict[str, Any]] = None,
        window: Optional[Dict[str, Any]] = None,
        details: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Records an action execution trace."""
        clean_args = {k: v for k, v in arguments.items() if "password" not in k.lower() and "secret" not in k.lower()}
        trace_entry = {
            "trace_id": trace_id or f"trace_act_{uuid.uuid4().hex[:8]}",
            "task_id": task_id,
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "application": application,
            "control": control,
            "process": process or {},
            "window": window or {},
            "arguments": clean_args,
            "security_status": security_status,
            "execution_status": execution_status,
            "verification_status": verification_status,
            "before_state": before_state,
            "after_state": after_state,
            "details": details or ""
        }
        self._action_traces.append(trace_entry)
        self._save_action_traces()
        return trace_entry

    def record_inspection(
        self,
        task_id: str,
        application: str,
        window: Dict[str, Any],
        process: Dict[str, Any],
        controls_found: int,
        controls_summary: List[Dict[str, Any]],
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Records a UI inspection trace."""
        trace_entry = {
            "trace_id": trace_id or f"trace_insp_{uuid.uuid4().hex[:8]}",
            "task_id": task_id,
            "timestamp": datetime.now().isoformat(),
            "application": application,
            "window": window,
            "process": process,
            "controls_found": controls_found,
            "controls_summary": controls_summary[:25]
        }
        self._inspection_traces.append(trace_entry)
        self._save_inspection_traces()
        return trace_entry

    def record_failure(
        self,
        task_id: str,
        action: str,
        application: str,
        failure_type: str,
        reason: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Records a deliberate failure or detected runtime anomaly."""
        failure_entry = {
            "failure_id": f"fail_{uuid.uuid4().hex[:8]}",
            "task_id": task_id,
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "application": application,
            "failure_type": failure_type,
            "reason": reason,
            "details": details or {}
        }
        self._failures.append(failure_entry)
        self._save_failures()
        return failure_entry

    def _save_action_traces(self):
        try:
            with open(ACTION_TRACE_FILE, "w", encoding="utf-8") as f:
                json.dump({"total_actions": len(self._action_traces), "traces": self._action_traces}, f, indent=2)
        except Exception:
            pass

    def _save_inspection_traces(self):
        try:
            with open(INSPECTION_TRACE_FILE, "w", encoding="utf-8") as f:
                json.dump({"total_inspections": len(self._inspection_traces), "traces": self._inspection_traces}, f, indent=2)
        except Exception:
            pass

    def _save_failures(self):
        try:
            with open(FAILURES_FILE, "w", encoding="utf-8") as f:
                json.dump({"total_failures": len(self._failures), "failures": self._failures}, f, indent=2)
        except Exception:
            pass


ui_tracer = UIAutomationTracer()
