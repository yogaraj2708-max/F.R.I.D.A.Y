"""
F.R.I.D.A.Y. 3.0 — Bounded Mouse & Real Keystroke Input Driver
Performs high-precision input interactions and real Windows SendInput keystroke injection.
Distinguishes real keyboard typing from clipboard paste and programmatic ValuePattern injection.
"""

from typing import Tuple, Optional, Callable, List, Any
import ctypes
from ctypes import wintypes
import time
import logging
from friday_core.platform_guard import IS_WINDOWS

try:
    import uiautomation as auto
except Exception:
    auto = None

logger = logging.getLogger("FRIDAY.InputDriver")


# Desktop attachment helper
class InputDesktopScope:
    """Context manager that temporarily attaches the thread to the active user input desktop."""
    def __init__(self):
        self.h_orig = None
        self.h_input = None

    def __enter__(self):
        if IS_WINDOWS and user32:
            try:
                kernel32 = ctypes.windll.kernel32
                self.h_orig = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
                self.h_input = user32.OpenInputDesktop(0, False, 0x01FF)
                if self.h_input:
                    user32.SetThreadDesktop(self.h_input)
            except Exception:
                pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if IS_WINDOWS and user32:
            try:
                if self.h_orig and self.h_input:
                    user32.SetThreadDesktop(self.h_orig)
                    user32.CloseDesktop(self.h_input)
            except Exception:
                pass


# Windows User32 SendInput Structures (64-bit and 32-bit compliant)
if IS_WINDOWS:
    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INPUT_UNION(ctypes.Union):
        _fields_ = [
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
            ("hi", HARDWAREINPUT),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", wintypes.DWORD),
            ("u", _INPUT_UNION),
        ]

    try:
        user32 = ctypes.windll.user32
        user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
        user32.SendInput.restype = wintypes.UINT
    except Exception:
        user32 = None
else:
    user32 = None

# Input Constants
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

# Virtual Key Codes
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_END = 0x23
VK_DELETE = 0x2E
VK_A = 0x41


import threading

_window_input_locks = {}
_locks_mutex = threading.Lock()

def get_window_input_lock(hwnd: Optional[int]) -> threading.Lock:
    """Returns a threading.Lock dedicated to the specified target window handle."""
    with _locks_mutex:
        h = hwnd or 0
        if h not in _window_input_locks:
            _window_input_locks[h] = threading.Lock()
        return _window_input_locks[h]


def send_inputs(inputs: List[Any]) -> int:
    """Dispatches an atomic array of INPUT structures via user32.SendInput."""
    if not IS_WINDOWS or not user32 or not inputs:
        return 0
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    cbSize = ctypes.sizeof(INPUT)
    res = user32.SendInput(n, ctypes.cast(arr, ctypes.c_void_p), cbSize)
    if res == 0:
        # If SendInput failed (e.g. non-interactive thread), retry within scoped input desktop
        with InputDesktopScope():
            res = user32.SendInput(n, ctypes.cast(arr, ctypes.c_void_p), cbSize)
    return res


def send_unicode_char(code_point: int, hold_s: float = 0.002) -> None:
    """Emits real key-down and key-up events for a printable Unicode character with explicit hold delay."""
    inp_down = INPUT(type=INPUT_KEYBOARD)
    inp_down.u.ki.wVk = 0
    inp_down.u.ki.wScan = code_point
    inp_down.u.ki.dwFlags = KEYEVENTF_UNICODE

    send_inputs([inp_down])
    if hold_s > 0:
        time.sleep(hold_s)

    inp_up = INPUT(type=INPUT_KEYBOARD)
    inp_up.u.ki.wVk = 0
    inp_up.u.ki.wScan = code_point
    inp_up.u.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP

    send_inputs([inp_up])


def send_virtual_key(vk: int, extended: bool = False, hold_s: float = 0.005, gap_s: float = 0.035) -> None:
    """Emits real key-down and key-up events for a virtual key code (Enter, Tab, Backspace, Delete)."""
    flags_down = KEYEVENTF_EXTENDEDKEY if extended else 0
    flags_up = (KEYEVENTF_EXTENDEDKEY if extended else 0) | KEYEVENTF_KEYUP
    scan = user32.MapVirtualKeyW(vk, 0) if user32 else 0

    inp_down = INPUT(type=INPUT_KEYBOARD)
    inp_down.u.ki.wVk = vk
    inp_down.u.ki.wScan = scan
    inp_down.u.ki.dwFlags = flags_down

    inp_up = INPUT(type=INPUT_KEYBOARD)
    inp_up.u.ki.wVk = vk
    inp_up.u.ki.wScan = scan
    inp_up.u.ki.dwFlags = flags_up

    send_inputs([inp_down])
    if hold_s > 0:
        time.sleep(hold_s)
    send_inputs([inp_up])
    if gap_s > 0:
        time.sleep(gap_s)


def release_all_modifiers() -> None:
    """Explicitly releases any latched modifier keys (Shift, Ctrl, Alt, Win)."""
    if not IS_WINDOWS or not user32:
        return
    modifiers = [VK_SHIFT, VK_CONTROL, 0x12, 0x5B, 0x5C]  # Shift, Ctrl, Alt, LWin, RWin
    ups = []
    for vk in modifiers:
        scan = user32.MapVirtualKeyW(vk, 0) if user32 else 0
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.u.ki.wVk = vk
        inp.u.ki.wScan = scan
        inp.u.ki.dwFlags = KEYEVENTF_KEYUP
        ups.append(inp)
    send_inputs(ups)


def send_ctrl_a_delete() -> None:
    """Executes real Ctrl+A followed by Delete key to clear content without ValuePattern."""
    release_all_modifiers()

    scan_ctrl = user32.MapVirtualKeyW(VK_CONTROL, 0) if user32 else 0
    scan_a = user32.MapVirtualKeyW(VK_A, 0) if user32 else 0
    scan_del = user32.MapVirtualKeyW(VK_DELETE, 0) if user32 else 0

    # 1. Ctrl down
    inp_ctrl_down = INPUT(type=INPUT_KEYBOARD)
    inp_ctrl_down.u.ki.wVk = VK_CONTROL
    inp_ctrl_down.u.ki.wScan = scan_ctrl
    inp_ctrl_down.u.ki.dwFlags = 0
    send_inputs([inp_ctrl_down])
    time.sleep(0.025)

    # 2. 'A' down
    inp_a_down = INPUT(type=INPUT_KEYBOARD)
    inp_a_down.u.ki.wVk = VK_A
    inp_a_down.u.ki.wScan = scan_a
    inp_a_down.u.ki.dwFlags = 0
    send_inputs([inp_a_down])
    time.sleep(0.020)

    # 3. 'A' up
    inp_a_up = INPUT(type=INPUT_KEYBOARD)
    inp_a_up.u.ki.wVk = VK_A
    inp_a_up.u.ki.wScan = scan_a
    inp_a_up.u.ki.dwFlags = KEYEVENTF_KEYUP
    send_inputs([inp_a_up])
    time.sleep(0.020)

    # 4. Ctrl up (guaranteed release!)
    inp_ctrl_up = INPUT(type=INPUT_KEYBOARD)
    inp_ctrl_up.u.ki.wVk = VK_CONTROL
    inp_ctrl_up.u.ki.wScan = scan_ctrl
    inp_ctrl_up.u.ki.dwFlags = KEYEVENTF_KEYUP
    send_inputs([inp_ctrl_up])
    time.sleep(0.050)

    # 5. Delete (extended key)
    send_virtual_key(VK_DELETE, extended=True, hold_s=0.015, gap_s=0.050)
    time.sleep(0.050)

    release_all_modifiers()


def send_ctrl_end() -> None:
    """Executes real Ctrl+End to move cursor to the end of the document without paste."""
    inp_ctrl_down = INPUT(type=INPUT_KEYBOARD)
    inp_ctrl_down.u.ki.wVk = VK_CONTROL
    inp_ctrl_down.u.ki.dwFlags = 0

    inp_end_down = INPUT(type=INPUT_KEYBOARD)
    inp_end_down.u.ki.wVk = VK_END
    inp_end_down.u.ki.dwFlags = KEYEVENTF_EXTENDEDKEY

    inp_end_up = INPUT(type=INPUT_KEYBOARD)
    inp_end_up.u.ki.wVk = VK_END
    inp_end_up.u.ki.dwFlags = KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP

    inp_ctrl_up = INPUT(type=INPUT_KEYBOARD)
    inp_ctrl_up.u.ki.wVk = VK_CONTROL
    inp_ctrl_up.u.ki.dwFlags = KEYEVENTF_KEYUP

    send_inputs([inp_ctrl_down, inp_end_down, inp_end_up, inp_ctrl_up])
    time.sleep(0.05)


_active_operations = set()
_completed_operations = set()
_op_lock = threading.Lock()


def type_real_keystrokes(
    text: str,
    mode: str = "type",
    typing_delay_ms: float = 5.0,
    hwnd: Optional[int] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    operation_id: Optional[str] = None
) -> Tuple[bool, str, int]:
    """
    Windows-native keyboard injection backend using user32.SendInput.
    Generates REAL KEYBOARD INPUT EVENTS:
    - KEYEVENTF_UNICODE key-down and key-up for printable Unicode characters.
    - Actual Enter key events for newlines.
    - Actual Tab key events for tabs.
    - Actual Backspace key events for backspaces.
    - Ctrl+A then Delete for mode='replace'.
    - Ctrl+End for mode='append'.
    - Focus and target-window safety verified before typing.
    - Dedicated per-window lock preventing concurrent typing collisions.
    - Configurable typing_delay_ms (floor: 36ms).
    """
    if not IS_WINDOWS:
        return False, "SendInput only supported on Windows.", 0

    if not text:
        return True, "Empty text, 0 characters typed.", 0

    op_id = operation_id or f"op_{int(time.time()*1000)}"
    with _op_lock:
        if op_id in _active_operations:
            logger.warning(f"[InputDriver]: operation_id={op_id} typing already active. Rejection duplicate entry.")
            return False, f"Duplicate text-entry rejected for operation_id={op_id}.", 0
        _active_operations.add(op_id)

    logger.info(f"[InputDriver]: operation_id={op_id} typing_started=1")

    try:
        # Guarantee strictly one active text-entry operation per target window
        lock = get_window_input_lock(hwnd)
        with lock:
            from friday_core.system.window_manager import run_on_interactive_desktop
            return run_on_interactive_desktop(
                _type_real_keystrokes_impl,
                text=text,
                mode=mode,
                typing_delay_ms=typing_delay_ms,
                hwnd=hwnd,
                cancel_check=cancel_check
            )
    finally:
        with _op_lock:
            _active_operations.discard(op_id)
            _completed_operations.add(op_id)
        logger.info(f"[InputDriver]: operation_id={op_id} typing_finished=1")


def _type_real_keystrokes_impl(
    text: str,
    mode: str = "type",
    typing_delay_ms: float = 5.0,
    hwnd: Optional[int] = None,
    cancel_check: Optional[Callable[[], bool]] = None
) -> Tuple[bool, str, int]:
    with InputDesktopScope():
        top_hwnd = hwnd
        if hwnd and user32:
            try:
                root_hwnd = user32.GetAncestor(hwnd, 2)  # GA_ROOT = 2
                if root_hwnd and user32.IsWindow(root_hwnd):
                    top_hwnd = root_hwnd
            except Exception:
                pass

        # 1. Focus Safety & Target Window Verification
        if top_hwnd and user32:
            if not user32.IsWindow(top_hwnd):
                return False, f"Target window HWND {top_hwnd} is invalid or closed.", 0
            
            target_pid = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(top_hwnd, ctypes.byref(target_pid))

            def is_target_focused(timeout: float = 0.5) -> bool:
                t0 = time.time()
                while time.time() - t0 <= timeout:
                    fg = user32.GetForegroundWindow()
                    if fg:
                        if fg == top_hwnd or user32.GetAncestor(fg, 2) == top_hwnd:
                            return True
                        fg_pid = ctypes.wintypes.DWORD()
                        user32.GetWindowThreadProcessId(fg, ctypes.byref(fg_pid))
                        if target_pid.value != 0 and fg_pid.value == target_pid.value:
                            return True
                    time.sleep(0.04)
                # If fg is None (0), no foreign window has focus; verify target window is valid and visible
                fg = user32.GetForegroundWindow()
                if not fg and user32.IsWindow(top_hwnd) and user32.IsWindowVisible(top_hwnd):
                    return True
                return False

            if not is_target_focused(timeout=0.2):
                from friday_core.system.window_manager import window_manager
                window_manager.focus_window_verified(top_hwnd)
                time.sleep(0.15)

            if not is_target_focused(timeout=0.6):
                fg = user32.GetForegroundWindow()
                title_buf = ctypes.create_unicode_buffer(256)
                if fg:
                    user32.GetWindowTextW(fg, title_buf, 256)
                return False, f"Focus failed: Target window HWND {top_hwnd} could not be brought to foreground (Current FG HWND={fg}, Title='{title_buf.value}').", 0

        # Locate active edit control if available and ensure focused
        doc = None
        vp = None
        if top_hwnd and auto:
            try:
                root = auto.ControlFromHandle(top_hwnd)
                doc = root.DocumentControl(searchDepth=4)
                if not doc.Exists(0, 0):
                    doc = root.EditControl(searchDepth=4)
                if doc and doc.Exists(0, 0):
                    try:
                        doc.SetFocus()
                    except Exception:
                        pass
                    try:
                        vp = doc.GetValuePattern()
                    except Exception:
                        pass
            except Exception:
                pass

        # 2. Mode Pre-actions using real keystrokes (NOT SetValue, NOT Clipboard)
        release_all_modifiers()
        mode_clean = (mode or "type").lower()
        if mode_clean == "replace":
            if doc and doc.Exists(0, 0):
                try:
                    doc.SetFocus()
                except Exception:
                    pass
                time.sleep(0.10)
            send_ctrl_a_delete()
            time.sleep(0.15)
            # Re-ensure focus on editor after clearing
            if doc and doc.Exists(0, 0):
                try:
                    doc.SetFocus()
                except Exception:
                    pass
                time.sleep(0.15)
        elif mode_clean == "append":
            send_ctrl_end()
            time.sleep(0.08)
        elif mode_clean in ("selection", "replace_selection"):
            send_virtual_key(VK_DELETE, extended=True, hold_s=0.005, gap_s=0.040)
            time.sleep(0.08)

        # 3. Progressive real keystroke typing
        # Standardize CRLF to avoid double newlines when sending VK_RETURN
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        # Enforce minimum delay floor (36.0ms) to ensure Windows 11 RichEdit/XAML frame budget is never starved
        delay_sec = max(0.036, float(typing_delay_ms) / 1000.0)
        punct_chars = set(".<>{}[ ]()%^&*/\\\"';:=-+!@#$?`~|")
        typed_count = 0

        for i, ch in enumerate(normalized):
            # Cancellation check
            if cancel_check and cancel_check():
                release_all_modifiers()
                return False, f"Typing cancelled by user after {typed_count} characters.", typed_count

            # Target window presence check (passive - never steal focus mid-stream!)
            if top_hwnd and user32:
                if not user32.IsWindow(top_hwnd):
                    release_all_modifiers()
                    return False, f"Target window disappeared during keystroke typing after {typed_count} characters.", typed_count

            # Real keyboard event dispatch
            if ch == "\n":
                send_virtual_key(VK_RETURN, hold_s=0.010, gap_s=0.050)
            elif ch == "\t":
                send_virtual_key(VK_TAB, hold_s=0.005, gap_s=0.040)
            elif ch == "\b":
                send_virtual_key(VK_BACK, hold_s=0.005, gap_s=0.040)
            else:
                code_point = ord(ch)
                send_unicode_char(code_point, hold_s=0.002)
                if ch in punct_chars:
                    time.sleep(max(0.045, delay_sec * 1.35))
                else:
                    time.sleep(delay_sec)

            typed_count += 1

        release_all_modifiers()
        return True, f"Successfully typed {typed_count} real keystrokes into target application.", typed_count


class BoundedInputDriver:
    """
    Executes mouse clicks and keyboard typing within verified bounding boxes.
    """
    def click_within_bounds(self, rect: Tuple[int, int, int, int]) -> Tuple[bool, str]:
        """
        Clicks the center of a bounding rectangle (left, top, right, bottom).
        Rejects invalid or unverified bounds.
        """
        if not IS_WINDOWS:
            return False, "Input driver only supported on Windows."

        left, top, right, bottom = rect
        if right <= left or bottom <= top:
            return False, f"Invalid bounding rectangle: {rect}"

        center_x = (left + right) // 2
        center_y = (top + bottom) // 2

        try:
            # Set cursor position
            ctypes.windll.user32.SetCursorPos(center_x, center_y)
            time.sleep(0.04)

            # MOUSEEVENTF_LEFTDOWN = 0x0002, MOUSEEVENTF_LEFTUP = 0x0004
            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.03)
            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)

            return True, f"Clicked within verified bounding rect at ({center_x}, {center_y})."
        except Exception as ex:
            return False, f"Error clicking at ({center_x}, {center_y}): {ex}"

    def type_text(self, text: str, mode: str = "type", typing_delay_ms: float = 5.0, hwnd: Optional[int] = None) -> Tuple[bool, str]:
        """Types string using Windows User32 SendInput real keystrokes."""
        success, msg, _ = type_real_keystrokes(text, mode=mode, typing_delay_ms=typing_delay_ms, hwnd=hwnd)
        return success, msg

    def type_real_keystrokes(
        self,
        text: str,
        mode: str = "type",
        typing_delay_ms: float = 5.0,
        hwnd: Optional[int] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> Tuple[bool, str, int]:
        """Exposes real keystroke injection engine directly on input driver."""
        return type_real_keystrokes(text, mode=mode, typing_delay_ms=typing_delay_ms, hwnd=hwnd, cancel_check=cancel_check)


# Global Singleton Input Driver
input_driver = BoundedInputDriver()
