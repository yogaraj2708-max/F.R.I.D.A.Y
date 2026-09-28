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
TIER_1_ACTIONS = {"open_app", "close_app", "open_url", "open_file", "organize_files", "adjust_volume", "screenshot", "lock_workstation", "save_note"}
TIER_2_ACTIONS = {"delete_file", "move_file", "kill_process", "write_file", "change_setting"}
TIER_3_ACTIONS = {"format_drive", "shell_exec", "elevate_admin", "shutdown", "restart", "download_and_exec", "registry_write"}

PROTECTED_SYSTEM_PROCESSES = {
    "csrss.exe", "lsass.exe", "services.exe", "smss.exe", "winlogon.exe",
    "wininit.exe", "explorer.exe", "svchost.exe", "dwm.exe", "spoolsv.exe",
    "runtimebroker.exe", "taskhostw.exe", "sihost.exe", "system.exe", "system"
}

class ActionGatekeeper:
    """Security Gatekeeper enforcing authorization and safety policies."""

    def __init__(self):
        self._action_history: List[float] = []  # Timestamps for rate limiting
        self._max_destructive_per_min = 3
        AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    def enable_panic_mode(self):
        """Enables observe-only panic switch immediately locking system mutations."""
        settings.set("observe_only", True)

    def disable_panic_mode(self):
        """Disables panic switch restoring normal operation."""
        settings.set("observe_only", False)

    @property
    def panic_mode(self) -> bool:
        """Returns True if observe-only panic mode is currently active."""
        return bool(settings.get("observe_only", False))

    @property
    def is_panic_mode(self) -> bool:
        """Returns True if observe-only panic mode is currently active."""
        return self.panic_mode

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

        # 4. Fencing for File Operations & System Processes
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

        if intent.action == "kill_process":
            p_name = intent.target.lower().strip()
            if not p_name.endswith(".exe"):
                p_name += ".exe"
            if p_name in PROTECTED_SYSTEM_PROCESSES or intent.target.lower().strip() in PROTECTED_SYSTEM_PROCESSES:
                res = ActionResult(
                    success=False,
                    message=f"Security Violation: Target process '{intent.target}' is a protected Windows system process and cannot be terminated.",
                    tier=tier,
                    audit_id=audit_id
                )
                self.log_audit(intent, res)
                return res

        # 5. Rate Limiting for Destructive Actions
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

            elif action == "close_app":
                if not IS_WINDOWS:
                    success = False
                    message = "Application termination requires Windows host."
                else:
                    target_raw = (intent.target or "").strip()
                    clean_target = target_raw.lower().replace(".exe", "").strip()

                    app_aliases = {
                        "notepad": ["notepad.exe"],
                        "notes": ["notepad.exe"],
                        "calc": ["calculatorapp.exe", "calculator.exe", "calc.exe"],
                        "calculator": ["calculatorapp.exe", "calculator.exe", "calc.exe"],
                        "wordpad": ["wordpad.exe"],
                        "word": ["winword.exe"],
                        "excel": ["excel.exe"],
                        "chrome": ["chrome.exe"],
                        "edge": ["msedge.exe"],
                        "explorer": ["explorer.exe"],
                        "file explorer": ["explorer.exe"]
                    }
                    candidate_exes = app_aliases.get(clean_target, [f"{clean_target}.exe"])

                    # Protected Process Guard
                    is_protected = False
                    for exe in candidate_exes:
                        if exe in PROTECTED_SYSTEM_PROCESSES and clean_target not in ("explorer", "file explorer"):
                            is_protected = True
                            success = False
                            message = f"Security Violation: Target process '{exe}' is a protected Windows core process and cannot be terminated."
                            logger.error(f"[Gatekeeper] BLOCKED CLOSE ON PROTECTED PROCESS: {exe}")
                            break

                    if not is_protected:
                        if clean_target in ("explorer", "file explorer"):
                            closed_any = False
                            try:
                                import uiautomation as auto
                                windows = auto.GetRootControl().GetChildren()
                                for w in windows:
                                    if w.ClassName == "CabinetWClass" or "file explorer" in w.Name.lower():
                                        w.SendKeys("{Alt}{F4}")
                                        closed_any = True
                                time.sleep(0.5)
                            except Exception:
                                pass
                            success = True
                            message = "File Explorer window closed and verified." if closed_any else "File Explorer is already closed."
                        else:
                            # 1. Locate target processes
                            import psutil
                            matched_procs = []
                            for p in psutil.process_iter(['pid', 'name']):
                                try:
                                    pname = p.info['name'].lower()
                                    if any(pname == cand or pname.replace(".exe", "") == clean_target for cand in candidate_exes):
                                        matched_procs.append(p)
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    continue

                            # Also locate UI app window
                            win = None
                            try:
                                import uiautomation as auto
                                win = auto.WindowControl(searchDepth=2, SubName=clean_target.title())
                                if not win.Exists(0, 0):
                                    win = auto.WindowControl(searchDepth=2, ClassName=clean_target.title())
                                if not win.Exists(0, 0) and clean_target == "notepad":
                                    win = auto.WindowControl(searchDepth=2, SubName="Notepad")
                            except Exception:
                                pass

                            # If psutil didn't match candidate exe name but window exists, grab process from window PID
                            if not matched_procs and win and win.Exists(0, 0):
                                try:
                                    win_pid = win.ProcessId
                                    if win_pid:
                                        p_win = psutil.Process(win_pid)
                                        matched_procs.append(p_win)
                                except Exception:
                                    pass

                            if not matched_procs and (win is None or not win.Exists(0, 0)):
                                # Truly already closed: zero processes and zero windows
                                success = True
                                message = f"Application '{target_raw.title()}' is already closed."
                            else:
                                # 2. Request termination (graceful window close first)
                                if win and win.Exists(0, 0):
                                    try:
                                        win.SendKeys("{Alt}{F4}")
                                        time.sleep(0.2)
                                    except Exception:
                                        pass

                                for p in matched_procs:
                                    try:
                                        p.terminate()
                                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                                        pass

                                # 3. Wait / Observe with Polling (up to 2.0s)
                                t0 = time.time()
                                all_gone = False
                                while time.time() - t0 < 2.0:
                                    alive = []
                                    for p in matched_procs:
                                        try:
                                            if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                                                alive.append(p)
                                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                                            pass
                                    win_alive = win.Exists(0, 0) if win else False
                                    if not alive and not win_alive:
                                        all_gone = True
                                        break
                                    time.sleep(0.15)

                                # Force kill if still lingering
                                if not all_gone:
                                    for p in matched_procs:
                                        try:
                                            if p.is_running():
                                                p.kill()
                                        except Exception:
                                            pass
                                    # Fallback taskkill for Windows store/UWP packaged apps
                                    for exe in candidate_exes:
                                        try:
                                            subprocess.run(["taskkill", "/F", "/T", "/IM", exe], capture_output=True, timeout=2.0)
                                        except Exception:
                                            pass
                                    time.sleep(0.3)

                                # 4. Rigorous Postcondition Verification Check
                                alive_final = [p for p in matched_procs if p.is_running()]
                                win_still_open = False
                                try:
                                    if win and win.Exists(0, 0):
                                        win_still_open = True
                                except Exception:
                                    pass

                                if not alive_final and not win_still_open:
                                    success = True
                                    message = f"Application '{target_raw.title()}' closed and verified terminated."
                                else:
                                    success = False
                                    message = f"Failed to close '{target_raw.title()}': Target process or window is still running."

            elif action == "kill_process":
                if IS_WINDOWS:
                    p_name = intent.target.lower().strip()
                    if not p_name.endswith(".exe"):
                        p_name += ".exe"
                    if p_name in PROTECTED_SYSTEM_PROCESSES or intent.target.lower().strip() in PROTECTED_SYSTEM_PROCESSES:
                        success = False
                        message = f"Security Violation: Target process '{intent.target}' is a protected Windows system process and cannot be terminated."
                        logger.error(f"[Gatekeeper] BLOCKED CRITICAL SYSTEM KILL: {intent.target}")
                    else:
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
                from friday_core.skills.builtins.desktop_action import capture_and_save_screenshot
                target_p = Path(intent.target) if intent.target and os.path.exists(intent.target) else None
                shot_path = capture_and_save_screenshot(target_dir=target_p)
                if shot_path and os.path.exists(shot_path):
                    success = True
                    message = f"Screenshot captured and saved to '{shot_path}'."
                else:
                    success = False
                    message = "Screenshot capture failed."

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
