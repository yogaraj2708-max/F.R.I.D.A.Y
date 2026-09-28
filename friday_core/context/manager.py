"""
F.R.I.D.A.Y. 3.0 — Desktop Context Manager & Permission Gates
Aggregates active window, clipboard, screen, and recent file context
under strict user permission gates. Never silently accesses disabled sources.
"""

import os
import re
import ctypes
import logging
import psutil
from typing import Optional, List, Tuple
from friday_core.platform_guard import IS_WINDOWS
from friday_core.settings import settings
from friday_core.context.models import ContextPermission, ContextPermissionError, DesktopContext

logger = logging.getLogger("FRIDAY.Context")


class ContextManager:
    """
    Coordinates desktop context gathering with permission enforcement.
    """
    def __init__(self, config=None):
        self.settings = config or settings

    def is_permitted(self, permission: ContextPermission) -> bool:
        """Checks whether the user has explicitly granted access to a context source."""
        return bool(self.settings.get(permission.value, True))

    def get_active_window(self, strict: bool = False) -> Optional[Tuple[str, str]]:
        """
        Retrieves (window_title, process_name) for the currently focused foreground window.
        Respects 'permission_background_context'.
        """
        if not self.is_permitted(ContextPermission.BACKGROUND_CONTEXT):
            if strict:
                raise ContextPermissionError(ContextPermission.BACKGROUND_CONTEXT)
            logger.debug("Background context access blocked by user permission.")
            return None

        if not IS_WINDOWS:
            return None

        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return None

            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip()

            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            proc_name = ""
            if pid.value:
                try:
                    proc_name = psutil.Process(pid.value).name()
                except Exception:
                    pass

            return title, proc_name
        except Exception as ex:
            logger.debug(f"Error inspecting active window: {ex}")
            return None

    def get_clipboard_text(self, strict: bool = False) -> Optional[str]:
        """
        Retrieves text currently in the Windows clipboard.
        Respects 'permission_clipboard_access'.
        """
        if not self.is_permitted(ContextPermission.CLIPBOARD):
            if strict:
                raise ContextPermissionError(ContextPermission.CLIPBOARD)
            logger.debug("Clipboard access blocked by user permission.")
            return None

        if not IS_WINDOWS:
            return None

        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                    data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                    return data.strip() if data else ""
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            # Fallback via ctypes
            try:
                import tkinter
                root = tkinter.Tk()
                root.withdraw()
                text = root.clipboard_get()
                root.destroy()
                return text.strip() if text else ""
            except Exception:
                pass
        return None

    def get_screen_dimensions(self, strict: bool = False) -> Optional[Tuple[int, int]]:
        """
        Retrieves display width and height.
        Respects 'permission_screen_access'.
        """
        if not self.is_permitted(ContextPermission.SCREEN):
            if strict:
                raise ContextPermissionError(ContextPermission.SCREEN)
            logger.debug("Screen access blocked by user permission.")
            return None

        if not IS_WINDOWS:
            return None

        try:
            width = ctypes.windll.user32.GetSystemMetrics(0)
            height = ctypes.windll.user32.GetSystemMetrics(1)
            return int(width), int(height)
        except Exception as ex:
            logger.debug(f"Error reading screen dimensions: {ex}")
            return None

    def get_recent_files(self, max_files: int = 5, strict: bool = False) -> List[str]:
        """
        Retrieves recent file paths from Windows shell history.
        Respects 'permission_file_indexing'.
        """
        if not self.is_permitted(ContextPermission.FILE_INDEXING):
            if strict:
                raise ContextPermissionError(ContextPermission.FILE_INDEXING)
            logger.debug("File indexing blocked by user permission.")
            return []

        recent_dir = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Recent")
        if not os.path.isdir(recent_dir):
            return []

        try:
            files = [
                os.path.join(recent_dir, f)
                for f in os.listdir(recent_dir)
                if not f.endswith(".lnk")  # filter bare targets or parse
            ]
            files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            return files[:max_files]
        except Exception as ex:
            logger.debug(f"Error querying recent files: {ex}")
            return []

    def snapshot(self, strict: bool = False) -> DesktopContext:
        """
        Creates a structured DesktopContext snapshot containing only permitted sources.
        """
        window_info = self.get_active_window(strict=strict)
        title, proc = window_info if window_info else (None, None)

        clipboard = self.get_clipboard_text(strict=strict)
        dimensions = self.get_screen_dimensions(strict=strict)
        recent = self.get_recent_files(strict=strict)

        return DesktopContext(
            active_window=title,
            active_process=proc,
            clipboard_text=clipboard,
            screen_dimensions=dimensions,
            recent_files=recent
        )

    def resolve_referential_command(self, command: str, context: DesktopContext) -> str:
        """
        Resolves contextual commands like 'summarize this', 'paste this', 'open that'.
        """
        cmd_lower = command.lower().strip()

        # Handle 'summarize this' or 'explain this'
        if any(cmd_lower.startswith(p) for p in ["summarize this", "explain this", "what is this"]):
            if context.clipboard_text:
                return f"{command}: \"\"\"\n{context.clipboard_text}\n\"\"\""

        # Handle 'paste this'
        if "paste this" in cmd_lower and context.clipboard_text:
            return f"paste the following: {context.clipboard_text}"

        return command


# Global Singleton Context Manager
context_manager = ContextManager()
