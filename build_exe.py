"""
F.R.I.D.A.Y. 2.0 - PyInstaller Executable Builder
Compiles the Python + PySide6 Fluent UI application into a standalone Windows app.
"""

import os
import sys
import subprocess

import time
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def kill_running_instances():
    try:
        subprocess.run(["taskkill", "/F", "/IM", "FRIDAY_2.0.exe"], capture_output=True)
    except Exception:
        pass
    time.sleep(1)
    dist_dir = os.path.join(BASE_DIR, "dist", "FRIDAY_2.0")
    if os.path.exists(dist_dir):
        for _ in range(5):
            try:
                shutil.rmtree(dist_dir)
                break
            except Exception:
                time.sleep(1)

def build():
    kill_running_instances()
    print("=" * 60)
    print("  COMPILING F.R.I.D.A.Y. 2.0 INTO STANDALONE WINDOWS APP")
    print("=" * 60)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",                 # Run as clean Windows desktop app without black console window
        "--name", "FRIDAY_2.0",
        "--icon", os.path.join(BASE_DIR, "friday_ui", "assets", "friday_icon.ico"),
        "--collect-all", "qfluentwidgets",
        "--collect-all", "qasync",
        "--collect-all", "certifi",
        "--collect-all", "win32com",
        "--hidden-import", "qfluentwidgets",
        "--hidden-import", "qasync",
        "--hidden-import", "certifi",
        "--hidden-import", "win32com",
        "--hidden-import", "win32com.client",
        "--hidden-import", "pythoncom",
        "--hidden-import", "sounddevice",
        "--hidden-import", "pygame",
        "--hidden-import", "speech_recognition",
        "--hidden-import", "edge_tts",
        "--hidden-import", "ollama",
        "--hidden-import", "duckduckgo_search",
        "--hidden-import", "sqlite3",
        "--hidden-import", "friday_ui",
        "--hidden-import", "friday_ui.widgets.command_bar",
        "--hidden-import", "friday_ui.widgets.operations_panel",
        "--hidden-import", "friday_core",
        "--hidden-import", "friday_core.gatekeeper",
        "--hidden-import", "friday_core.system",
        "--hidden-import", "friday_core.web",
        "--hidden-import", "friday_core.calc",
        "--hidden-import", "friday_core.settings",
        "--hidden-import", "friday_core.platform_guard",
        "--add-data", f"{os.path.join(BASE_DIR, 'friday_ui')};friday_ui",
        "--add-data", f"{os.path.join(BASE_DIR, 'friday_core')};friday_core",
        os.path.join(BASE_DIR, "run_friday_gui.py")
    ]

    print("[Build]: Running PyInstaller command:")
    print(" ".join(cmd))
    subprocess.run(cmd, cwd=BASE_DIR, check=True)
    print("\n[Build]: COMPILATION COMPLETE! Standalone app located in:")
    print(os.path.join(BASE_DIR, "dist", "FRIDAY_2.0", "FRIDAY_2.0.exe"))

if __name__ == "__main__":
    build()
