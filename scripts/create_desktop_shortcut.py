"""
F.R.I.D.A.Y. 2.0 - Desktop & Start Menu Shortcut Creator
Generates styled application shortcuts with the custom Arc Reactor icon and
registers the explicit Windows 11 AppUserModelID (StarkIndustries.FRIDAY.Assistant.2.0)
so the application binds properly to the Windows Taskbar and Start Menu.
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FRIDAY.Shortcut")

APP_USER_MODEL_ID = "StarkIndustries.FRIDAY.Assistant.2.0"
APP_DESCRIPTION = "F.R.I.D.A.Y. 2.0 - Tactical Personal Assistant"


def _set_app_user_model_id(shortcut_path: str, app_id: str = APP_USER_MODEL_ID) -> bool:
    """Sets the System.AppUserModel.ID property on a Windows shortcut file."""
    try:
        import pythoncom
        from win32com.propsys import propsys, pscon

        prop_store = propsys.SHGetPropertyStoreFromParsingName(
            shortcut_path, None, 2, propsys.IID_IPropertyStore
        )
        pv = propsys.PROPVARIANTType(app_id, pythoncom.VT_LPWSTR)
        prop_store.SetValue(pscon.PKEY_AppUserModel_ID, pv)
        prop_store.Commit()
        del prop_store
        logger.info(f"Registered AppUserModelID '{app_id}' on {shortcut_path}")
        return True
    except Exception as ex:
        logger.debug(f"win32com.propsys registration note on {shortcut_path}: {ex}")
        return False


def create_desktop_shortcut() -> bool:
    """
    Creates Windows Desktop and Start Menu shortcuts for F.R.I.D.A.Y. 2.0
    with direct pythonw execution, custom Arc Reactor icon, and AppUserModelID.
    """
    if sys.platform != "win32":
        logger.info("Desktop shortcut creation is only supported on Windows.")
        return False

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    icon_path = os.path.join(project_root, "friday_ui", "assets", "friday_icon.ico")
    gui_script = os.path.join(project_root, "run_friday_gui.py")

    # Locate pythonw.exe to run without opening a black CMD window
    venv_pythonw = os.path.join(project_root, ".venv", "Scripts", "pythonw.exe")
    fallback_pythonw = sys.executable.replace("python.exe", "pythonw.exe")

    if os.path.exists(venv_pythonw):
        target_exe = venv_pythonw
        args = f'"{gui_script}"'
    elif os.path.exists(fallback_pythonw):
        target_exe = fallback_pythonw
        args = f'"{gui_script}"'
    else:
        # Fallback to batch launcher if pythonw is not located
        target_exe = os.path.join(project_root, "Launch_FRIDAY_App.bat")
        args = ""

    success = False

    # Method 1: Using pywin32 / WScript.Shell
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")

        desktop_dir = shell.SpecialFolders("Desktop")
        programs_dir = shell.SpecialFolders("Programs")

        targets = []
        if desktop_dir and os.path.exists(desktop_dir):
            targets.append(os.path.join(desktop_dir, "F.R.I.D.A.Y. 2.0.lnk"))
        if programs_dir and os.path.exists(programs_dir):
            targets.append(os.path.join(programs_dir, "F.R.I.D.A.Y. 2.0.lnk"))

        for link_path in targets:
            try:
                shortcut = shell.CreateShortcut(link_path)
                shortcut.TargetPath = target_exe
                shortcut.Arguments = args
                shortcut.WorkingDirectory = project_root
                shortcut.Description = APP_DESCRIPTION
                if os.path.exists(icon_path):
                    shortcut.IconLocation = f"{icon_path},0"
                shortcut.WindowStyle = 1  # Normal window
                shortcut.Save()
                del shortcut

                # Bind Windows 11 AppUserModelID
                _set_app_user_model_id(link_path, APP_USER_MODEL_ID)
                logger.info(f"Shortcut created successfully at: {link_path}")
                success = True
            except Exception as item_err:
                logger.warning(f"Error creating shortcut {link_path}: {item_err}")

        if success:
            return True

    except Exception as e:
        logger.debug(f"win32com shortcut creation failed: {e}. Trying PowerShell fallback...")

    # Method 2: PowerShell fallback
    try:
        import subprocess
        ps_script = f"""
        $WshShell = New-Object -comObject WScript.Shell
        $Desktop = [System.Environment]::GetFolderPath('Desktop')
        $Programs = [System.Environment]::GetFolderPath('Programs')
        
        $Paths = @(
            (Join-Path $Desktop "F.R.I.D.A.Y. 2.0.lnk"),
            (Join-Path $Programs "F.R.I.D.A.Y. 2.0.lnk")
        )
        
        foreach ($p in $Paths) {{
            $Shortcut = $WshShell.CreateShortcut($p)
            $Shortcut.TargetPath = "{target_exe}"
            $Shortcut.Arguments = '{args}'
            $Shortcut.WorkingDirectory = "{project_root}"
            $Shortcut.Description = "{APP_DESCRIPTION}"
            if (Test-Path "{icon_path}") {{
                $Shortcut.IconLocation = "{icon_path},0"
            }}
            $Shortcut.WindowStyle = 1
            $Shortcut.Save()
        }}
        """
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], capture_output=True, text=True)
        if res.returncode == 0:
            logger.info("Shortcuts created via PowerShell fallback.")
            return True
        else:
            logger.warning(f"PowerShell shortcut error: {res.stderr}")
    except Exception as ex:
        logger.error(f"Failed to create shortcuts: {ex}")

    return success


if __name__ == "__main__":
    status = create_desktop_shortcut()
    sys.exit(0 if status else 1)
