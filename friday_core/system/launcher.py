"""
F.R.I.D.A.Y. 2.0 - Universal Windows Application & System Launcher
Single unified launcher implementation with zero hardcoded machine paths,
native ShellExecute execution, and zero CMD window popups.
"""

import os
import re
import sys
import time
import ctypes
import subprocess
import logging
from typing import Tuple, Dict

from friday_core.platform_guard import IS_WINDOWS
from friday_core.system.apps import KNOWN_WINDOWS_APPS, get_registry_app_paths

logger = logging.getLogger("FRIDAY.Launcher")

def safe_launch(target: str, args: str = "") -> bool:
    """
    Launches target cleanly using Windows ShellExecute or CREATE_NO_WINDOW subprocess.
    Guarantees zero CMD/console windows appear on screen.
    """
    if not IS_WINDOWS:
        logger.warning(f"[Launcher]: Cannot launch '{target}' on non-Windows host.")
        return False

    try:
        clean_target = target.strip()
        if clean_target.startswith("start "):
            clean_target = clean_target[6:].strip().strip('"')

        # Check if URL or protocol
        if (clean_target.startswith("http://") or clean_target.startswith("https://") or
            clean_target.startswith("ms-") or clean_target.startswith("microsoft.") or
            (":" in clean_target and clean_target.endswith(":"))):
            os.startfile(clean_target)
            return True

        if os.path.exists(clean_target):
            if args:
                ret = ctypes.windll.shell32.ShellExecuteW(None, "open", clean_target, args, None, 1)
                return ret > 32
            os.startfile(clean_target)
            return True

        # ShellExecuteW directly opens system registered executables
        ret = ctypes.windll.shell32.ShellExecuteW(None, "open", clean_target, args, None, 1)
        if ret > 32:
            return True
    except Exception as e:
        logger.debug(f"[Launcher]: Primary launch error on '{target}': {e}")

    # Subprocess fallback with CREATE_NO_WINDOW
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        cmd = f'start "" "{clean_target}" {args}'.strip()
        subprocess.Popen(
            cmd,
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            startupinfo=startupinfo
        )
        return True
    except Exception as e:
        logger.error(f"[Launcher]: Failed to launch '{target}': {e}")
        return False

def bring_or_launch_vscode() -> bool:
    """
    Brings an existing Visual Studio Code window to foreground or cleanly launches a fresh one.
    Uses purely dynamic environment paths (%LOCALAPPDATA%, %APPDATA%, %USERPROFILE%)
    with ZERO machine-specific username hardcoding.
    """
    if not IS_WINDOWS:
        return False

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    found_hwnds = []

    def enum_handler(hwnd, lParam):
        if user32.IsWindow(hwnd) and (user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd)):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                if "Visual Studio Code" in buff.value:
                    found_hwnds.append(hwnd)
        return True

    try:
        from ctypes import wintypes
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_handler), 0)
    except Exception:
        pass

    if found_hwnds:
        for hwnd in found_hwnds:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            try:
                fore_hwnd = user32.GetForegroundWindow()
                fore_tid = user32.GetWindowThreadProcessId(fore_hwnd, None)
                curr_tid = kernel32.GetCurrentThreadId()
                if fore_tid != curr_tid:
                    user32.AttachThreadInput(curr_tid, fore_tid, True)
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
                    user32.AttachThreadInput(curr_tid, fore_tid, False)
                else:
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
            except Exception:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
        return True

    # Terminate any hung headless Code.exe background processes
    try:
        chk = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Code.exe"], capture_output=True, text=True)
        if "Code.exe" in chk.stdout:
            subprocess.run(["taskkill", "/F", "/IM", "Code.exe"], capture_output=True, timeout=2)
            time.sleep(0.3)
    except Exception:
        pass

    # 1. Desktop / Start Menu shortcut (dynamically resolved)
    lnk_candidates = [
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Visual Studio Code.lnk"),
        os.path.expandvars(r"%USERPROFILE%\OneDrive\Desktop\Visual Studio Code.lnk"),
        os.path.expandvars(r"%USERPROFILE%\Desktop\Visual Studio Code.lnk"),
        os.path.expandvars(r"%PUBLIC%\Desktop\Visual Studio Code.lnk"),
        os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\Visual Studio Code.lnk"),
    ]
    for lnk in lnk_candidates:
        if os.path.exists(lnk):
            if safe_launch(lnk):
                return True

    # 2. Direct Code.exe with explicit WinSta0\Default desktop
    exe_candidates = [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
        r"C:\Program Files\Microsoft VS Code\Code.exe",
        r"C:\Program Files (x86)\Microsoft VS Code\Code.exe",
    ]
    for exe_path in exe_candidates:
        if os.path.exists(exe_path):
            try:
                si = subprocess.STARTUPINFO()
                si.lpDesktop = r"WinSta0\Default"
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 1
                subprocess.Popen([exe_path], startupinfo=si)
                return True
            except Exception:
                if safe_launch(exe_path):
                    return True

    return safe_launch("code")

def find_and_open_desktop_or_system_item(query: str) -> Tuple[bool, str]:
    """
    Scans Windows known apps, Registry App Paths, User Desktop, Documents, and Downloads.
    Resolves targets purely using environment variables.
    """
    q = re.sub(r"^(open|launch|start|pull up|bring up|run|play|show me)\s+", "", query.lower()).strip()
    if not q:
        return False, query

    # Conversational alias mappings
    aliases = {
        "minecraft": "tlauncher",
        "spiderman": "marvel's spider-man 2",
        "spider man": "marvel's spider-man 2",
        "rdr2": "red dead redemption 2",
        "red dead": "red dead redemption 2",
        "silksong": "hollow knight - silksong",
        "hollow knight": "hollow knight - silksong",
    }
    for alias_k, alias_v in aliases.items():
        if alias_k in q:
            q = alias_v
            break

    # 1. Check Known Windows & Office Apps
    for app_key, app_target in KNOWN_WINDOWS_APPS.items():
        if q == app_key or q == f"my {app_key}":
            if safe_launch(app_target):
                return True, app_key.title()

    # 2. Check Windows Registry App Paths
    reg_apps = get_registry_app_paths()
    clean_q = re.sub(r"[^a-zA-Z0-9]", "", q)
    if clean_q:
        for reg_name, reg_path in reg_apps.items():
            clean_reg = re.sub(r"[^a-zA-Z0-9]", "", reg_name)
            if clean_q == clean_reg or (len(clean_q) >= 4 and clean_q in clean_reg):
                if safe_launch(reg_path):
                    return True, reg_name.title()

    # 3. Scan User Desktop, Documents, Downloads, Start Menu
    search_dirs = [
        (os.path.expandvars(r"%USERPROFILE%\OneDrive\Desktop"), 60),
        (os.path.expandvars(r"%USERPROFILE%\Desktop"), 60),
        (os.path.expandvars(r"%PUBLIC%\Desktop"), 50),
        (os.path.expandvars(r"%USERPROFILE%\OneDrive\Documents"), 40),
        (os.path.expandvars(r"%USERPROFILE%\Documents"), 40),
        (os.path.expandvars(r"%USERPROFILE%\Downloads"), 30),
        (os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"), 20),
        (os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs"), 20),
    ]

    candidates = []
    for d, priority in search_dirs:
        if not os.path.exists(d):
            continue
        for root, dirs_list, files in os.walk(d):
            rel_depth = root[len(d):].count(os.sep)
            if rel_depth > 2:
                continue
            for item in files + dirs_list:
                base = os.path.splitext(item)[0]
                clean_base = re.sub(r"[^a-zA-Z0-9]", "", base.lower())
                if not clean_base:
                    continue
                score = 0
                if clean_q == clean_base:
                    score = 100 + priority
                elif clean_base.startswith(clean_q) or clean_q.startswith(clean_base):
                    score = 80 + priority
                elif clean_q in clean_base:
                    score = 60 + priority
                elif clean_base in clean_q and len(clean_base) >= 4:
                    score = 40 + priority

                if score > 0:
                    candidates.append((score, base, os.path.join(root, item)))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_name, best_path = candidates[0]
        if safe_launch(best_path):
            return True, best_name

    return False, query

def launch_application(target: str) -> Tuple[bool, str]:
    """Universal Application & File Launcher Dispatcher."""
    t = target.lower().strip()

    # 1. Visual Studio Code
    if (
        t in ["code", "vs code", "vscode", "visual studio code", "visual studio"]
        or bool(re.search(r"\b(?:vs\s*code|vscode|visual\s+studio\s+code|visual\s+studio)\b", t))
        or (t.startswith("code ") and not any(w in t for w in ["for", "of", "snippet", "example", "block", "sample", "in ", "script"]))
    ):
        bring_or_launch_vscode()
        return True, "Visual Studio Code"

    # 2. Microsoft Edge
    if (
        t in ["edge", "msedge", "microsoft edge"]
        or bool(re.search(r"\b(?:microsoft\s+edge|msedge)\b", t))
        or (bool(re.search(r"\bedge\b", t)) and any(w in t for w in ["browser", "app", "open", "launch"]))
    ):
        safe_launch("msedge", "https://www.google.com")
        return True, "Microsoft Edge"

    # 3. Google Chrome
    if (
        t in ["chrome", "google chrome"]
        or bool(re.search(r"\b(?:google\s+chrome|chrome\s+browser)\b", t))
        or (bool(re.search(r"\bchrome\b", t)) and any(w in t for w in ["browser", "app", "open", "launch"]))
    ):
        chrome_candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
        for p in chrome_candidates:
            if os.path.exists(p):
                safe_launch(p, "--new-window https://www.google.com")
                return True, "Google Chrome"
        safe_launch("chrome", "https://www.google.com")
        return True, "Google Chrome"

    # 4. Universal Windows System, Office, Desktop, Files & Registry Search
    found, item_name = find_and_open_desktop_or_system_item(t)
    if found:
        return True, item_name

    # 5. Generic fallback via safe_launch
    clean_app = re.sub(r"^(open|launch|start|pull up|bring up|run|play)\s+", "", t).strip()
    if clean_app:
        if safe_launch(clean_app):
            return True, clean_app

    return False, target
