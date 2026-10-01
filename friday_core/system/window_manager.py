"""
F.R.I.D.A.Y. 3.0 — Centralized Desktop App Window Manager & Lifecycle Controller
Zero-Trust Window Reuse & Idempotent Application Lifecycle Management.

Enforces:
1. Idempotent app launching: Detects and reuses existing application windows.
2. Single-flight per-app concurrency locking: Serializes launch operations to prevent race conditions.
3. Execution-level anti-duplication guard: Limits automatic launch attempts to maximum 1 per operation.
4. Window ownership binding: Records PID, HWND, process name, window title, class name, creation time.
5. Deterministic target window selection: Foreground > Interacted > Active > Lowest PID.
6. Robust focus verification: Restores, switches foreground, and verifies GetForegroundWindow() == target_hwnd.
7. Scoped retry logic: Never relaunches an application process merely because focus or typing failed.
"""

import os
import re
import time
import logging
import threading
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple

from friday_core.platform_guard import IS_WINDOWS

logger = logging.getLogger("FRIDAY.WindowManager")

if IS_WINDOWS:
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        HAS_WIN32 = True

        user32.OpenDesktopW.restype = ctypes.c_void_p
        user32.OpenDesktopW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_bool, ctypes.c_uint]
        user32.OpenInputDesktop.restype = ctypes.c_void_p
        user32.OpenInputDesktop.argtypes = [ctypes.c_uint, ctypes.c_bool, ctypes.c_uint]
        user32.SetThreadDesktop.restype = ctypes.c_bool
        user32.SetThreadDesktop.argtypes = [ctypes.c_void_p]

        user32.IsWindow.restype = ctypes.c_bool
        user32.IsWindow.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = ctypes.c_bool
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowEnabled.restype = ctypes.c_bool
        user32.IsWindowEnabled.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = ctypes.c_bool
        user32.IsIconic.argtypes = [wintypes.HWND]

        user32.ShowWindow.restype = ctypes.c_bool
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetForegroundWindow.restype = ctypes.c_bool
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetForegroundWindow.argtypes = []
        user32.BringWindowToTop.restype = ctypes.c_bool
        user32.BringWindowToTop.argtypes = [wintypes.HWND]

        user32.SwitchToThisWindow.restype = None
        # Note: Do not set SwitchToThisWindow.argtypes as uiautomation passes c_void_p / c_int

        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.GetClassNameW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]

        user32.GetWindowRect.restype = ctypes.c_bool
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]

        user32.AttachThreadInput.restype = ctypes.c_bool
        user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, ctypes.c_bool]
        user32.AllowSetForegroundWindow.restype = ctypes.c_bool
        user32.AllowSetForegroundWindow.argtypes = [ctypes.c_int]
        user32.GetAncestor.restype = wintypes.HWND
        # Note: Do not set GetAncestor.argtypes as uiautomation passes c_void_p / c_int
    except Exception as ex:
        logger.warning(f"Win32 initialization error in WindowManager: {ex}")
        HAS_WIN32 = False
else:
    HAS_WIN32 = False


def ensure_interactive_desktop() -> bool:
    """Attaches calling thread to active user input desktop if running in an isolated desktop."""
    if HAS_WIN32:
        try:
            h_input = user32.OpenInputDesktop(0, False, 0x01FF) or user32.OpenDesktopW("default", 0, False, 0x01FF)
            if h_input:
                res = user32.SetThreadDesktop(h_input)
                return bool(res)
        except Exception as ex:
            logger.debug(f"WindowManager desktop attach note: {ex}")
    return False


def run_on_interactive_desktop(func, *args, **kwargs):
    """
    Executes a callable on the interactive user desktop.

    If the current thread is already attached to the interactive desktop (or attaches cleanly),
    runs directly on the current thread.

    If the current thread cannot switch desktops (Win32 Error 170 ERROR_BUSY, which occurs
    when the thread has already initialized UI message loops or audio devices like PySide6
    or pygame.mixer), dispatches execution to a dedicated clean worker thread that attaches
    to the active input desktop.
    """
    if not HAS_WIN32:
        return func(*args, **kwargs)

    # If already running inside an InteractiveDesktopWorker, COM and UIA are already initialized
    if getattr(threading.current_thread(), "_is_interactive_desktop_worker", False):
        return func(*args, **kwargs)

    result_container = []
    exc_container = []

    def _worker():
        setattr(threading.current_thread(), "_is_interactive_desktop_worker", True)
        co_inited = False
        ole32 = getattr(ctypes.windll, "ole32", None)
        try:
            # Desktop MUST be switched BEFORE CoInitialize, otherwise COM window creation causes Error 170 (ERROR_BUSY)
            ensure_interactive_desktop()
            if ole32:
                hr = ole32.CoInitialize(None)
                co_inited = (hr >= 0)
            try:
                import uiautomation as _auto
                has_auto = True
            except Exception:
                has_auto = False

            if has_auto:
                with _auto.UIAutomationInitializerInThread():
                    res = func(*args, **kwargs)
                    result_container.append(res)
            else:
                res = func(*args, **kwargs)
                result_container.append(res)
        except Exception as e:
            exc_container.append(e)
        finally:
            if co_inited and ole32:
                try:
                    ole32.CoUninitialize()
                except Exception:
                    pass

    desktop_timeout = kwargs.pop("desktop_timeout", 180.0)
    worker_name = f"InteractiveDesktopWorker_{getattr(func, '__name__', 'task')}"
    t = threading.Thread(target=_worker, daemon=True, name=worker_name)
    t.start()
    t.join(timeout=desktop_timeout)

    if exc_container:
        raise exc_container[0]
    if result_container:
        return result_container[0]

    # Worker timed out: NEVER re-run concurrently on main thread as that causes disastrous duplicate keystroke collisions
    logger.error(f"Execution on interactive desktop timed out after {desktop_timeout}s.")
    return (False, f"Operation timed out after {desktop_timeout}s.", 0) if "keystroke" in getattr(func, "__name__", "") else None



@dataclass
class WindowTarget:
    hwnd: int
    pid: int
    process_name: str
    title: str
    class_name: str
    rect: Tuple[int, int, int, int]  # (left, top, right, bottom)
    is_minimized: bool
    is_foreground: bool
    create_time: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hwnd": self.hwnd,
            "pid": self.pid,
            "process_name": self.process_name,
            "title": self.title,
            "class_name": self.class_name,
            "rect": list(self.rect),
            "is_minimized": self.is_minimized,
            "is_foreground": self.is_foreground,
            "create_time": self.create_time,
        }


class AppWindowManager:
    """
    Centralized, thread-safe, idempotent application window manager.
    Prevents duplicate process spawns and guarantees single target binding.
    """

    def __init__(self):
        self._global_lock = threading.RLock()
        self._app_launch_locks: Dict[str, threading.RLock] = {}
        self._operation_launches: Dict[str, int] = {}
        self._operation_targets: Dict[str, WindowTarget] = {}
        self._last_interacted_hwnd: Dict[str, int] = {}

    def _get_app_lock(self, app_name: str) -> threading.RLock:
        """Returns or creates a per-application single-flight lock."""
        clean = self.normalize_app_name(app_name)
        with self._global_lock:
            if clean not in self._app_launch_locks:
                self._app_launch_locks[clean] = threading.RLock()
            return self._app_launch_locks[clean]

    @staticmethod
    def normalize_app_name(app_name: str) -> str:
        """Normalizes conversational or filename inputs into canonical application keys."""
        q = (app_name or "").lower().strip()
        q = re.sub(r"^(open|launch|start|run|my|the)\s+", "", q).strip()
        q = q.replace(".exe", "").replace(" ", "").replace("_", "").replace("-", "")

        aliases = {
            "notepad": "notepad",
            "note pad": "notepad",
            "calculator": "calculator",
            "calc": "calculator",
            "code": "vscode",
            "vscode": "vscode",
            "visualstudiocode": "vscode",
            "word": "word",
            "msword": "word",
            "microsoftword": "word",
            "winword": "word",
            "chrome": "chrome",
            "googlechrome": "chrome",
            "edge": "edge",
            "msedge": "edge",
            "microsoftedge": "edge",
            "explorer": "explorer",
            "fileexplorer": "explorer",
            "cmd": "cmd",
            "commandprompt": "cmd",
            "powershell": "powershell",
            "terminal": "terminal",
            "taskmanager": "taskmgr",
            "taskmgr": "taskmgr",
        }
        return aliases.get(q, q)

    def find_matching_windows(self, app_name: str) -> List[WindowTarget]:
        """
        Scans all top-level windows on the interactive desktop and returns
        matching target windows for the given application.
        """
        return run_on_interactive_desktop(self._find_matching_windows_impl, app_name)

    def _find_matching_windows_impl(self, app_name: str) -> List[WindowTarget]:
        if not HAS_WIN32:
            return []

        ensure_interactive_desktop()
        clean = self.normalize_app_name(app_name)
        targets: List[WindowTarget] = []

        import psutil

        fg_hwnd = user32.GetForegroundWindow()
        fg_root = user32.GetAncestor(fg_hwnd, 2) if (fg_hwnd and user32.IsWindow(fg_hwnd)) else 0
        fg_pid = wintypes.DWORD()
        if fg_hwnd:
            user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(fg_pid))

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def enum_cb(hwnd, lparam):
            if not user32.IsWindow(hwnd):
                return True
            # Must be visible or minimized (iconic)
            is_vis = bool(user32.IsWindowVisible(hwnd))
            is_min = bool(user32.IsIconic(hwnd))
            if not (is_vis or is_min):
                return True

            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top

            # Filter out zero-size or offscreen ghost windows unless minimized
            if not is_min and (w < 80 or h < 60):
                return True

            # Extract window text
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()

            # Extract class name
            cbuf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cbuf, 256)
            cname = cbuf.value.strip()

            # Ignore tooltips, IME, overlays, and taskbar
            ignored_classes = {
                "Shell_TrayWnd", "Progman", "WorkerW", "IME", "MSCTFIME UI",
                "tooltips_class32", "TopLevelWindowForOverflowXamlIsland",
                "CEF-OSC-WIDGET", "UAC_InputIndicatorOverlayWnd", "GDI+ Window"
            }
            if cname in ignored_classes:
                return True

            # Extract PID and process name
            pid_val = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_val))
            pid = pid_val.value
            pname = "unknown"
            create_time = 0.0
            try:
                proc = psutil.Process(pid)
                pname = proc.name()
                create_time = proc.create_time()
            except Exception:
                pass

            pname_lower = pname.lower()
            title_lower = title.lower()
            cname_lower = cname.lower()

            match = False

            if clean == "notepad":
                # Windows 11 / classic Notepad: process MUST be notepad.exe or class "Notepad" (excluding IDEs/browsers)
                is_notepad_proc = (pname_lower == "notepad.exe")
                is_notepad_class = (cname == "Notepad" and not any(x in pname_lower for x in ("code", "antigravity", "chrome", "edge", "devenv")))
                is_notepad_title = ("notepad" in title_lower and not any(x in pname_lower for x in ("code", "antigravity", "chrome", "edge", "devenv")))
                if (is_notepad_proc or is_notepad_class or is_notepad_title) and (is_min or (rect.left > -10000 and rect.top > -10000)):
                    match = True
            elif clean == "calculator":
                if ("calculator" in title_lower) or (cname in ("ApplicationFrameWindow", "CalcFrame") and "calc" in title_lower) or ("calculator" in pname_lower):
                    match = True
            elif clean == "vscode":
                if ("visual studio code" in title_lower) or ("code - " in title_lower) or (pname_lower == "code.exe" and "code" in title_lower):
                    match = True
            elif clean == "word":
                if ("word" in title_lower and not "wordpad" in title_lower) or (cname in ("OpusApp", "Word") or pname_lower == "winword.exe"):
                    match = True
            elif clean == "chrome":
                if ("google chrome" in title_lower) or (pname_lower == "chrome.exe" and title):
                    match = True
            elif clean == "edge":
                if ("edge" in title_lower) or (pname_lower == "msedge.exe" and title):
                    match = True
            elif clean == "explorer":
                if (cname == "CabinetWClass") or ("file explorer" in title_lower):
                    match = True
            else:
                # Generic match
                if clean in title_lower or clean in pname_lower or clean in cname_lower:
                    match = True

            if match:
                targets.append(WindowTarget(
                    hwnd=hwnd,
                    pid=pid,
                    process_name=pname,
                    title=title,
                    class_name=cname,
                    rect=(rect.left, rect.top, rect.right, rect.bottom),
                    is_minimized=is_min,
                    is_foreground=(hwnd == fg_hwnd or (fg_root and hwnd == fg_root) or (fg_pid.value != 0 and pid == fg_pid.value)),
                    create_time=create_time
                ))

            return True

        try:
            cb_func = WNDENUMPROC(enum_cb)
            user32.EnumWindows(cb_func, 0)
        except Exception as ex:
            logger.warning(f"Error enumerating windows for '{app_name}': {ex}")

        return targets

    def select_target_window(
        self,
        candidates: List[WindowTarget],
        app_name: str = "",
        preferred_title: Optional[str] = None
    ) -> Optional[WindowTarget]:
        """
        Deterministically selects exactly ONE target window from candidate list:
        1. Explicit title match if requested.
        2. Currently foreground matching window.
        3. Most recently interacted matching window.
        4. Normal (non-minimized) window over minimized.
        5. Most recently created process.
        """
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        # 1. Preferred title match
        if preferred_title:
            pt_clean = preferred_title.lower().strip()
            for cand in candidates:
                if pt_clean in cand.title.lower():
                    return cand

        # 2. Currently foreground window
        for cand in candidates:
            if cand.is_foreground:
                return cand

        # 3. Most recently interacted window
        clean = self.normalize_app_name(app_name)
        last_hwnd = self._last_interacted_hwnd.get(clean)
        if last_hwnd:
            for cand in candidates:
                if cand.hwnd == last_hwnd:
                    return cand

        # 4. Prefer visible / non-minimized
        normal_cands = [c for c in candidates if not c.is_minimized]
        if normal_cands:
            # Sort by creation time (most recent first)
            normal_cands.sort(key=lambda c: c.create_time, reverse=True)
            return normal_cands[0]

        # Fallback to first candidate
        candidates.sort(key=lambda c: c.create_time, reverse=True)
        return candidates[0]

    def focus_window_verified(self, hwnd: int, timeout: float = 1.2) -> bool:
        """
        Focuses target window and verifies it becomes the active foreground window.
        DOES NOT launch any processes on focus failure.
        """
        return run_on_interactive_desktop(self._focus_window_verified_impl, hwnd, timeout)

    def _focus_window_verified_impl(self, hwnd: int, timeout: float = 1.2) -> bool:
        if not HAS_WIN32 or not hwnd or not user32.IsWindow(hwnd):
            return False

        ensure_interactive_desktop()

        # If child control HWND was passed, resolve to root top-level window (GA_ROOT = 2)
        try:
            root_hwnd = user32.GetAncestor(hwnd, 2)
            if root_hwnd and user32.IsWindow(root_hwnd):
                hwnd = root_hwnd
        except Exception:
            pass

        SW_RESTORE = 9
        SW_SHOW = 5
        HWND_TOP = 0
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040

        # Step 1: Restore if minimized
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.05)
        else:
            user32.ShowWindow(hwnd, SW_SHOW)

        # Step 2: Thread attachment & SwitchToThisWindow
        try:
            user32.AllowSetForegroundWindow(-1)
            fore_hwnd = user32.GetForegroundWindow()
            p_dummy = wintypes.DWORD()
            fore_tid = user32.GetWindowThreadProcessId(fore_hwnd, ctypes.byref(p_dummy))
            curr_tid = kernel32.GetCurrentThreadId()
            target_tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p_dummy))

            if fore_tid and fore_tid != curr_tid:
                user32.AttachThreadInput(curr_tid, fore_tid, True)
            if target_tid and target_tid != curr_tid:
                user32.AttachThreadInput(curr_tid, target_tid, True)

            # Bring to top and switch
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.SwitchToThisWindow(hwnd, True)

            if fore_tid and fore_tid != curr_tid:
                user32.AttachThreadInput(curr_tid, fore_tid, False)
            if target_tid and target_tid != curr_tid:
                user32.AttachThreadInput(curr_tid, target_tid, False)
        except Exception as ex:
            logger.debug(f"Focus thread attachment error: {ex}")
            try:
                user32.SwitchToThisWindow(hwnd, True)
            except Exception:
                pass

        # Step 3: Loop verification
        target_pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(target_pid))

        t0 = time.time()
        while time.time() - t0 <= timeout:
            fg = user32.GetForegroundWindow()
            if fg == hwnd:
                return True
            if fg:
                root = user32.GetAncestor(fg, 2)
                if root == hwnd:
                    return True
                fg_pid = ctypes.wintypes.DWORD()
                user32.GetWindowThreadProcessId(fg, ctypes.byref(fg_pid))
                if target_pid.value != 0 and fg_pid.value == target_pid.value:
                    return True
            # Re-attempt SwitchToThisWindow
            user32.SwitchToThisWindow(hwnd, True)
            time.sleep(0.05)

        # Final check
        fg = user32.GetForegroundWindow()
        if fg == hwnd or (fg and user32.GetAncestor(fg, 2) == hwnd):
            return True
        fg_pid = ctypes.wintypes.DWORD()
        if fg:
            user32.GetWindowThreadProcessId(fg, ctypes.byref(fg_pid))
        return bool(fg and target_pid.value != 0 and fg_pid.value == target_pid.value)

    def get_or_launch_window(
        self,
        app_name: str,
        operation_id: Optional[str] = None,
        force_new: bool = False,
        timeout: float = 6.0
    ) -> Tuple[bool, Optional[WindowTarget], bool, str]:
        """
        Idempotent app window provider.
        Under per-app single-flight lock:
        1. Checks if a valid matching window already exists.
        2. If YES: focuses and returns it (reused=True, NO new process).
        3. If NO: checks anti-duplication guard (max 1 launch per operation_id).
        4. Launches exactly ONE instance, polls/waits for the window, binds and focuses.

        Returns: (success: bool, target: Optional[WindowTarget], was_reused: bool, message: str)
        """
        clean = self.normalize_app_name(app_name)
        if not clean:
            return False, None, False, "Invalid empty application name."

        lock = self._get_app_lock(clean)
        with lock:
            ensure_interactive_desktop()

            # 0. Check if target is already bound to this operation (Target Binding Contract)
            if operation_id and operation_id in self._operation_targets:
                bound = self._operation_targets[operation_id]
                if bound and user32 and user32.IsWindow(bound.hwnd):
                    bound_norm = self.normalize_app_name(bound.process_name)
                    if bound_norm == clean or clean in bound.title.lower():
                        self.focus_window_verified(bound.hwnd)
                        self._last_interacted_hwnd[clean] = bound.hwnd
                        msg = f"Reused bound target for operation '{operation_id}' (HWND={bound.hwnd}, PID={bound.pid})."
                        logger.info(f"[WindowManager]: {msg}")
                        return True, bound, True, msg

            # 1. Check existing window (Idempotency)
            if not force_new:
                existing = self.find_matching_windows(clean)
                if existing:
                    target = self.select_target_window(existing, app_name=clean)
                    if target:
                        self.focus_window_verified(target.hwnd)
                        self._last_interacted_hwnd[clean] = target.hwnd
                        if operation_id:
                            self._operation_targets[operation_id] = target
                        msg = f"Reused existing {target.process_name} window (HWND={target.hwnd}, PID={target.pid})."
                        logger.info(f"[WindowManager]: {msg}")
                        return True, target, True, msg

            # 2. Anti-duplication guard: max 1 automatic launch attempt per operation_id
            op_key = operation_id or f"unbound_{clean}_{time.time()}"
            launch_count = self._operation_launches.get(op_key, 0)
            if launch_count >= 1:
                msg = f"LAUNCH_ATTEMPT_LIMIT_EXCEEDED: Operation '{op_key}' already performed {launch_count} launch attempt(s). Relaunch prevented."
                logger.warning(f"[WindowManager]: {msg}")
                return False, None, False, msg

            self._operation_launches[op_key] = launch_count + 1

            # 3. Launch exactly ONE instance
            logger.info(f"[WindowManager]: No existing window for '{clean}'. Launching exactly ONE instance (attempt 1/1)...")
            from friday_core.system.launcher import safe_launch

            if clean == "notepad":
                # Windows 11 modern Notepad: shell:AppsFolder provides reliable interactive GUI window
                safe_launch(r"shell:AppsFolder\Microsoft.WindowsNotepad_8wekyb3d8bbwe!App")
            elif clean == "calculator":
                safe_launch("calc.exe")
            elif clean == "vscode":
                from friday_core.system.launcher import bring_or_launch_vscode
                bring_or_launch_vscode()
            elif clean == "word":
                from friday_core.system.office import open_blank_word
                open_blank_word()
            else:
                from friday_core.system.launcher import launch_application
                launch_application(app_name, raw_launch=True)

            # 4. Wait / poll for top-level window to appear and bind
            t0 = time.time()
            while time.time() - t0 <= timeout:
                time.sleep(0.15)
                wins = self.find_matching_windows(clean)
                if wins:
                    target = self.select_target_window(wins, app_name=clean)
                    if target:
                        self.focus_window_verified(target.hwnd)
                        self._last_interacted_hwnd[clean] = target.hwnd
                        if operation_id:
                            self._operation_targets[operation_id] = target
                        msg = f"Launched and bound {target.process_name} (HWND={target.hwnd}, PID={target.pid})."
                        logger.info(f"[WindowManager]: {msg}")
                        return True, target, False, msg

            msg = f"LAUNCH_FAILED: Timed out waiting {timeout}s for '{clean}' window to appear."
            logger.error(f"[WindowManager]: {msg}")
            return False, None, False, msg

    def get_bound_target(self, operation_id: str) -> Optional[WindowTarget]:
        """Retrieves target window previously bound to an operation."""
        return self._operation_targets.get(operation_id)


# Global singleton
window_manager = AppWindowManager()
