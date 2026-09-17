"""
F.R.I.D.A.Y. 2.0 - Microsoft Office Automation Service
Provides robust Win32 COM and CLI integration for Microsoft Word, Excel, and PowerPoint.
Enables opening clean blank documents and directly inserting AI-generated drafts.
"""

import os
import sys
import tempfile
import logging
import subprocess
from typing import Tuple, Optional

logger = logging.getLogger("FRIDAY.Office")

STANDARD_WORD_PATHS = [
    r"C:\Program Files\Microsoft Office\Root\Office16\WINWORD.EXE",
    r"C:\Program Files (x86)\Microsoft Office\Root\Office16\WINWORD.EXE",
    r"C:\Program Files\Microsoft Office\Office16\WINWORD.EXE",
    r"C:\Program Files (x86)\Microsoft Office\Office16\WINWORD.EXE",
    r"C:\Program Files\Microsoft Office\Office15\WINWORD.EXE",
    r"C:\Program Files (x86)\Microsoft Office\Office15\WINWORD.EXE"
]


def find_word_executable() -> Optional[str]:
    """Locates the WINWORD.EXE binary on the local system."""
    for path in STANDARD_WORD_PATHS:
        if os.path.isfile(path):
            return path
    # Check registry or PATH
    try:
        from friday_core.system.apps import get_registry_app_paths
        reg_paths = get_registry_app_paths()
        for key in ["winword.exe", "word.exe"]:
            if key in reg_paths and os.path.isfile(reg_paths[key]):
                return reg_paths[key]
    except Exception:
        pass
    return None


def open_blank_word() -> Tuple[bool, str]:
    """
    Opens Microsoft Word with a clean, blank document.
    Uses COM automation first, falling back to executable launch if needed.
    """
    if sys.platform == "win32":
        # 1. Try Win32 COM
        try:
            import win32com.client
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = True
            word.Documents.Add()
            word.Activate()
            logger.info("Opened blank document in Microsoft Word via COM.")
            return True, "Opened blank document in Microsoft Word."
        except Exception as com_err:
            logger.debug(f"Word COM launch exception: {com_err}. Attempting binary launch...")

        # 2. Try direct WINWORD.EXE path
        word_exe = find_word_executable()
        if word_exe:
            try:
                subprocess.Popen([word_exe, "/q", "/n"])
                logger.info(f"Launched Word executable: {word_exe}")
                return True, "Launched Microsoft Word with a blank document."
            except Exception as exe_err:
                logger.warning(f"Failed launching Word executable: {exe_err}")

        # 3. Try Windows Shell 'start winword'
        try:
            subprocess.Popen("start winword", shell=True)
            logger.info("Launched Word via shell command 'start winword'.")
            return True, "Launched Microsoft Word via shell command."
        except Exception as shell_err:
            logger.warning(f"Shell launch winword failed: {shell_err}")

    return False, "Microsoft Word does not appear to be installed on this workstation."


def open_word_with_content(content: str, title: str = None) -> Tuple[bool, str]:
    """
    Opens Microsoft Word, creates a new document, and inserts the specified content.
    Also copies content to clipboard as a seamless convenience.
    """
    clean_text = content.strip()
    if not clean_text:
        return open_blank_word()

    # Convenience: Copy to clipboard
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        GMEM_MOVEABLE = 0x0002
        if user32.OpenClipboard(None):
            user32.EmptyClipboard()
            encoded = clean_text.encode("utf-16le") + b"\x00\x00"
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
            p_mem = kernel32.GlobalLock(h_mem)
            ctypes.memmove(p_mem, encoded, len(encoded))
            kernel32.GlobalUnlock(h_mem)
            user32.SetClipboardData(13, h_mem)  # CF_UNICODETEXT = 13
            user32.CloseClipboard()
    except Exception as clip_err:
        logger.debug(f"Clipboard copy note: {clip_err}")

    if sys.platform == "win32":
        # Method 1: Win32 COM Automation (Instant insertion directly into Word)
        try:
            import win32com.client
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = True
            doc = word.Documents.Add()
            # Insert text cleanly
            doc.Content.Text = clean_text
            word.Activate()
            logger.info("Successfully inserted drafted text into Word document via COM.")
            return True, "Inserted content directly into new Microsoft Word document."
        except Exception as com_err:
            logger.warning(f"Word COM content insertion error: {com_err}. Trying temp RTF fallback...")

        # Method 2: Temporary RTF / document fallback
        try:
            temp_dir = tempfile.gettempdir()
            filename = f"FRIDAY_Draft_{title.replace(' ', '_') if title else 'Document'}.rtf"
            temp_path = os.path.join(temp_dir, filename)

            # Generate basic RTF content
            rtf_body = clean_text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\par\n")
            rtf_content = "{\\rtf1\\ansi\\deff0\n{\\fonttbl{\\f0 Segoe UI;}}\n\\f0\\fs22\n" + rtf_body + "\n}"

            with open(temp_path, "w", encoding="utf-8", errors="ignore") as f:
                f.write(rtf_content)

            os.startfile(temp_path)
            logger.info(f"Created and opened temporary draft document: {temp_path}")
            return True, f"Created and opened draft at {temp_path}."
        except Exception as rtf_err:
            logger.error(f"RTF fallback error: {rtf_err}")

    return False, "Unable to insert content into Microsoft Word."
