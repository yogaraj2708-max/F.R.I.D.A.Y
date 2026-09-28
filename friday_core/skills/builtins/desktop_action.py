"""
F.R.I.D.A.Y. 3.0 — Desktop Action Verifiable Skills
Provides robust, verifiable Screenshot capture and Clipboard operations
with native Windows Input Desktop station synchronization.
"""

import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from pydantic import BaseModel, Field

from friday_core.skills.base import (
    BaseSkill,
    RiskLevel,
    ObservationResult,
    VerificationResult,
    RollbackResult
)
from friday_core.skills.builtins.ui_automation import _ensure_interactive_desktop

logger = logging.getLogger("FRIDAY.DesktopAction")


def _grab_display_worker():
    """Worker function executed on a clean background thread without GUI hooks."""
    if sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            h_input = user32.OpenInputDesktop(0, False, 0x01FF)
            if h_input:
                user32.SetThreadDesktop(h_input)
        except Exception:
            pass

    from PIL import ImageGrab
    try:
        return ImageGrab.grab()
    except Exception:
        return ImageGrab.grab(all_screens=True)


def capture_and_save_screenshot(
    target_path: Optional[str] = None,
    target_dir: Optional[Any] = None,
    return_details: bool = False
) -> Any:
    """
    Captures the physical Windows display buffer and saves it to disk.
    Verifies that the file exists, has non-zero size, and is a valid readable image.
    Executes screen capture on a dedicated thread to ensure clean Win32 station synchronization.
    """
    import concurrent.futures

    resolved_dest = str(target_dir) if target_dir is not None else target_path

    # Resolve target save path
    if not resolved_dest:
        desktop_candidates = [
            Path(os.path.expanduser("~")) / "Desktop",
            Path(os.path.expanduser("~")) / "OneDrive" / "Desktop"
        ]
        target_directory = desktop_candidates[0]
        for d in desktop_candidates:
            if d.exists():
                target_directory = d
                break
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_file = target_directory / f"screenshot_{timestamp}.png"
    else:
        p = Path(resolved_dest)
        if p.is_dir() or not p.suffix:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target_file = p / f"screenshot_{timestamp}.png"
        else:
            if not p.is_absolute():
                desktop = Path(os.path.expanduser("~")) / "Desktop"
                target_file = desktop / p.name
            else:
                target_file = p

    target_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Capture display buffer via dedicated worker thread
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_grab_display_worker)
            img = future.result(timeout=5.0)

        if img is None or img.size[0] == 0 or img.size[1] == 0:
            if return_details:
                return False, "Failed to capture display buffer (0x0 dimensions)", {}
            return None

        img.save(str(target_file), format="PNG")

        # Independent physical verification
        if not target_file.exists() or target_file.stat().st_size == 0:
            if return_details:
                return False, "Screenshot file was not written to disk or is empty", {}
            return None

        # Verify readability and dimensions
        from PIL import Image
        with Image.open(str(target_file)) as verified_img:
            w, h = verified_img.size
            if w <= 0 or h <= 0:
                if return_details:
                    return False, f"Image dimensions invalid: {w}x{h}", {}
                return None

        details = {
            "path": str(target_file.resolve()),
            "width": w,
            "height": h,
            "size_bytes": target_file.stat().st_size
        }
        if return_details:
            return True, str(target_file.resolve()), details
        return str(target_file.resolve())
    except Exception as e:
        logger.exception(f"Screenshot capture failure: {e}")
        if return_details:
            return False, f"Screenshot capture error: {str(e)}", {}
        return None


class ScreenshotInput(BaseModel):
    save_path: Optional[str] = Field(default="", description="Optional destination path or folder for screenshot")
    target_dir: Optional[str] = Field(default="", description="Optional destination directory for screenshot")


class ScreenshotOutput(BaseModel):
    success: bool
    path: str
    width: int = 0
    height: int = 0
    size_bytes: int = 0
    message: str = ""


class ScreenshotSkill(BaseSkill):
    tool_id = "screenshot"
    tool_version = "1.0.0"
    description = "Captures full screen display and saves to disk with image integrity verification."
    input_schema = ScreenshotInput
    output_schema = ScreenshotOutput
    permissions = ["system:screen_capture"]
    risk_level = RiskLevel.LOW_RISK
    timeout = 8.0
    audit_event = "SCREENSHOT_CAPTURE"

    def __init__(self):
        super().__init__()
        self._last_saved: Dict[str, str] = {}

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        return sys.platform == "win32"

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        save_p = params.get("save_path") or params.get("target_dir") or ""
        ok, res_path, details = capture_and_save_screenshot(save_p if save_p else None, return_details=True)
        if ok:
            self._last_saved[operation_id] = res_path
            return {
                "success": True,
                "path": res_path,
                "width": details.get("width", 0),
                "height": details.get("height", 0),
                "size_bytes": details.get("size_bytes", 0),
                "message": f"Screenshot captured and saved to '{res_path}'."
            }
        return {
            "success": False,
            "path": "",
            "message": f"Screenshot failed: {res_path}"
        }

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        path = self._last_saved.get(operation_id, "")
        if not path or not os.path.exists(path):
            return ObservationResult(observed_state={"file_exists": False, "path": path})

        size = os.path.getsize(path)
        is_valid_img = False
        w, h = 0, 0
        try:
            from PIL import Image
            with Image.open(path) as img:
                w, h = img.size
                is_valid_img = w > 0 and h > 0
        except Exception:
            pass

        return ObservationResult(observed_state={
            "file_exists": True,
            "path": path,
            "size_bytes": size,
            "is_valid_image": is_valid_img,
            "width": w,
            "height": h
        })

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        state = observation.observed_state
        if not state.get("file_exists") or state.get("size_bytes", 0) == 0:
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message="Screenshot file does not exist or has 0 bytes on disk."
            )
        if not state.get("is_valid_image"):
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message="Screenshot file exists but cannot be parsed as a valid image."
            )
        return VerificationResult(
            verified=True,
            postcondition_met=True,
            message=f"Verified screenshot on disk: {state.get('path')} ({state.get('width')}x{state.get('height')}, {state.get('size_bytes')} bytes)."
        )

    def rollback(self, operation_id: str, params: Dict[str, Any] = None) -> RollbackResult:
        path = self._last_saved.get(operation_id)
        if path and os.path.exists(path):
            try:
                os.remove(path)
                return RollbackResult(success=True, message=f"Removed screenshot {path}.")
            except Exception as e:
                return RollbackResult(success=False, message=f"Failed to delete screenshot: {e}")
        return RollbackResult(success=True, message="No screenshot to rollback.")


# ─────────────────────────────────────────────────────────────
# CLIPBOARD OPERATIONS & SKILL
# ─────────────────────────────────────────────────────────────

def clipboard_set(text: str) -> bool:
    """Sets Unicode text into Windows clipboard using Win32 API with contention retries."""
    _ensure_interactive_desktop()
    for attempt in range(6):
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
                return True
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            time.sleep(0.04)

    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        for attempt in range(6):
            if user32.OpenClipboard(None):
                try:
                    user32.EmptyClipboard()
                    encoded = text.encode("utf-16le") + b"\x00\x00"
                    h_mem = kernel32.GlobalAlloc(0x0042, len(encoded))  # GMEM_MOVEABLE | GMEM_ZEROINIT
                    if not h_mem:
                        return False
                    p_mem = kernel32.GlobalLock(h_mem)
                    if not p_mem:
                        return False
                    ctypes.memmove(p_mem, encoded, len(encoded))
                    kernel32.GlobalUnlock(h_mem)
                    return bool(user32.SetClipboardData(13, h_mem))  # CF_UNICODETEXT = 13
                finally:
                    user32.CloseClipboard()
            time.sleep(0.04)
    except Exception as e:
        logger.exception(f"[Clipboard]: Failed to set clipboard: {e}")
        return False
    return False


def clipboard_get() -> str:
    """Reads back Unicode text from Windows clipboard with contention retries."""
    _ensure_interactive_desktop()
    for attempt in range(6):
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                    data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                    return data if data is not None else ""
                elif win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_TEXT):
                    data = win32clipboard.GetClipboardData(win32clipboard.CF_TEXT)
                    return data.decode("utf-8", errors="ignore") if isinstance(data, bytes) else str(data or "")
                return ""
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            time.sleep(0.04)

    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        for attempt in range(6):
            if user32.OpenClipboard(None):
                try:
                    if user32.IsClipboardFormatAvailable(13):  # CF_UNICODETEXT
                        h_clip = user32.GetClipboardData(13)
                        if h_clip:
                            p_clip = kernel32.GlobalLock(h_clip)
                            if p_clip:
                                val = ctypes.wstring_at(p_clip)
                                kernel32.GlobalUnlock(h_clip)
                                return val
                    return ""
                finally:
                    user32.CloseClipboard()
            time.sleep(0.04)
    except Exception as e:
        logger.debug(f"[Clipboard]: ctypes read error: {e}")
        return ""
    return ""


def clipboard_verify(expected: str) -> bool:
    """Verifies that the clipboard readback exactly matches the expected text with retries."""
    for _ in range(6):
        actual = clipboard_get()
        if actual == expected:
            return True
        time.sleep(0.04)
    return False


class ClipboardInput(BaseModel):
    action: str = Field(default="set", description="Action to perform: 'set', 'get', or 'verify'")
    text: str = Field(default="", description="Text to write to or verify against the clipboard")


class ClipboardOutput(BaseModel):
    success: bool
    text: str = ""
    verified: bool = False
    message: str = ""


class ClipboardSkill(BaseSkill):
    tool_id = "clipboard"
    tool_version = "1.0.0"
    description = "Reads, writes, and verifies Windows clipboard text with exact readback matching."
    input_schema = ClipboardInput
    output_schema = ClipboardOutput
    permissions = ["system:clipboard"]
    risk_level = RiskLevel.SAFE
    timeout = 3.0
    audit_event = "CLIPBOARD_OP"

    def __init__(self):
        super().__init__()
        self._previous_clip: Dict[str, str] = {}

    def precondition_check(self, params: Dict[str, Any]) -> bool:
        return sys.platform == "win32"

    def execute(self, params: Dict[str, Any], operation_id: str) -> Dict[str, Any]:
        action = params.get("action", "set").lower().strip()
        text = params.get("text", "")

        # Save previous for rollback
        self._previous_clip[operation_id] = clipboard_get()

        if action == "set":
            ok = clipboard_set(text)
            readback = clipboard_get()
            verified = (readback == text)
            return {
                "success": ok and verified,
                "text": readback,
                "verified": verified,
                "message": f"Clipboard updated and verified ({len(text)} chars)." if verified else "Clipboard write failed readback verification."
            }
        elif action == "get":
            current = clipboard_get()
            return {
                "success": True,
                "text": current,
                "verified": True,
                "message": f"Read {len(current)} chars from clipboard."
            }
        elif action == "verify":
            verified = clipboard_verify(text)
            return {
                "success": verified,
                "text": clipboard_get(),
                "verified": verified,
                "message": "Clipboard matches expected content." if verified else "Clipboard content does not match expected text."
            }
        return {"success": False, "message": f"Unknown clipboard action '{action}'"}

    def observe(self, operation_id: str, params: Dict[str, Any] = None) -> ObservationResult:
        expected = params.get("text", "") if params else ""
        current = ""
        for _ in range(6):
            current = clipboard_get()
            if not expected or current == expected:
                break
            time.sleep(0.04)
        return ObservationResult(observed_state={"current_clipboard": current})

    def verify(self, observation: ObservationResult, params: Dict[str, Any] = None) -> VerificationResult:
        action = params.get("action", "set") if params else "set"
        expected = params.get("text", "") if params else ""
        current = observation.observed_state.get("current_clipboard", "")

        if action in ["set", "verify"]:
            if current == expected:
                return VerificationResult(
                    verified=True,
                    postcondition_met=True,
                    message=f"Verified clipboard contains exact expected text ({len(expected)} chars)."
                )
            return VerificationResult(
                verified=False,
                postcondition_met=False,
                message=f"Clipboard readback mismatch. Expected length {len(expected)}, found {len(current)}."
            )
        return VerificationResult(verified=True, postcondition_met=True, message="Clipboard read completed.")

    def rollback(self, operation_id: str, params: Dict[str, Any] = None) -> RollbackResult:
        prev = self._previous_clip.get(operation_id)
        if prev is not None:
            clipboard_set(prev)
            return RollbackResult(success=True, message="Restored previous clipboard state.")
        return RollbackResult(success=True, message="No previous clipboard state to restore.")
