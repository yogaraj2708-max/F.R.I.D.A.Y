"""
F.R.I.D.A.Y. 2.0 - Graphical Launcher
Run this script to launch the Windows 11 Fluent Design AI Assistant.
"""

import os
import sys

# Ensure Windows SSL certificate authority bundle is explicitly registered
try:
    import certifi
    ca_bundle = certifi.where()
    if os.path.exists(ca_bundle):
        os.environ["SSL_CERT_FILE"] = ca_bundle
        os.environ["REQUESTS_CA_BUNDLE"] = ca_bundle
        os.environ["CURL_CA_BUNDLE"] = ca_bundle
except Exception as e:
    import logging
    logging.getLogger("FRIDAY.Launcher").warning(f"Failed to register custom CA bundle: {e}")

# Ensure root directory is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

def check_single_instance() -> bool:
    """Ensures only one instance of F.R.I.D.A.Y. 2.0 can run at a time."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        mutex_name = "Local\\FRIDAY_2_0_SINGLE_INSTANCE_MUTEX"
        ERROR_ALREADY_EXISTS = 183
        kernel32 = ctypes.windll.kernel32
        mutex = kernel32.CreateMutexW(None, True, mutex_name)
        last_error = kernel32.GetLastError()
        if last_error == ERROR_ALREADY_EXISTS:
            # Another instance is already active! Restore existing window to foreground
            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, "F.R.I.D.A.Y. 2.0")
            if hwnd:
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
                user32.SetForegroundWindow(hwnd)
            return False
        globals()["_app_mutex"] = mutex
        return True
    except Exception:
        return True

from friday_ui.app import main

if __name__ == "__main__":
    if not check_single_instance():
        sys.exit(0)
    main()

