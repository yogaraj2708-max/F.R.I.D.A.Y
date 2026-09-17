"""
F.R.I.D.A.Y. 2.0 - Known Windows Applications & Registry Scanner
Centralized application dictionary and Windows Registry App Paths extractor.
"""

import os
import logging
from typing import Dict
from friday_core.platform_guard import IS_WINDOWS

# winreg only exists on Windows. Importing it unconditionally made the whole
# package fail to import elsewhere, which also broke the test suite on CI.
if IS_WINDOWS:
    import winreg
else:  # pragma: no cover - non-Windows fallback
    winreg = None

logger = logging.getLogger("FRIDAY.SystemApps")

# Centralized known system utilities, Office suite, and Windows modern protocols
KNOWN_WINDOWS_APPS: Dict[str, str] = {
    # Microsoft Office
    "word": "winword.exe",
    "ms word": "winword.exe",
    "microsoft word": "winword.exe",
    "excel": "excel.exe",
    "ms excel": "excel.exe",
    "microsoft excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "ppt": "powerpnt.exe",
    "microsoft powerpoint": "powerpnt.exe",
    "onenote": "onenote.exe",
    "outlook": "outlook.exe",
    # Shell & System Terminals
    "powershell": "powershell.exe",
    "windows powershell": "powershell.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    # System Management
    "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "control panel": "control.exe",
    "device manager": "devmgmt.msc",
    "services": "services.msc",
    "registry editor": "regedit.exe",
    "regedit": "regedit.exe",
    "disk management": "diskmgmt.msc",
    # Tools & Accessories
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "snipping tool": "snippingtool.exe",
    "snip": "snippingtool.exe",
    "screenshot": "snippingtool.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "notepad": "notepad.exe",
    # Windows Modern / UWP Protocols
    "camera": "microsoft.windows.camera:",
    "settings": "ms-settings:",
    "windows settings": "ms-settings:",
    "clock": "ms-clock:",
    "alarm": "ms-clock:",
    "store": "ms-windows-store:",
    "microsoft store": "ms-windows-store:",
    # Folders & Shell
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "files": "explorer.exe",
    "file manager": "explorer.exe",
    "windows explorer": "explorer.exe",
    "recycle bin": "explorer.exe shell:RecycleBinFolder",
    "this pc": "explorer.exe shell:MyComputerFolder",
    "my computer": "explorer.exe shell:MyComputerFolder",
    "downloads": os.path.expandvars(r"%USERPROFILE%\Downloads"),
    "my downloads": os.path.expandvars(r"%USERPROFILE%\Downloads"),
    "downloads folder": os.path.expandvars(r"%USERPROFILE%\Downloads"),
    "desktop": os.path.expandvars(r"%USERPROFILE%\Desktop"),
    "my desktop": os.path.expandvars(r"%USERPROFILE%\Desktop"),
    "desktop folder": os.path.expandvars(r"%USERPROFILE%\Desktop"),
    "documents": os.path.expandvars(r"%USERPROFILE%\Documents"),
    "my documents": os.path.expandvars(r"%USERPROFILE%\Documents"),
    "documents folder": os.path.expandvars(r"%USERPROFILE%\Documents"),
    "pictures": os.path.expandvars(r"%USERPROFILE%\Pictures"),
    "my pictures": os.path.expandvars(r"%USERPROFILE%\Pictures"),
    "pictures folder": os.path.expandvars(r"%USERPROFILE%\Pictures"),
    "music": os.path.expandvars(r"%USERPROFILE%\Music"),
    "videos": os.path.expandvars(r"%USERPROFILE%\Videos"),
}

def get_registry_app_paths() -> Dict[str, str]:
    """Reads registered application paths from Windows 64-bit and 32-bit registry."""
    if not IS_WINDOWS or winreg is None:
        return {}

    apps: Dict[str, str] = {}
    for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
        sub = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
        try:
            with winreg.OpenKey(hkey, sub, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                count = winreg.QueryInfoKey(key)[0]
                for i in range(count):
                    try:
                        name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(hkey, f"{sub}\\{name}", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as app_key:
                            val, _ = winreg.QueryValueEx(app_key, "")
                            if val:
                                expanded = os.path.expandvars(val.strip('"'))
                                base = os.path.splitext(name)[0].lower()
                                apps[base] = expanded
                    except Exception:
                        pass
        except Exception:
            pass
    return apps
