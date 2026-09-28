"""
F.R.I.D.A.Y. 3.0 — UI Automation & Accessibility Inspector
Zero-Trust Forensic UI Inspection Layer.

Inspects Windows desktop windows, controls, accessibility hierarchies,
bounding rectangles, states, and values. Defends against stale controls.
Never assumes control state without inspection.
"""

import time
import uuid
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("FRIDAY.UIInspector")

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
    user32.IsWindow.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.restype = ctypes.c_bool
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindowEnabled.restype = ctypes.c_bool
    user32.IsWindowEnabled.argtypes = [ctypes.c_void_p]
    user32.IsIconic.restype = ctypes.c_bool
    user32.IsIconic.argtypes = [ctypes.c_void_p]
    user32.ShowWindow.restype = ctypes.c_bool
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.SetForegroundWindow.restype = ctypes.c_bool
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetForegroundWindow.argtypes = []
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextLengthW.argtypes = [ctypes.c_void_p]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
except Exception:
    HAS_WIN32 = False


def ensure_interactive_desktop():
    """
    Attaches calling thread to interactive 'default' user desktop if running in an isolated service/sandbox desktop.
    Must be called before any thread initializes COM or window controls.
    """
    if HAS_WIN32:
        try:
            h_desk = user32.OpenDesktopW("default", 0, False, 0x01FF) or user32.OpenInputDesktop(0, False, 0x01FF)
            if h_desk:
                user32.SetThreadDesktop(h_desk)
        except Exception as ex:
            logger.debug(f"Desktop attach note: {ex}")


# Attach calling thread to default interactive desktop BEFORE importing uiautomation
ensure_interactive_desktop()

try:
    import uiautomation as auto
    HAS_UIA = True
except Exception:
    auto = None
    HAS_UIA = False

from friday_core.automation.tracer import ui_tracer


@dataclass
class UIElementInfo:
    control_type: str
    name: str
    automation_id: str
    bounding_rect: Tuple[int, int, int, int]  # (left, top, right, bottom)
    is_enabled: bool
    is_visible: bool
    current_value: Optional[str] = None
    hwnd: Optional[int] = None
    runtime_id: Optional[Tuple[int, ...]] = None
    class_name: Optional[str] = None
    process_id: Optional[int] = None
    depth: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "control_type": self.control_type,
            "name": self.name,
            "automation_id": self.automation_id,
            "bounding_rect": list(self.bounding_rect),
            "is_enabled": self.is_enabled,
            "is_visible": self.is_visible,
            "current_value": self.current_value,
            "hwnd": self.hwnd,
            "runtime_id": list(self.runtime_id) if self.runtime_id else None,
            "class_name": self.class_name,
            "process_id": self.process_id,
            "depth": self.depth
        }


@dataclass
class WindowInspection:
    window_title: str
    app_name: str
    process_id: int
    process_name: str
    hwnd: int
    is_foreground: bool
    is_visible: bool
    is_enabled: bool
    is_minimized: bool
    bounding_rect: Tuple[int, int, int, int]
    elements: List[UIElementInfo] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    inspection_id: str = field(default_factory=lambda: f"insp_{uuid.uuid4().hex[:8]}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inspection_id": self.inspection_id,
            "timestamp": self.timestamp,
            "window_title": self.window_title,
            "app_name": self.app_name,
            "process_id": self.process_id,
            "process_name": self.process_name,
            "hwnd": self.hwnd,
            "is_foreground": self.is_foreground,
            "is_visible": self.is_visible,
            "is_enabled": self.is_enabled,
            "is_minimized": self.is_minimized,
            "bounding_rect": list(self.bounding_rect),
            "elements_count": len(self.elements),
            "elements": [e.to_dict() for e in self.elements]
        }

    def summary(self) -> str:
        controls_summary = []
        for e in self.elements[:15]:
            desc = f"[{e.control_type}] '{e.name}'"
            if e.automation_id:
                desc += f" (id={e.automation_id})"
            if e.current_value:
                desc += f" value='{e.current_value}'"
            controls_summary.append(desc)
        return (
            f"Window '{self.window_title}' (HWND={self.hwnd}, PID={self.process_id}, App='{self.app_name}', "
            f"Active={self.is_foreground}). Controls ({len(self.elements)} total): "
            + "; ".join(controls_summary)
        )


class UIInspector:
    """
    Zero-trust accessibility and UI inspector for Windows desktop applications.
    """

    def __init__(self):
        self._last_inspections: Dict[int, WindowInspection] = {}

    def is_hwnd_valid(self, hwnd: int) -> bool:
        """Verifies if an HWND is currently valid and not destroyed."""
        if not HAS_WIN32 or not hwnd:
            return False
        try:
            return bool(user32.IsWindow(hwnd))
        except Exception:
            return False

    def is_control_stale(
        self,
        element: Any,
        expected_hwnd: Optional[int] = None,
        cached_rect: Optional[Tuple[int, int, int, int]] = None
    ) -> bool:
        """
        Defends against stale controls:
        1. Checks window existence.
        2. Probes UIA element presence without throwing.
        3. Validates bounding box stability.
        """
        if expected_hwnd is None and hasattr(element, "hwnd") and element.hwnd:
            expected_hwnd = element.hwnd
        if cached_rect is None and hasattr(element, "bounding_rect") and element.bounding_rect:
            cached_rect = element.bounding_rect

        if expected_hwnd and not self.is_hwnd_valid(expected_hwnd):
            return True

        if not element:
            return True

        try:
            # Check COM handle validity
            if hasattr(element, "Exists"):
                if not element.Exists(0, 0):
                    return True

            # Check bounding box
            if cached_rect and hasattr(element, "BoundingRectangle"):
                rect = element.BoundingRectangle
                if rect:
                    current_rect = (rect.left, rect.top, rect.right, rect.bottom)
                    # If element collapsed to (0,0,0,0) or moved wildly, consider stale/invalid
                    if current_rect == (0, 0, 0, 0) and cached_rect != (0, 0, 0, 0):
                        return True
            return False
        except Exception as ex:
            logger.debug(f"Stale control detected via exception: {ex}")
            return True

    def find_window_by_app_name(
        self,
        app_name: str,
        timeout: float = 3.0
    ) -> Optional[Any]:
        """
        Finds target window control reliably across common applications.
        """
        ensure_interactive_desktop()
        if not HAS_UIA or not auto:
            return None

        clean = (app_name or "").lower().replace(" ", "").replace(".exe", "")
        name_map = {
            "notepad": "Notepad",
            "calculator": "Calculator",
            "calc": "Calculator",
            "explorer": "File Explorer",
            "fileexplorer": "File Explorer",
            "chrome": "Google Chrome",
            "googlechrome": "Google Chrome",
            "edge": "Microsoft Edge",
            "msedge": "Microsoft Edge",
            "word": "Word",
            "cmd": "Command Prompt",
            "powershell": "PowerShell",
            "friday": "F.R.I.D.A.Y."
        }
        target_name = name_map.get(clean, app_name)
        t0 = time.time()

        while time.time() - t0 <= timeout:
            # 1. Search by SubName
            win = auto.WindowControl(searchDepth=2, SubName=target_name)
            if win.Exists(0, 0):
                return win

            # 2. Search by known ClassName
            if "notepad" in clean:
                win_class = auto.WindowControl(searchDepth=2, ClassName="Notepad")
                if win_class.Exists(0, 0):
                    return win_class
            elif "explorer" in clean:
                win_class = auto.WindowControl(searchDepth=2, ClassName="CabinetWClass")
                if win_class.Exists(0, 0):
                    return win_class
            elif "calc" in clean:
                win_class = auto.WindowControl(searchDepth=2, ClassName="ApplicationFrameWindow", SubName="Calculator")
                if win_class.Exists(0, 0):
                    return win_class

            # 3. Dual-stage fallback: Enumerate top-level visible windows via Win32
            if HAS_WIN32:
                try:
                    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                    matched_hwnds: List[int] = []

                    def enum_cb(h, lparam):
                        if user32.IsWindowVisible(h):
                            length = user32.GetWindowTextLengthW(h)
                            if length > 0:
                                buf = ctypes.create_unicode_buffer(length + 1)
                                user32.GetWindowTextW(h, buf, length + 1)
                                title = buf.value
                                if target_name.lower() in title.lower() or (clean and clean in title.lower()):
                                    matched_hwnds.append(h)
                        return True

                    user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.c_void_p]
                    user32.EnumWindows.restype = ctypes.c_bool
                    cb_func = WNDENUMPROC(enum_cb)
                    user32.EnumWindows(cb_func, 0)

                    if matched_hwnds:
                        h = matched_hwnds[0]
                        # Wake the window so UIA is active
                        user32.ShowWindow(h, 9)  # SW_RESTORE
                        user32.SetForegroundWindow(h)
                        time.sleep(0.2)
                        try:
                            ctrl = auto.ControlFromHandle(h)
                            if ctrl and ctrl.Exists(0, 0):
                                return ctrl
                        except Exception as c_ex:
                            logger.debug(f"ControlFromHandle({h}) note: {c_ex}")
                except Exception as ex:
                    logger.debug(f"EnumWindows discovery fallback note: {ex}")

            time.sleep(0.2)
        return None

    def get_process_info(self, hwnd: int) -> Tuple[int, str]:
        """Extracts PID and process image name from HWND."""
        if not HAS_WIN32 or not hwnd:
            return 0, "unknown"
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        p_name = "unknown"
        try:
            import psutil
            proc = psutil.Process(pid.value)
            p_name = proc.name()
        except Exception:
            pass
        return pid.value, p_name

    def inspect_window(
        self,
        app_name: str = "",
        hwnd: Optional[int] = None,
        max_elements: int = 80,
        wake_window: bool = True
    ) -> Optional[WindowInspection]:
        """
        Conducts deep forensic UI inspection on a desktop window.
        Extracts metadata, control hierarchy, states, bounding boxes, and values.
        """
        ensure_interactive_desktop()
        if not HAS_UIA or not auto:
            logger.warning("UIA not available for inspection.")
            return None

        win = None
        if hwnd:
            try:
                win = auto.ControlFromHandle(hwnd)
            except Exception as ex:
                logger.debug(f"Failed ControlFromHandle({hwnd}): {ex}")

        if not win or not win.Exists(0, 0):
            if app_name:
                win = self.find_window_by_app_name(app_name, timeout=1.5)
            else:
                win = auto.GetForegroundControl()

        if not win or not win.Exists(0, 0):
            return None

        h = win.NativeWindowHandle
        if wake_window and h and HAS_WIN32:
            try:
                # If minimized, restore
                if user32.IsIconic(h):
                    user32.ShowWindow(h, 9)  # SW_RESTORE
                user32.SetForegroundWindow(h)
                time.sleep(0.15)
            except Exception:
                pass

        # Window properties
        title = win.Name or ""
        pid, pname = self.get_process_info(h)
        is_fg = False
        if HAS_WIN32 and h:
            is_fg = (user32.GetForegroundWindow() == h)

        is_vis = bool(user32.IsWindowVisible(h)) if (HAS_WIN32 and h) else True
        is_en = bool(user32.IsWindowEnabled(h)) if (HAS_WIN32 and h) else True
        is_min = bool(user32.IsIconic(h)) if (HAS_WIN32 and h) else False

        rect = win.BoundingRectangle
        w_rect = (rect.left, rect.top, rect.right, rect.bottom) if rect else (0, 0, 0, 0)

        # Inspect controls recursively
        elements: List[UIElementInfo] = []

        def _walk_controls(ctrl: Any, depth: int = 0, max_depth: int = 4):
            if depth > max_depth or len(elements) >= max_elements:
                return
            try:
                children = ctrl.GetChildren()
            except Exception:
                return

            for c in children:
                if len(elements) >= max_elements:
                    break
                try:
                    name = (c.Name or "").strip()
                    ctype = c.ControlTypeName or "Control"
                    aid = (c.AutomationId or "").strip()
                    c_rect = c.BoundingRectangle
                    b_rect = (c_rect.left, c_rect.top, c_rect.right, c_rect.bottom) if c_rect else (0, 0, 0, 0)
                    enabled = getattr(c, "IsEnabled", True)
                    visible = not getattr(c, "IsOffscreen", False)
                    c_class = getattr(c, "ClassName", "")
                    c_hwnd = getattr(c, "NativeWindowHandle", None)
                    c_pid = getattr(c, "ProcessId", pid)

                    # Extract current value
                    val = None
                    try:
                        vp = c.GetValuePattern()
                        if vp and vp.Value:
                            val = vp.Value
                    except Exception:
                        pass
                    if not val:
                        try:
                            tp = c.GetTextPattern()
                            if tp and tp.DocumentRange:
                                val = tp.DocumentRange.GetText(-1)
                        except Exception:
                            pass
                    if not val and ctype in ("TextControl", "EditControl"):
                        try:
                            val = c.GetWindowText()
                        except Exception:
                            pass

                    # Filter out purely empty filler panes without names or ids
                    if name or aid or val or ctype in ("ButtonControl", "EditControl", "DocumentControl", "TextControl"):
                        elements.append(UIElementInfo(
                            control_type=ctype,
                            name=name,
                            automation_id=aid,
                            bounding_rect=b_rect,
                            is_enabled=enabled,
                            is_visible=visible,
                            current_value=val,
                            hwnd=c_hwnd,
                            runtime_id=getattr(c, "GetRuntimeId", lambda: None)(),
                            class_name=c_class,
                            process_id=c_pid,
                            depth=depth
                        ))

                    # Recurse children
                    _walk_controls(c, depth + 1, max_depth)
                except Exception as ex:
                    logger.debug(f"Element extraction error: {ex}")

        _walk_controls(win, depth=0, max_depth=4)

        inspection = WindowInspection(
            window_title=title,
            app_name=app_name or pname,
            process_id=pid,
            process_name=pname,
            hwnd=h,
            is_foreground=is_fg,
            is_visible=is_vis,
            is_enabled=is_en,
            is_minimized=is_min,
            bounding_rect=w_rect,
            elements=elements
        )

        if h:
            self._last_inspections[h] = inspection

        # Record inspection in forensic tracer
        ui_tracer.record_inspection(
            task_id=f"insp_task_{uuid.uuid4().hex[:6]}",
            application=app_name or pname,
            window={
                "title": title,
                "hwnd": h,
                "is_foreground": is_fg,
                "is_minimized": is_min,
                "bounding_rect": list(w_rect)
            },
            process={
                "pid": pid,
                "name": pname
            },
            controls_found=len(elements),
            controls_summary=[e.to_dict() for e in elements[:25]]
        )

        return inspection

    def search_control(
        self,
        inspection: WindowInspection,
        name: Optional[str] = None,
        control_type: Optional[str] = None,
        automation_id: Optional[str] = None
    ) -> Optional[UIElementInfo]:
        """
        Locates a control from inspection by Name, AutomationId, or ControlType.
        """
        if not inspection or not inspection.elements:
            return None

        # 1. Exact AutomationId match (highest specificity)
        if automation_id:
            for e in inspection.elements:
                if e.automation_id == automation_id:
                    return e

        # 2. Exact Name match
        if name:
            for e in inspection.elements:
                if e.name.lower() == name.lower():
                    if not control_type or control_type.lower() in e.control_type.lower():
                        return e

        # 3. Substring Name or AutomationId match
        if name:
            for e in inspection.elements:
                if name.lower() in e.name.lower() or name.lower() in e.automation_id.lower():
                    if not control_type or control_type.lower() in e.control_type.lower():
                        return e

        # 4. Fallback by control type only (e.g. first EditControl or DocumentControl)
        if control_type:
            for e in inspection.elements:
                if control_type.lower() in e.control_type.lower():
                    return e

        # 5. Targeted direct search via live UIA hierarchy
        if HAS_UIA and auto and inspection.hwnd:
            try:
                root = auto.ControlFromHandle(inspection.hwnd)
                live = None
                if automation_id:
                    live = root.Control(searchDepth=6, AutomationId=automation_id)
                if not live or not live.Exists(0, 0):
                    if name:
                        live = root.Control(searchDepth=6, Name=name)
                if live and live.Exists(0, 0):
                    rect = live.BoundingRectangle
                    b_rect = (rect.left, rect.top, rect.right, rect.bottom) if rect else (0, 0, 0, 0)
                    elem_info = UIElementInfo(
                        control_type=live.ControlTypeName or "Control",
                        name=live.Name or name or "",
                        automation_id=live.AutomationId or automation_id or "",
                        bounding_rect=b_rect,
                        is_enabled=getattr(live, "IsEnabled", True),
                        is_visible=not getattr(live, "IsOffscreen", False),
                        current_value=None,
                        hwnd=getattr(live, "NativeWindowHandle", None),
                        runtime_id=getattr(live, "GetRuntimeId", lambda: None)(),
                        class_name=getattr(live, "ClassName", ""),
                        process_id=getattr(live, "ProcessId", inspection.process_id),
                        depth=0
                    )
                    inspection.elements.append(elem_info)
                    return elem_info
            except Exception as ex:
                logger.debug(f"Direct UIA targeted search note: {ex}")

        return None

    def verify_content(
        self,
        inspection: WindowInspection,
        expected_text: str
    ) -> Tuple[bool, str]:
        """
        Verifies if expected text is present in any control or value of the inspected window.
        """
        if not inspection:
            return False, "Inspection is empty; window not available."

        target = expected_text.strip().lower()
        if not target:
            return True, "No expected content specified; window verified open."

        # Check window title
        if target in inspection.window_title.lower():
            return True, f"Found '{expected_text}' in window title '{inspection.window_title}'."

        # Check element values and names
        for e in inspection.elements:
            if e.current_value and target in e.current_value.lower():
                return True, f"Found '{expected_text}' in [{e.control_type}] '{e.name}' value='{e.current_value}'."
            if e.name and target in e.name.lower():
                return True, f"Found '{expected_text}' in [{e.control_type}] name='{e.name}'."

        return False, f"Expected text '{expected_text}' not observed in {len(inspection.elements)} window controls."


# Global Singleton Inspector
ui_inspector = UIInspector()
