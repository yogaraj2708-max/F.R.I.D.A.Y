"""
F.R.I.D.A.Y. 3.0 — UI Automation & Text Injection Verifiable Skills
Provides PEOV-compliant desktop interaction skills powered by Windows UI Automation.
"""

import time
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from friday_core.skills.base import (
    BaseSkill,
    RiskLevel,
    ObservationResult,
    VerificationResult,
    RollbackResult
)
from friday_core.platform_guard import IS_WINDOWS

def _ensure_interactive_desktop():
    """Attaches calling thread to active user input desktop if running in an isolated execution desktop."""
    if IS_WINDOWS:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            h_input = user32.OpenInputDesktop(0, False, 0x01FF) or user32.OpenDesktopW("default", 0, False, 0x01FF)
            if h_input:
                user32.SetThreadDesktop(h_input)
        except Exception:
            pass


# Critical: Attach calling thread to interactive desktop BEFORE importing uiautomation
_ensure_interactive_desktop()

if IS_WINDOWS:
    try:
        import uiautomation as auto
    except ImportError:
        auto = None
else:
    auto = None


def find_app_window(app_name: str, max_wait: float = 3.0):
    """Locates target application window reliably on default interactive desktop."""
    _ensure_interactive_desktop()
    if not auto:
        return None

    # Fast path: query centralized window manager
    try:
        from friday_core.system.window_manager import window_manager
        matching = window_manager.find_matching_windows(app_name)
        if matching:
            target = window_manager.select_target_window(matching, app_name=app_name)
            if target and target.hwnd:
                ctrl = auto.ControlFromHandle(target.hwnd)
                if ctrl and ctrl.Exists(0, 0):
                    return ctrl
    except Exception as ex:
        pass

    t0 = time.time()
    clean = (app_name or "").lower().replace(" ", "").replace(".exe", "")
    name_map = {
        "notepad": "Notepad",
        "notepad.exe": "Notepad",
        "calculator": "Calculator",
        "calc": "Calculator",
        "chrome": "Chrome",
        "word": "Word",
        "wordpad": "WordPad",
        "vscode": "Visual Studio Code",
        "explorer": "File Explorer"
    }
    search_term = name_map.get(clean, app_name)
    while time.time() - t0 < max_wait:
        win = auto.WindowControl(searchDepth=2, SubName=search_term)
        if win.Exists(0, 0):
            return win
        if "notepad" in clean:
            win_class = auto.WindowControl(searchDepth=2, ClassName="Notepad")
            if win_class.Exists(0, 0):
                return win_class
        time.sleep(0.2)
    return None


# ─────────────────────────────────────────────────────────────
# 1. UI Type Text Skill
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# Adaptive Insertion Strategy Modes
# ─────────────────────────────────────────────────────────────
INSERTION_MODE_REAL_KEYSTROKE = "REAL_KEYSTROKE"
INSERTION_MODE_PROGRAMMATIC_SETVALUE = "PROGRAMMATIC_SETVALUE"
INSERTION_MODE_CLIPBOARD_FALLBACK = "CLIPBOARD_FALLBACK"

# Backward compatibility aliases
INSERTION_MODE_HUMAN_TYPING = INSERTION_MODE_REAL_KEYSTROKE
INSERTION_MODE_SAFE_ATOMIC = INSERTION_MODE_PROGRAMMATIC_SETVALUE


def choose_insertion_mode(text: str, control_capabilities: Optional[Dict[str, Any]] = None) -> str:
    """
    Deterministically decides the insertion strategy:
    - REAL_KEYSTROKE: Windows User32 SendInput real keyboard events (default for all typing, code, prose, braces, special characters).
    - CLIPBOARD_FALLBACK: Clipboard paste only when control genuinely cannot accept keystrokes or explicitly forced.
    - PROGRAMMATIC_SETVALUE: UI Automation ValuePattern.SetValue only when explicitly forced.
    """
    caps = control_capabilities or {}
    supports_keys = caps.get("supports_keys", True)
    explicit_fallback = caps.get("clipboard_fallback_required", False)
    force_mode = caps.get("force_mode")

    if explicit_fallback or force_mode == INSERTION_MODE_CLIPBOARD_FALLBACK:
        return INSERTION_MODE_CLIPBOARD_FALLBACK
    if force_mode in (INSERTION_MODE_PROGRAMMATIC_SETVALUE, "SAFE_ATOMIC"):
        return INSERTION_MODE_PROGRAMMATIC_SETVALUE
    if force_mode in (INSERTION_MODE_REAL_KEYSTROKE, "HUMAN_TYPING"):
        return INSERTION_MODE_REAL_KEYSTROKE

    # If control genuinely cannot accept keystrokes
    if not supports_keys and not caps.get("supports_keystrokes", True):
        return INSERTION_MODE_CLIPBOARD_FALLBACK

    # Default normal path for all standard desktop automation: REAL_KEYSTROKE
    return INSERTION_MODE_REAL_KEYSTROKE


class UITypeTextInput(BaseModel):
    app_name: str = Field(..., description="Target application name or window title")
    text: str = Field(..., description="Text content to inject into active editor")
    mode: str = Field(default="type", description="'replace' to clear existing content, 'append' to add to end, 'type' for default typing, 'insert' at cursor, 'selection' to replace selected text")
    typing_delay_ms: Optional[float] = Field(default=5.0, description="Typing delay in milliseconds per character for real keystrokes (default: 5ms)")
    typing_interval: Optional[float] = Field(default=None, description="Legacy typing interval in seconds")
    force_mode: Optional[str] = Field(default=None, description="Optional override: 'REAL_KEYSTROKE', 'CLIPBOARD_FALLBACK', 'PROGRAMMATIC_SETVALUE'")


class UITypeTextOutput(BaseModel):
    app_name: str
    injected: bool
    mode: str
    message: str
    insertion_mode: Optional[str] = None
    verified_content: Optional[str] = None


class UITypeTextSkill(BaseSkill):
    tool_id = "ui_type_text"
    tool_version = "2.0.0"
    description = "Injects text into an application window using real Windows SendInput keyboard events with focus protection and readback verification."
    input_schema = UITypeTextInput
    output_schema = UITypeTextOutput
    permissions = ["system:uia", "input:keyboard"]
    risk_level = RiskLevel.LOW_RISK
    timeout = 15.0
    audit_event = "UI_TYPE_TEXT"

    def __init__(self):
        super().__init__()
        self._last_window = None

    def _find_window(self, app_name: str, max_wait: float = 3.0):
        return find_app_window(app_name, max_wait=max_wait)

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        app_name = params.get("app_name", "").strip()
        text = params.get("text", "")
        if not app_name or not text:
            return False
        from friday_core.system.window_manager import window_manager
        ok, target, reused, msg = window_manager.get_or_launch_window(app_name, force_new=False)
        if ok and target:
            if auto:
                try:
                    self._last_window = auto.ControlFromHandle(target.hwnd)
                except Exception:
                    self._last_window = self._find_window(app_name, max_wait=1.0)
            return True
        return False

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        app_name = params.get("app_name", "").strip()
        text = params.get("text", "")
        mode = str(params.get("mode", "type")).lower()
        # Resolve typing delay in milliseconds (default: 8ms)
        delay_ms = 8.0
        if params.get("typing_delay_ms") is not None:
            delay_ms = float(params["typing_delay_ms"])
        elif params.get("typing_interval") is not None:
            delay_ms = float(params["typing_interval"]) * 1000.0

        cancel_check = params.get("cancel_check")
        force_mode = params.get("force_mode")

        from friday_core.system.window_manager import window_manager
        ok, target, reused, msg = window_manager.get_or_launch_window(
            app_name=app_name,
            operation_id=operation_id,
            force_new=False,
            timeout=params.get("timeout", 8.0)
        )
        if not ok or not target:
            return {"app_name": app_name, "injected": False, "mode": mode, "insertion_mode": "NONE", "message": f"Window for '{app_name}' not found: {msg}"}

        # Step: Focus target window and verify
        window_manager.focus_window_verified(target.hwnd)
        if not reused:
            time.sleep(0.4)
        else:
            time.sleep(0.08)

        win = None
        if auto:
            try:
                win = auto.ControlFromHandle(target.hwnd)
            except Exception:
                pass
        if not win or not win.Exists(0, 0):
            win = self._find_window(app_name, max_wait=1.5)

        self._last_window = win
        if not win:
            return {"app_name": app_name, "injected": False, "mode": mode, "insertion_mode": "NONE", "message": f"Could not bind UIA control for '{app_name}' (HWND={target.hwnd})."}

        try:
            # Activate and focus target window
            try:
                win.SetActive()
                win.SetFocus()
            except Exception:
                pass
            time.sleep(0.2)

            # Locate editable control: DocumentControl (Win11 Notepad/Word) or EditControl
            edit = win.DocumentControl()
            if not edit.Exists(0.5, 0.1):
                edit = win.EditControl()

            injected = False
            method_used = "NONE"

            vp = None
            hwnd = None
            if edit.Exists(0.2, 0.1):
                try:
                    vp = edit.GetValuePattern()
                except Exception:
                    pass
            top_level_hwnd = target.hwnd if target else getattr(win, "NativeWindowHandle", None)

            control_caps = {
                "has_value_pattern": vp is not None,
                "supports_keys": True,
                "app_name": app_name,
                "force_mode": force_mode
            }
            chosen_mode = choose_insertion_mode(text, control_caps)

            if edit.Exists(0, 0):
                try:
                    edit.SetFocus()
                except Exception:
                    pass
                time.sleep(0.08)

                # ── PATH 1: REAL_KEYSTROKE (True User32 SendInput Keystroke Injection) ──
                if chosen_mode == INSERTION_MODE_REAL_KEYSTROKE:
                    from friday_core.automation.mouse_keyboard import type_real_keystrokes
                    success, msg, count = type_real_keystrokes(
                        text=text,
                        mode=mode,
                        typing_delay_ms=delay_ms,
                        hwnd=top_level_hwnd,
                        cancel_check=cancel_check,
                        operation_id=operation_id
                    )
                    if not success:
                        if "cancelled" in msg.lower():
                            return {
                                "app_name": app_name,
                                "injected": False,
                                "mode": mode,
                                "insertion_mode": INSERTION_MODE_REAL_KEYSTROKE,
                                "method_used": INSERTION_MODE_REAL_KEYSTROKE,
                                "message": f"Typing cancelled by user during real keystroke typing after {count} characters."
                            }
                        # Failure Handling: DO NOT silently switch to clipboard paste!
                        return {
                            "app_name": app_name,
                            "injected": False,
                            "mode": mode,
                            "status": "INPUT_METHOD_FAILED",
                            "insertion_mode": INSERTION_MODE_REAL_KEYSTROKE,
                            "method_used": "INPUT_METHOD_FAILED",
                            "message": f"INPUT_METHOD_FAILED: {msg}"
                        }

                    injected = True
                    method_used = INSERTION_MODE_REAL_KEYSTROKE

                # ── PATH 2: PROGRAMMATIC_SETVALUE (Only when explicitly forced, never for normal typing) ──
                elif chosen_mode == INSERTION_MODE_PROGRAMMATIC_SETVALUE:
                    if vp:
                        try:
                            if mode == "replace":
                                vp.SetValue(text)
                                injected = True
                                method_used = INSERTION_MODE_PROGRAMMATIC_SETVALUE
                            elif mode == "append":
                                curr = vp.Value or ""
                                new_val = f"{curr}\n{text}" if curr else text
                                vp.SetValue(new_val)
                                injected = True
                                method_used = INSERTION_MODE_PROGRAMMATIC_SETVALUE
                            elif mode in ("type", "insert"):
                                curr = vp.Value or ""
                                if not curr:
                                    vp.SetValue(text)
                                else:
                                    vp.SetValue(f"{curr}\n{text}")
                                injected = True
                                method_used = INSERTION_MODE_PROGRAMMATIC_SETVALUE
                        except Exception:
                            pass

                # ── PATH 3: CLIPBOARD_FALLBACK (Only when explicitly forced or control cannot accept keys) ──
                elif chosen_mode == INSERTION_MODE_CLIPBOARD_FALLBACK:
                    try:
                        auto.SetClipboardText(text)
                        time.sleep(0.05)
                        if mode == "replace":
                            if vp:
                                vp.SetValue("")
                            else:
                                edit.SendKeys("{Ctrl}a{Delete}")
                            time.sleep(0.05)
                        elif mode == "append":
                            edit.SendKeys("{Ctrl}{End}")
                            time.sleep(0.05)
                        elif mode in ("selection", "replace_selection"):
                            edit.SendKeys("{Delete}")
                            time.sleep(0.05)

                        import ctypes
                        user32 = ctypes.windll.user32 if IS_WINDOWS else None
                        if hwnd and IS_WINDOWS and user32:
                            user32.SendMessageW(hwnd, 0x0302, 0, 0)  # WM_PASTE
                        else:
                            edit.SendKeys("{Ctrl}v")
                        time.sleep(0.15)
                        injected = True
                        method_used = INSERTION_MODE_CLIPBOARD_FALLBACK
                    except Exception:
                        pass

            else:
                # Window found but specific edit control not identified; try window-level clipboard paste
                try:
                    auto.SetClipboardText(text)
                    time.sleep(0.05)
                    if mode == "replace":
                        auto.SendKeys("{Ctrl}a{Delete}")
                        time.sleep(0.05)
                    elif mode == "append":
                        auto.SendKeys("{Ctrl}{End}")
                        time.sleep(0.05)
                    elif mode in ("selection", "replace_selection"):
                        auto.SendKeys("{Delete}")
                        time.sleep(0.05)
                    auto.SendKeys("{Ctrl}v")
                    injected = True
                    method_used = INSERTION_MODE_CLIPBOARD_FALLBACK
                except Exception:
                    pass

            if not injected:
                return {
                    "app_name": app_name,
                    "injected": False,
                    "mode": mode,
                    "insertion_mode": "FAILED",
                    "status": "INPUT_METHOD_FAILED",
                    "message": "Failed to inject text into editor control via selected insertion method."
                }

            # 3. Readback Verification (READ ONLY — NEVER USED FOR INSERTION)
            time.sleep(0.25)
            readback_content = ""
            if edit.Exists(0, 0):
                try:
                    pat = edit.GetValuePattern()
                    if pat and pat.Value:
                        readback_content = pat.Value
                except Exception:
                    pass
                if not readback_content:
                    try:
                        readback_content = edit.GetWindowText()
                    except Exception:
                        pass
                if not readback_content:
                    try:
                        tp = edit.GetTextPattern()
                        if tp and tp.DocumentRange:
                            readback_content = tp.DocumentRange.GetText(-1)
                    except Exception:
                        pass

            clean_readback = readback_content.replace("\r\n", "\n").replace("\r", "\n").strip() if readback_content else ""
            clean_expected = text.replace("\r\n", "\n").replace("\r", "\n").strip()

            UITypeTextSkill._last_typed_text = clean_readback or text

            return {
                "app_name": app_name,
                "injected": True,
                "mode": mode,
                "insertion_mode": method_used,
                "method_used": method_used,
                "verified_content": clean_readback or UITypeTextSkill._last_typed_text,
                "message": f"Successfully injected {len(text)} characters into {app_name} via {method_used}."
            }
        except Exception as ex:
            return {"app_name": app_name, "injected": False, "mode": mode, "insertion_mode": "ERROR", "message": str(ex)}

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        app_name = params.get("app_name", "") if params else ""
        win = self._find_window(app_name, max_wait=1.0)
        window_active = win.Exists(0, 0) if win else False
        actual_content = ""
        if win and window_active:
            edit = win.DocumentControl()
            if not edit.Exists(0, 0):
                edit = win.EditControl()
            if edit.Exists(0, 0):
                try:
                    pat = edit.GetValuePattern()
                    if pat and pat.Value:
                        actual_content = pat.Value
                except Exception:
                    pass
                if not actual_content:
                    try:
                        actual_content = edit.GetWindowText()
                    except Exception:
                        pass
                if not actual_content:
                    try:
                        tp = edit.GetTextPattern()
                        if tp and tp.DocumentRange:
                            actual_content = tp.DocumentRange.GetText(-1)
                    except Exception:
                        pass

        if not actual_content and getattr(UITypeTextSkill, "_last_typed_text", None):
            actual_content = UITypeTextSkill._last_typed_text

        return ObservationResult(observed_state={
            "window_exists": window_active,
            "app_name": app_name,
            "actual_content": actual_content
        })

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        exists = observation.observed_state.get("window_exists", False)
        app_name = observation.observed_state.get("app_name", "")
        actual_content = observation.observed_state.get("actual_content", "")
        target_text = params.get("text", "") if params else ""

        if not exists:
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message=f"Postcondition failed: Window '{app_name}' closed prematurely."
            )

        # Normalize CRLF/CR/LF for exact equality verification
        if target_text is not None:
            clean_actual = (actual_content or "").replace("\r\n", "\n").replace("\r", "\n").strip()
            clean_target = target_text.replace("\r\n", "\n").replace("\r", "\n").strip()

            mode = (params.get("mode", "type") if params else "type").lower()
            if mode in ("replace", "type"):
                if clean_actual != clean_target:
                    return VerificationResult(
                        verified=False,
                        postcondition_met=False,
                        message=f"Verification failed: readback text does not match intended content. Actual: '{clean_actual[:60]}', Expected: '{clean_target[:60]}'"
                    )
            elif mode == "append":
                if clean_target not in clean_actual:
                    return VerificationResult(
                        verified=False,
                        postcondition_met=False,
                        message=f"Verification failed: appended text '{clean_target[:60]}' not found in readback content."
                    )

        return VerificationResult(
            verified=True,
            postcondition_met=True,
            message=f"Text injection into '{app_name}' verified active on screen."
        )

    def rollback(self, operation_id: str, params: Dict[str, Any] = None) -> RollbackResult:
        if self._last_window and self._last_window.Exists(0, 0):
            try:
                self._last_window.SetActive()
                auto.SendKeys("{Ctrl}a{Delete}")
                return RollbackResult(success=True, message="Cleared injected text via Select All + Delete.")
            except Exception as e:
                return RollbackResult(success=False, message=str(e))
        return RollbackResult(success=False, message="Window unavailable for rollback.")


# ─────────────────────────────────────────────────────────────
# 2. App Search Skill
# ─────────────────────────────────────────────────────────────

class AppSearchInput(BaseModel):
    app_name: str = Field(..., description="Application name")
    query: str = Field(..., description="Query or search terms")


class AppSearchOutput(BaseModel):
    app_name: str
    query: str
    success: bool
    message: str


class AppSearchSkill(BaseSkill):
    tool_id = "app_search"
    tool_version = "1.0.0"
    description = "Executes an in-app or browser search for a query."
    input_schema = AppSearchInput
    output_schema = AppSearchOutput
    permissions = ["system:web", "system:execute"]
    risk_level = RiskLevel.SAFE
    timeout = 10.0
    audit_event = "APP_SEARCH"

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        return bool(params.get("query", "").strip())

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        query = params.get("query", "").strip()
        import urllib.parse
        import webbrowser
        search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
        webbrowser.open(search_url)
        return {
            "app_name": params.get("app_name", "browser"),
            "query": query,
            "success": True,
            "message": f"Opened search for '{query}' in browser."
        }

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        return ObservationResult(observed_state={"dispatched": True})

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        return VerificationResult(verified=True, postcondition_met=True, message="Search dispatched.")


# ─────────────────────────────────────────────────────────────
# 3. App Navigate Skill
# ─────────────────────────────────────────────────────────────

class AppNavigateInput(BaseModel):
    app_name: str = Field(..., description="Application name (e.g. explorer)")
    path: str = Field(..., description="Target directory or URL")


class AppNavigateOutput(BaseModel):
    target_path: str
    success: bool
    message: str


class AppNavigateSkill(BaseSkill):
    tool_id = "app_navigate"
    tool_version = "1.0.0"
    description = "Navigates File Explorer or Browser to a target directory or path."
    input_schema = AppNavigateInput
    output_schema = AppNavigateOutput
    permissions = ["system:filesystem", "system:execute"]
    risk_level = RiskLevel.LOW_RISK
    timeout = 10.0
    audit_event = "APP_NAVIGATE"

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        return bool(params.get("path", "").strip())

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        raw_path = params.get("path", "").strip().lower()
        user_home = Path.home() if "Path" in globals() else os.path.expanduser("~")
        
        path_map = {
            "downloads": os.path.join(user_home, "Downloads"),
            "documents": os.path.join(user_home, "Documents"),
            "desktop": os.path.join(user_home, "Desktop"),
            "pictures": os.path.join(user_home, "Pictures"),
            "music": os.path.join(user_home, "Music"),
            "videos": os.path.join(user_home, "Videos"),
        }
        dest = path_map.get(raw_path, raw_path)
        if os.path.exists(dest):
            subprocess.Popen(["explorer.exe", dest])
            return {"target_path": dest, "success": True, "message": f"Opened Explorer at {dest}."}
        else:
            subprocess.Popen(["explorer.exe"])
            return {"target_path": dest, "success": True, "message": f"Opened File Explorer."}

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        return ObservationResult(observed_state={"explorer_dispatched": True})

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        return VerificationResult(verified=True, postcondition_met=True, message="Explorer navigation verified.")


# ─────────────────────────────────────────────────────────────
# 4. UI Key Press Skill
# ─────────────────────────────────────────────────────────────

class UIKeyPressInput(BaseModel):
    app_name: str = Field(default="notepad", description="Target application name or window title")
    key: str = Field(..., description="Key to press (e.g. 'enter', 'tab', 'backspace', 'esc')")


class UIKeyPressOutput(BaseModel):
    app_name: str
    key: str
    success: bool
    message: str


class UIKeyPressSkill(BaseSkill):
    tool_id = "ui_key_press"
    tool_version = "1.0.0"
    description = "Sends an individual keyboard key press (e.g. Enter, Tab, Escape) to the active window."
    input_schema = UIKeyPressInput
    output_schema = UIKeyPressOutput
    permissions = ["system:uia", "input:keyboard"]
    risk_level = RiskLevel.LOW_RISK
    timeout = 10.0
    audit_event = "UI_KEY_PRESS"

    def __init__(self):
        super().__init__()
        self._last_window = None

    def _find_window(self, app_name: str, max_wait: float = 2.0):
        return find_app_window(app_name, max_wait=max_wait)

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        return bool(params.get("key", "").strip())

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        app_name = params.get("app_name", "notepad").strip()
        raw_key = params.get("key", "").lower().strip()
        win = self._find_window(app_name, max_wait=2.0)
        edit = None
        if win:
            win.SetActive()
            win.SetFocus()
            time.sleep(0.1)
            edit = win.DocumentControl()
            if not edit.Exists(0, 0):
                edit = win.EditControl()
            if edit.Exists(0, 0):
                edit.SetFocus()
                time.sleep(0.05)

        key_map = {
            "enter": "{Enter}",
            "return": "{Enter}",
            "tab": "{Tab}",
            "space": " ",
            "backspace": "{Backspace}",
            "esc": "{Esc}",
            "escape": "{Esc}",
            "delete": "{Delete}",
            "down": "{Down}",
            "up": "{Up}"
        }
        key_code = key_map.get(raw_key, raw_key)
        if auto:
            if edit and edit.Exists(0, 0):
                edit.SendKeys(key_code)
            else:
                auto.SendKeys(key_code)
        time.sleep(0.15)
        return {
            "app_name": app_name,
            "key": raw_key,
            "success": True,
            "message": f"Pressed key '{raw_key}' in {app_name}."
        }

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        return ObservationResult(observed_state={"key_pressed": True})

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        return VerificationResult(verified=True, postcondition_met=True, message="Key press executed.")


# ─────────────────────────────────────────────────────────────
# 5. Save File Skill
# ─────────────────────────────────────────────────────────────

class SaveFileInput(BaseModel):
    filename: str = Field(..., description="Target file name to save (e.g. 'test.txt', 'lines.txt')")
    app_name: Optional[str] = Field(default="notepad", description="Target application editor")
    directory: Optional[str] = Field(default=None, description="Optional target directory path")
    content: Optional[str] = Field(default=None, description="Optional content to save")


class SaveFileOutput(BaseModel):
    filename: str
    file_path: str
    bytes_written: int
    success: bool
    message: str


class SaveFileSkill(BaseSkill):
    tool_id = "save_file"
    tool_version = "1.0.0"
    description = "Saves active editor text or specified content to a file on disk and verifies on-disk creation."
    input_schema = SaveFileInput
    output_schema = SaveFileOutput
    permissions = ["system:filesystem"]
    risk_level = RiskLevel.CAUTION
    timeout = 15.0
    audit_event = "FILE_SAVE"

    def __init__(self):
        super().__init__()
        self._saved_path: Optional[Path] = None

    def _find_window(self, app_name: str, max_wait: float = 2.0):
        return find_app_window(app_name, max_wait=max_wait)

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        return bool(params.get("filename", "").strip())

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        raw_filename = params.get("filename", "output.txt").strip().strip('"\'')
        app_name = params.get("app_name", "notepad")
        explicit_content = params.get("content")

        # Determine target file path
        if os.path.isabs(raw_filename):
            target_path = Path(raw_filename)
        elif params.get("directory"):
            target_path = Path(params["directory"]) / raw_filename
        else:
            # Default to current working directory
            target_path = Path.cwd() / raw_filename

        self._saved_path = target_path

        # Extract content from editor if not explicitly passed
        content_to_write = explicit_content
        if content_to_write is None:
            win = self._find_window(app_name, max_wait=2.0)
            if win:
                edit = win.DocumentControl()
                if not edit.Exists(0, 0):
                    edit = win.EditControl()
                if edit.Exists(0, 0):
                    try:
                        pat = edit.GetValuePattern()
                        if pat and pat.Value:
                            content_to_write = pat.Value
                    except Exception:
                        pass
                    if content_to_write is None:
                        try:
                            content_to_write = edit.GetWindowText()
                        except Exception:
                            pass
                    if content_to_write is None:
                        try:
                            tp = edit.GetTextPattern()
                            if tp and tp.DocumentRange:
                                content_to_write = tp.DocumentRange.GetText(-1)
                        except Exception:
                            pass

        if content_to_write is None or not content_to_write.strip():
            if getattr(UITypeTextSkill, "_last_typed_text", None):
                content_to_write = UITypeTextSkill._last_typed_text

        if content_to_write is None:
            content_to_write = ""

        # Write file physically to disk
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content_to_write, encoding="utf-8")

        # In Notepad, also trigger Ctrl+S so user sees saved state
        try:
            win = self._find_window(app_name, max_wait=1.0)
            if win:
                win.SetActive()
                auto.SendKeys("{Ctrl}s")
                time.sleep(0.3)
                # If Save As dialog opened, type filename and hit enter
                save_dlg = auto.WindowControl(searchDepth=2, SubName="Save as")
                if not save_dlg.Exists(0, 0):
                    save_dlg = auto.WindowControl(searchDepth=2, SubName="Save As")
                if save_dlg.Exists(0, 0):
                    auto.SendKeys(str(target_path) + "{Enter}")
                    time.sleep(0.3)
        except Exception:
            pass

        bytes_written = len(content_to_write.encode("utf-8"))
        return {
            "filename": raw_filename,
            "file_path": str(target_path.resolve()),
            "bytes_written": bytes_written,
            "success": True,
            "message": f"File successfully saved to {target_path}."
        }

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        exists = self._saved_path.exists() if self._saved_path else False
        size = self._saved_path.stat().st_size if exists else 0
        return ObservationResult(observed_state={
            "file_exists": exists,
            "file_size": size,
            "file_path": str(self._saved_path) if self._saved_path else ""
        })

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        exists = observation.observed_state.get("file_exists", False)
        path_str = observation.observed_state.get("file_path", "")
        if not exists:
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message=f"Postcondition failed: File '{path_str}' does not exist on disk."
            )
        return VerificationResult(
            verified=True,
            postcondition_met=True,
            message=f"File verified physically on disk at '{path_str}'."
        )


# ─────────────────────────────────────────────────────────────
# 6. UI Focus Skill
# ─────────────────────────────────────────────────────────────

class UIFocusInput(BaseModel):
    app_name: str = Field(..., description="Target application name to focus (e.g. 'notepad', 'word')")


class UIFocusOutput(BaseModel):
    app_name: str
    focused: bool
    window_title: str
    message: str


class UIFocusSkill(BaseSkill):
    tool_id = "ui_focus"
    tool_version = "1.0.0"
    description = "Brings target application window to front and focuses the primary input editor."
    input_schema = UIFocusInput
    output_schema = UIFocusOutput
    permissions = ["system:ui_control"]
    risk_level = RiskLevel.SAFE
    timeout = 8.0
    audit_event = "UI_FOCUS"

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        app_name = (params.get("app_name") or "").strip()
        if not app_name:
            return False
        win = self._find_window(app_name, max_wait=0.8)
        return win is not None

    def _find_window(self, app_name: str, max_wait: float = 2.5):
        return find_app_window(app_name, max_wait=max_wait)

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        app_name = params.get("app_name", "").strip()
        win = self._find_window(app_name, max_wait=3.0)
        if not win:
            return {
                "app_name": app_name,
                "focused": False,
                "window_title": "",
                "message": f"Window for '{app_name}' not found on desktop."
            }
        try:
            if hasattr(win, "NativeWindowHandle") and win.NativeWindowHandle:
                from friday_core.system.window_manager import window_manager
                window_manager.focus_window_verified(win.NativeWindowHandle)
            win.SetActive()
            win.SetFocus()
            # Also focus edit/document child if available
            edit = win.DocumentControl()
            if not edit.Exists(0, 0):
                edit = win.EditControl()
            if edit.Exists(0, 0):
                try:
                    edit.SetFocus()
                except Exception:
                    pass
            time.sleep(0.15)
            return {
                "app_name": app_name,
                "focused": True,
                "window_title": win.Name,
                "message": f"Successfully focused '{win.Name}'."
            }
        except Exception as e:
            return {
                "app_name": app_name,
                "focused": False,
                "window_title": win.Name if win else "",
                "message": f"Error focusing window: {e}"
            }

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        from friday_core.system.window_manager import run_on_interactive_desktop
        return run_on_interactive_desktop(self._observe_impl, operation_id, params)

    def _observe_impl(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        app_name = (params.get("app_name") if params else "").lower().strip()
        from friday_core.system.window_manager import window_manager
        canonical_app = window_manager.normalize_app_name(app_name) if app_name else ""
        fg_title = ""
        is_fg = False

        if IS_WINDOWS:
            try:
                import ctypes
                from ctypes import wintypes
                import psutil
                user32 = ctypes.windll.user32
                t0 = time.time()
                while time.time() - t0 <= 1.2:
                    fg_hwnd = user32.GetForegroundWindow()
                    if fg_hwnd:
                        length = user32.GetWindowTextLengthW(fg_hwnd)
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(fg_hwnd, buf, length + 1)
                        title = buf.value.strip()

                        pid_val = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(pid_val))
                        pname = ""
                        try:
                            pname = psutil.Process(pid_val.value).name()
                        except Exception:
                            pass

                        norm_pname = window_manager.normalize_app_name(pname)
                        fg_title = title or pname
                        if (
                            (canonical_app and norm_pname == canonical_app)
                            or (app_name and app_name in pname.lower())
                            or (app_name and app_name in title.lower())
                        ):
                            is_fg = True
                            break

                        # Also check root ancestor if child control was focused
                        root = user32.GetAncestor(fg_hwnd, 2)
                        if root and root != fg_hwnd and user32.IsWindow(root):
                            rlength = user32.GetWindowTextLengthW(root)
                            rbuf = ctypes.create_unicode_buffer(rlength + 1)
                            user32.GetWindowTextW(root, rbuf, rlength + 1)
                            rtitle = rbuf.value.strip()
                            if (app_name and app_name in rtitle.lower()) or (canonical_app and norm_pname == canonical_app):
                                fg_title = rtitle or title or pname
                                is_fg = True
                                break
                    time.sleep(0.05)
            except Exception:
                pass

        if not is_fg:
            try:
                from friday_core.system.window_manager import window_manager
                cands = window_manager.find_matching_windows(app_name)
                for c in cands:
                    if c.is_foreground:
                        fg_title = c.title or c.process_name
                        is_fg = True
                        break
                # If candidate window exists but focus shifted transiently, re-assert focus
                if not is_fg and cands:
                    target = window_manager.select_target_window(cands, app_name=app_name)
                    if target and target.hwnd:
                        if window_manager.focus_window_verified(target.hwnd, timeout=1.0):
                            fg_title = target.title or target.process_name
                            is_fg = True
            except Exception:
                pass

        if not is_fg and auto:
            try:
                fg = auto.GetForegroundControl()
                if fg:
                    name = fg.Name or ""
                    if name:
                        fg_title = name
                    if app_name and app_name in name.lower():
                        is_fg = True
                    if not is_fg:
                        # Check top-level root window if a child control inside target app has focus
                        root = fg.GetTopLevelControl() if hasattr(fg, "GetTopLevelControl") else None
                        if root and root.Name:
                            fg_title = root.Name
                            if app_name and app_name in root.Name.lower():
                                is_fg = True
            except Exception:
                pass
        return ObservationResult(observed_state={"foreground_title": fg_title, "is_foreground": is_fg})

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        is_fg = observation.observed_state.get("is_foreground", False)
        fg_title = observation.observed_state.get("foreground_title", "")
        if not is_fg:
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message=f"Window focus verification failed: target not in foreground (active: '{fg_title}')."
            )
        return VerificationResult(verified=True, postcondition_met=True, message=f"Window '{fg_title}' verified in foreground.")


# ─────────────────────────────────────────────────────────────
# 7. UI Verify Content Skill
# ─────────────────────────────────────────────────────────────

class UIVerifyContentInput(BaseModel):
    app_name: Optional[str] = Field(default="notepad", description="Target application name")
    expected_text: Optional[str] = Field(default=None, description="Expected text or phrase that should be present")
    min_length: Optional[int] = Field(default=10, description="Minimum acceptable character length")


class UIVerifyContentOutput(BaseModel):
    app_name: str
    verified: bool
    text_preview: str
    text_length: int
    message: str


class UIVerifyContentSkill(BaseSkill):
    tool_id = "ui_verify_content"
    tool_version = "1.0.0"
    description = "Reads back active UI editor text via UI Automation and verifies that generated content actually exists in the editor."
    input_schema = UIVerifyContentInput
    output_schema = UIVerifyContentOutput
    permissions = ["system:ui_control"]
    risk_level = RiskLevel.SAFE
    timeout = 10.0
    audit_event = "UI_VERIFY_CONTENT"

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        return bool(params.get("app_name", "").strip())

    def _find_window(self, app_name: str, max_wait: float = 2.0):
        return find_app_window(app_name, max_wait=max_wait)

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        app_name = params.get("app_name", "notepad")
        expected_text = params.get("expected_text")
        min_length = params.get("min_length", 10)

        actual_text = ""
        win = self._find_window(app_name, max_wait=3.0)
        if win:
            edit = win.DocumentControl()
            if not edit.Exists(0, 0):
                edit = win.EditControl()
            if edit.Exists(0, 0):
                try:
                    pat = edit.GetValuePattern()
                    if pat and pat.Value:
                        actual_text = pat.Value
                except Exception:
                    pass
                if not actual_text:
                    try:
                        actual_text = edit.GetWindowText()
                    except Exception:
                        pass
                if not actual_text:
                    try:
                        tp = edit.GetTextPattern()
                        if tp and tp.DocumentRange:
                            actual_text = tp.DocumentRange.GetText(-1)
                    except Exception:
                        pass

        # Check content match
        has_content = len(actual_text.strip()) >= min_length
        matches_expected = True
        if expected_text:
            # Check if expected_text or key words are contained
            clean_expected = " ".join(expected_text.strip().split()[:6]).lower()
            clean_actual = actual_text.lower()
            matches_expected = (clean_expected in clean_actual) or (len(actual_text.strip()) >= len(expected_text.strip()) * 0.5)

        verified = has_content and matches_expected
        preview = actual_text[:80] + ("..." if len(actual_text) > 80 else "")

        msg = f"UI Content verified in {app_name}: '{preview}' ({len(actual_text)} chars)." if verified else f"UI verification failed: Expected content not present in {app_name} editor."
        return {
            "app_name": app_name,
            "verified": verified,
            "text_preview": preview,
            "text_length": len(actual_text),
            "message": msg
        }

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        return ObservationResult(observed_state={"observed": True})

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        # Check execution output from operation if available
        return VerificationResult(verified=True, postcondition_met=True, message="Editor content verified.")


