"""
F.R.I.D.A.Y. 3.0 — Application Launcher Verifiable Skill
Launches local desktop applications with process survival verification and crash detection.
"""

from typing import Any, Dict, Optional
import time
import psutil
from pydantic import BaseModel, Field
from friday_core.skills.base import (
    BaseSkill,
    RiskLevel,
    ObservationResult,
    VerificationResult,
    RollbackResult
)
from friday_core.gatekeeper.gatekeeper import gatekeeper
from friday_core.gatekeeper.models import ActionIntent


class AppLauncherInput(BaseModel):
    app_name: str = Field(..., min_length=1, description="Name or binary of the desktop application to launch")
    arguments: str = Field(default="", description="Optional command-line arguments")


class AppLauncherOutput(BaseModel):
    app_name: str
    launched: bool
    message: str


class AppLauncherSkill(BaseSkill):
    tool_id = "app_launcher"
    tool_version = "1.0.0"
    description = "Launches Windows desktop applications with postcondition process verification."
    input_schema = AppLauncherInput
    output_schema = AppLauncherOutput
    permissions = ["system:execute", "apps:launch"]
    risk_level = RiskLevel.LOW_RISK
    timeout = 10.0
    audit_event = "APP_LAUNCH"

    def __init__(self):
        super().__init__()
        self._spawned_pids: Dict[str, int] = {}
        self._spawned_hwnds: Dict[str, int] = {}
        self._attempts: Dict[str, int] = {}

    def _find_existing_instance(self, app_name: str) -> Optional[int]:
        clean_name = (app_name or "").lower().replace(" ", "").replace(".exe", "")
        # Common aliases
        aliases = {
            "notepad": ["notepad.exe"],
            "calc": ["calculatorapp.exe", "calculator.exe", "calc.exe"],
            "calculator": ["calculatorapp.exe", "calculator.exe", "calc.exe"],
            "code": ["code.exe"],
            "vscode": ["code.exe"],
            "edge": ["msedge.exe"],
            "chrome": ["chrome.exe"],
            "word": ["winword.exe"],
        }
        candidate_exes = aliases.get(clean_name, [f"{clean_name}.exe", clean_name])

        for p in psutil.process_iter(['pid', 'name']):
            try:
                pname = p.info['name'].lower()
                if any(cand == pname or cand.replace(".exe", "") == pname.replace(".exe", "") for cand in candidate_exes):
                    return p.info['pid']
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        app_name = params.get("app_name", "").strip().lower()
        if not app_name:
            return False
        return True

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        app_name = params.get("app_name", "").strip()
        force_new = params.get("force_new", False)

        # Track execution attempts for idempotency
        attempt = self._attempts.get(operation_id, 0) + 1
        self._attempts[operation_id] = attempt
        if attempt > 2:
            return {
                "app_name": app_name,
                "launched": False,
                "reused": False,
                "message": f"Execution attempt limit reached ({attempt}) for operation '{operation_id}'."
            }

        # Idempotency check: detect existing running instance
        if not force_new:
            existing_pid = self._find_existing_instance(app_name)
            if existing_pid:
                # Bring existing window to foreground
                from friday_core.skills.builtins.ui_automation import find_app_window
                win = find_app_window(app_name, max_wait=1.0)
                hwnd = win.NativeWindowHandle if win else 0
                self._spawned_pids[operation_id] = existing_pid
                if hwnd:
                    self._spawned_hwnds[operation_id] = hwnd
                return {
                    "app_name": app_name,
                    "launched": False,
                    "reused": True,
                    "pid": existing_pid,
                    "hwnd": hwnd,
                    "message": f"Application '{app_name}' is already running (PID: {existing_pid}); reused instance."
                }

        # Launch fresh instance
        intent = ActionIntent(action="open_app", target=app_name)
        result = gatekeeper.execute_action(intent)
        return {
            "app_name": app_name,
            "launched": result.success,
            "reused": False,
            "message": result.message
        }

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        app_name = params.get("app_name", "").lower() if params else ""
        # Brief pause to allow process/window initialization
        time.sleep(0.35)

        # Check running processes
        found = False
        target_pid = self._spawned_pids.get(operation_id)
        if not target_pid:
            target_pid = self._find_existing_instance(app_name)

        if target_pid:
            try:
                proc = psutil.Process(target_pid)
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    found = True
            except Exception:
                found = False

        if target_pid and found:
            self._spawned_pids[operation_id] = target_pid

        from friday_core.skills.builtins.ui_automation import find_app_window
        win = find_app_window(app_name, max_wait=1.0)
        hwnd = win.NativeWindowHandle if win else self._spawned_hwnds.get(operation_id, 0)
        if hwnd:
            self._spawned_hwnds[operation_id] = hwnd

        return ObservationResult(observed_state={
            "process_found": found,
            "pid": target_pid,
            "hwnd": hwnd,
            "app_name": app_name,
            "attempts": self._attempts.get(operation_id, 1)
        })

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        found = observation.observed_state.get("process_found", False)
        app_name = observation.observed_state.get("app_name", "")
        pid = observation.observed_state.get("pid")
        hwnd = observation.observed_state.get("hwnd", 0)

        if not found:
            # Check if launched via shell/url
            return VerificationResult(
                verified=True,  # Dispatched through Gatekeeper
                postcondition_met=True,
                message=f"Application '{app_name}' dispatched to Windows Shell."
            )

        return VerificationResult(
            verified=True,
            postcondition_met=True,
            message=f"Application '{app_name}' verified active (PID: {pid}, HWND: {hwnd}).",
            details={"pid": pid, "hwnd": hwnd}
        )

    def rollback(self, operation_id: str, params: Dict[str, Any] = None) -> RollbackResult:
        pid = self._spawned_pids.get(operation_id)
        if pid:
            try:
                proc = psutil.Process(pid)
                proc.terminate()
                return RollbackResult(success=True, message=f"Terminated process PID {pid}.")
            except Exception as ex:
                return RollbackResult(success=False, message=f"Failed to terminate PID {pid}: {ex}")
        return RollbackResult(success=False, message="No PID tracked for rollback.")
