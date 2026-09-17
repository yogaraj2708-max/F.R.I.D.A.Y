"""
F.R.I.D.A.Y. 2.0 - Security Action Gatekeeper
Single Choke Point for all Operating System & Environmental Interactions.
Implements 4-Tier Permission Classification, Windows Recycle Bin routing,
sliding-window rate limiting, path fencing, panic switch, and JSONL audit logging.
"""

import os
import sys
import json
import time
import uuid
import ctypes
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from friday_core.platform_guard import IS_WINDOWS
from friday_core.settings import settings, APP_DATA_DIR
from friday_core.gatekeeper.models import ActionIntent, ActionResult
from friday_core.system.launcher import safe_launch, launch_application
from friday_core.system.telemetry import get_battery_info, get_memory_info, adjust_volume

logger = logging.getLogger("FRIDAY.Gatekeeper")

AUDIT_LOG_FILE = APP_DATA_DIR / "logs" / "audit.jsonl"
ALLOWLIST_FILE = APP_DATA_DIR / "tier3_allowlist.json"

# Permitted Path Roots for File Modification
ALLOWED_PATH_ROOTS = [
    os.path.expandvars(r"%USERPROFILE%\OneDrive\Desktop"),
    os.path.expandvars(r"%USERPROFILE%\Desktop"),
    os.path.expandvars(r"%USERPROFILE%\OneDrive\Documents"),
    os.path.expandvars(r"%USERPROFILE%\Documents"),
    os.path.expandvars(r"%USERPROFILE%\Downloads"),
    os.path.expandvars(r"%USERPROFILE%\OneDrive\Pictures"),
    os.path.expandvars(r"%USERPROFILE%\Pictures"),
    os.path.expandvars(r"%USERPROFILE%\Videos"),
    os.path.expandvars(r"%USERPROFILE%\Music"),
    str(APP_DATA_DIR)
]

TIER_0_ACTIONS = {"get_telemetry", "get_weather", "get_time", "get_date", "calculate", "list_files", "status"}
TIER_1_ACTIONS = {"open_app", "open_url", "open_file", "organize_files", "adjust_volume", "screenshot", "lock_workstation", "save_note"}
TIER_2_ACTIONS = {"delete_file", "move_file", "kill_process", "write_file", "change_setting"}
TIER_3_ACTIONS = {"format_drive", "shell_exec", "elevate_admin", "shutdown", "restart", "download_and_exec", "registry_write"}

class ActionGatekeeper:
    """Security Gatekeeper enforcing authorization and safety policies."""

    def __init__(self):
        self._action_history: List[float] = []  # Timestamps for rate limiting
        self._max_destructive_per_min = 3
        AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    def classify_tier(self, intent: ActionIntent) -> int:
        """Determines the safety tier for an incoming intent."""
        if intent.tier is not None:
            return intent.tier
        action = intent.action.lower()
        if action in TIER_0_ACTIONS:
            return 0
        if action in TIER_1_ACTIONS:
            return 1
        if action in TIER_2_ACTIONS:
            return 2
        if action in TIER_3_ACTIONS:
            return 3
        return 2  # Conservative default for unknown actions

    def get_dry_run_preview(self, intent: ActionIntent) -> str:
        """Produces a plain-language explanation of the proposed operation."""
        action = intent.action.lower()
        t = intent.target
        if action == "delete_file":
            return f"This will safely move file '{t}' to the Windows Recycle Bin (recoverable)."
        if action == "move_file":
            dest = intent.params.get("destination", "unknown")
            return f"This will move '{t}' to '{dest}'."
        if action == "kill_process":
            return f"This will force-terminate running process '{t}'."
        if action == "write_file":
            return f"This will create or overwrite file at '{t}'."
        if action == "change_setting":
            return f"This will alter system setting '{t}' to '{intent.params.get('value')}''."
        if action == "open_app":
            return f"This will launch application '{t}' in the active user desktop."
        if action == "open_file":
            return f"This will open file '{t}' in its default application."
        if action == "organize_files":
            return f"This will organize loose files in '{t}' into category folders."
        return f"This will execute system action '{action}' on target '{t}'."

    def is_path_safe(self, target_path: str) -> Tuple[bool, str]:
        """Validates path against path fencing allowlist and rejects '..' traversal."""
        if not target_path:
            return False, "Target path is empty"
        if ".." in target_path:
            return False, "Path contains invalid directory traversal sequences"

        # A plain startswith() comparison treated "C:\\Users\\me\\DesktopBackup"
        # as being inside "C:\\Users\\me\\Desktop", so files outside the fence were
        # deletable. Compare whole path components instead, and resolve symlinks
        # so a link inside an allowed folder cannot point outside it.
        try:
            real_target = os.path.realpath(os.path.abspath(target_path))
        except OSError:
            return False, "Target path could not be resolved"

        for allowed in ALLOWED_PATH_ROOTS:
            if not allowed:
                continue
            try:
                real_allowed = os.path.realpath(os.path.abspath(allowed))
            except OSError:
                continue
            try:
                if os.path.commonpath([real_target, real_allowed]) == real_allowed:
                    return True, "Path is within designated workspace"
            except ValueError:
                # Different drives -- commonpath raises rather than returning "".
                continue

        return False, f"Path '{target_path}' is outside designated safe directories"

    def check_rate_limit(self) -> bool:
        """Enforces a maximum rate on destructive actions."""
        now = time.time()
        # Discard timestamps older than 60 seconds
        self._action_history = [t for t in self._action_history if now - t < 60.0]
        if len(self._action_history) >= self._max_destructive_per_min:
            return False
        self._action_history.append(now)
        return True

    def _send_to_recycle_bin(self, path: str) -> bool:
        """Deletes file cleanly using Windows Shell Recycle Bin with undo capability."""
        if not IS_WINDOWS or not os.path.exists(path):
            return False

        try:
            from ctypes import wintypes
            class SHFILEOPSTRUCTW(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("wFunc", wintypes.UINT),
                    ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR),
                    ("fFlags", wintypes.WORD),
                    ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", wintypes.LPVOID),
                    ("lpszProgressTitle", wintypes.LPCWSTR)
                ]

            FO_DELETE = 0x0003
            FOF_ALLOWUNDO = 0x0040
            FOF_NOCONFIRMATION = 0x0010
            FOF_SILENT = 0x0004

            # Windows Shell API requires double null-terminated string
            double_null_path = os.path.abspath(path) + "\0\0"
            file_op = SHFILEOPSTRUCTW()
            file_op.wFunc = FO_DELETE
            file_op.pFrom = double_null_path
            file_op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT

            res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(file_op))
            return res == 0
        except Exception as e:
            logger.error(f"[Gatekeeper]: Recycle bin deletion error: {e}")
            return False

    def log_audit(self, intent: ActionIntent, result: ActionResult):
        """Appends action record to append-only JSONL audit log."""
        record = {
            "audit_id": result.audit_id,
            "timestamp": result.timestamp,
            "action": intent.action,
            "target": intent.target,
            "params": intent.params,
            "reason": intent.reason,
            "source": intent.source,
            "tier": result.tier,
            "confirmed": intent.confirmed,
            "success": result.success,
            "message": result.message
        }
        try:
            with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.error(f"[Gatekeeper]: Failed writing audit log: {e}")

    def execute_action(self, intent: ActionIntent) -> ActionResult:
        """
        THE ONLY FUNCTION ALLOWED TO TOUCH THE HOST OS.
        Checks permission tier, panic switch, confirmation, rate limiting, and audit logging.
        """
        audit_id = str(uuid.uuid4())[:8]
        tier = self.classify_tier(intent)

        # 1. Panic Switch Guard: If Observe-Only is active, deny Tier 1+
        if settings.get("observe_only", False) and tier > 0:
            res = ActionResult(
                success=False,
                message="Security Alert: F.R.I.D.A.Y. is currently locked in 'Observe Only' panic mode. System mutations refused.",
                tier=tier,
                audit_id=audit_id
            )
            self.log_audit(intent, res)
            return res

        # 2. Tier 3 Guard: Strictly off by default, must be explicitly present in tier3_allowlist.json
        if tier == 3:
            allowed_tier3 = []
            if ALLOWLIST_FILE.exists():
                try:
                    with open(ALLOWLIST_FILE, "r", encoding="utf-8") as f:
                        allowed_tier3 = json.load(f).get("allowed_actions", [])
                except Exception:
                    pass
            if intent.action not in allowed_tier3:
                res = ActionResult(
                    success=False,
                    message=f"Access Denied: Tier 3 action '{intent.action}' is not in local tier3_allowlist.json.",
                    tier=tier,
                    audit_id=audit_id
                )
                self.log_audit(intent, res)
                return res

        # 3. Tier 2 Confirmation & Dry Run
        dry_run = self.get_dry_run_preview(intent)
        if tier == 2 and not intent.confirmed:
            return ActionResult(
                success=False,
                message=f"Confirmation required for Tier 2 action: {dry_run}",
                tier=tier,
                audit_id=audit_id,
                dry_run_text=dry_run,
                requires_confirmation=True
            )

        # 4. Rate Limiting for Destructive Actions
        if tier >= 2:
            if not self.check_rate_limit():
                res = ActionResult(
                    success=False,
                    message="Security Rate Limit: Exceeded maximum allowed destructive actions per minute (3/60s). Operation halted.",
                    tier=tier,
                    audit_id=audit_id
                )
                self.log_audit(intent, res)
                return res

        # 5. Path Fencing for File Operations
        if intent.action in ["delete_file", "move_file", "write_file", "organize_files"]:
            safe, path_msg = self.is_path_safe(intent.target)
            if not safe:
                res = ActionResult(
                    success=False,
                    message=f"Path Security Violation: {path_msg}",
                    tier=tier,
                    audit_id=audit_id
                )
                self.log_audit(intent, res)
                return res

        # 6. ACTION DISPATCHING (The only place touching the OS)
        success = False
        message = ""
        action = intent.action.lower()

        try:
            if action == "open_app":
                success, item_name = launch_application(intent.target)
                message = f"Launched '{item_name}'." if success else f"Could not find application '{intent.target}'."

            elif action == "open_file":
                target_path = intent.target
                if IS_WINDOWS and os.path.exists(target_path):
                    try:
                        os.startfile(target_path)
                        success = True
                        message = f"Opened '{os.path.basename(target_path)}'."
                    except Exception as e:
                        success = False
                        message = f"Failed to open '{target_path}': {e}"
                else:
                    success, item_name = launch_application(target_path)
                    message = f"Opened '{item_name}'." if success else f"Could not find '{target_path}'."

            elif action == "open_url":
                import webbrowser
                success = safe_launch(intent.target)
                if not success:
                    webbrowser.open(intent.target)
                    success = True
                message = f"Opened URL: {intent.target}"

            elif action == "delete_file":
                success = self._send_to_recycle_bin(intent.target)
                message = f"Moved '{intent.target}' to Recycle Bin." if success else f"Failed to recycle '{intent.target}'."

            elif action == "kill_process":
                if IS_WINDOWS:
                    p_name = intent.target
                    if not p_name.endswith(".exe"):
                        p_name += ".exe"
                    cmd = ["taskkill", "/F", "/IM", p_name]
                    proc = subprocess.run(cmd, capture_output=True, text=True)
                    success = proc.returncode == 0
                    message = f"Process '{p_name}' terminated." if success else f"Could not terminate '{p_name}': {proc.stderr.strip()}"
                else:
                    success = False
                    message = "Process control requires Windows host."

            elif action == "adjust_volume":
                adjust_volume(intent.target)
                success = True
                message = f"Adjusted volume: {intent.target}."

            elif action == "screenshot":
                safe_launch("ms-screenclip:")
                success = True
                message = "Snipping tool activated."

            elif action == "lock_workstation":
                if IS_WINDOWS:
                    ctypes.windll.user32.LockWorkStation()
                    success = True
                    message = "Workstation locked."
                else:
                    success = False
                    message = "Locking the workstation requires a Windows host."

            elif action in ["get_telemetry", "status"]:
                bat, chg = get_battery_info()
                mem = get_memory_info()
                success = True
                message = f"Battery: {bat}% ({'Charging' if chg else 'Discharging'}), RAM: {mem}%."

            else:
                success = True
                message = f"Action '{action}' executed."

        except Exception as e:
            logger.error(f"[Gatekeeper]: Execution fault on '{action}': {e}")
            success = False
            message = f"Execution error: {str(e)}"

        result = ActionResult(
            success=success,
            message=message,
            tier=tier,
            audit_id=audit_id,
            dry_run_text=dry_run
        )
        self.log_audit(intent, result)
        return result

# Global singleton Gatekeeper
gatekeeper = ActionGatekeeper()
