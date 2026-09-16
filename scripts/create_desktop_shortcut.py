"""
F.R.I.D.A.Y. 2.0 - Desktop Shortcut Creator
Generates a styled desktop application shortcut with the custom Arc Reactor icon.
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FRIDAY.Shortcut")


def create_desktop_shortcut() -> bool:
    """Creates a Windows Desktop shortcut for F.R.I.D.A.Y. 2.0 with custom icon."""
    if sys.platform != "win32":
        logger.info("Desktop shortcut creation is only supported on Windows.")
        return False

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_bat = os.path.join(project_root, "Launch_FRIDAY_App.bat")
    icon_path = os.path.join(project_root, "friday_ui", "assets", "friday_icon.ico")

    if not os.path.exists(target_bat):
        logger.warning(f"Target launcher not found: {target_bat}")
        return False

    # Method 1: Using pywin32 / WScript.Shell
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
        desktop_dir = shell.SpecialFolders("Desktop")
        shortcut_path = os.path.join(desktop_dir, "F.R.I.D.A.Y. 2.0.lnk")

        shortcut = shell.CreateShortcut(shortcut_path)
        shortcut.TargetPath = target_bat
        shortcut.WorkingDirectory = project_root
        shortcut.Description = "F.R.I.D.A.Y. 2.0 - Tactical Personal Assistant"
        if os.path.exists(icon_path):
            shortcut.IconLocation = f"{icon_path},0"
        shortcut.WindowStyle = 7  # Minimized launch for the batch stub
        shortcut.Save()
        logger.info(f"Desktop shortcut created successfully at: {shortcut_path}")
        return True
    except Exception as e:
        logger.debug(f"win32com shortcut creation failed: {e}. Trying PowerShell fallback...")

    # Method 2: PowerShell fallback
    try:
        import subprocess
        ps_script = f"""
        $WshShell = New-Object -comObject WScript.Shell
        $Desktop = [System.Environment]::GetFolderPath('Desktop')
        $Shortcut = $WshShell.CreateShortcut("$Desktop\\F.R.I.D.A.Y. 2.0.lnk")
        $Shortcut.TargetPath = "{target_bat}"
        $Shortcut.WorkingDirectory = "{project_root}"
        $Shortcut.Description = "F.R.I.D.A.Y. 2.0 - Tactical Personal Assistant"
        if (Test-Path "{icon_path}") {{
            $Shortcut.IconLocation = "{icon_path},0"
        }}
        $Shortcut.WindowStyle = 7
        $Shortcut.Save()
        """
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True)
        if res.returncode == 0:
            logger.info("Desktop shortcut created via PowerShell fallback.")
            return True
        else:
            logger.warning(f"PowerShell shortcut error: {res.stderr}")
    except Exception as ex:
        logger.error(f"Failed to create desktop shortcut: {ex}")

    return False


if __name__ == "__main__":
    success = create_desktop_shortcut()
    sys.exit(0 if success else 1)
