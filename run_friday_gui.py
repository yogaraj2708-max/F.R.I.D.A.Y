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

# Set Windows AppUserModelID immediately so the process groups under F.R.I.D.A.Y. on the taskbar
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("StarkIndustries.FRIDAY.Assistant.2.0")
    except Exception:
        pass

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

def handle_cli_mode() -> bool:
    """
    Handles command line arguments when launched from a terminal.
    Returns True if a CLI argument was handled (and process should exit),
    or False to proceed to normal GUI launch.
    """
    if len(sys.argv) <= 1:
        return False

    # Attach to parent console and initialize UTF-8 streams for packaged executable
    if sys.platform == "win32":
        import ctypes
        import msvcrt
        try:
            ctypes.windll.kernel32.AttachConsole(-1)
        except Exception:
            pass

        if sys.stdout is None:
            try:
                handle = ctypes.windll.kernel32.GetStdHandle(-11)
                if handle and handle != -1 and handle != 0:
                    fd = msvcrt.open_osfhandle(handle, 0)
                    sys.stdout = open(fd, "w", encoding="utf-8", errors="replace", closefd=False)
            except Exception:
                pass
        if sys.stdout is None:
            try:
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
            except Exception:
                sys.stdout = open(os.devnull, "w", encoding="utf-8")
        else:
            try:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

        if sys.stderr is None:
            try:
                handle = ctypes.windll.kernel32.GetStdHandle(-12)
                if handle and handle != -1 and handle != 0:
                    fd = msvcrt.open_osfhandle(handle, 0)
                    sys.stderr = open(fd, "w", encoding="utf-8", errors="replace", closefd=False)
            except Exception:
                pass
        if sys.stderr is None:
            try:
                sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
            except Exception:
                sys.stderr = open(os.devnull, "w", encoding="utf-8")
        else:
            try:
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    if "--help" in sys.argv or "-h" in sys.argv:
        print("""F.R.I.D.A.Y. 3.0 — Production Tactical Assistant
Usage:
  F.R.I.D.A.Y. 3.0.exe                           Launch full Fluent Design GUI
  F.R.I.D.A.Y. 3.0.exe --verify-runtime          Verify packaged dependencies & Ollama connectivity
  F.R.I.D.A.Y. 3.0.exe --directive "<text>"       Execute text directive through packaged agent
  F.R.I.D.A.Y. 3.0.exe --voice-directive "<text>" Execute voice directive with speech synthesis
""")
        return True

    if "--verify-runtime" in sys.argv:
        import json
        res = {
            "status": "PASS",
            "frozen": getattr(sys, "frozen", False),
            "executable": sys.executable,
            "version": "3.0.0-production",
            "python_version": sys.version
        }
        test_mods = [
            "PySide6", "qfluentwidgets", "qasync", "sounddevice", "soundfile",
            "faster_whisper", "kokoro_onnx", "onnxruntime", "ollama",
            "uiautomation", "docx", "pypdf", "lxml", "psutil", "mss", "certifi"
        ]
        import_statuses = {}
        for mod in test_mods:
            try:
                __import__(mod)
                import_statuses[mod] = "OK"
            except Exception as ex:
                import_statuses[mod] = f"FAIL: {ex}"
        res["modules"] = import_statuses
        
        # Test Ollama
        try:
            import urllib.request
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode())
                models = [m.get("name") for m in data.get("models", [])]
                res["ollama"] = {
                    "connected": True,
                    "qwen3.5:9b": any("qwen3.5:9b" in m for m in models),
                    "models_count": len(models)
                }
        except Exception as ex:
            res["ollama"] = {"connected": False, "error": str(ex)}

        print(json.dumps(res, indent=2))
        return True

    if "--directive" in sys.argv or "--voice-directive" in sys.argv:
        try:
            if sys.stdout:
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            if sys.stderr:
                sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

        is_voice = "--voice-directive" in sys.argv
        flag = "--voice-directive" if is_voice else "--directive"
        idx = sys.argv.index(flag)
        if idx + 1 < len(sys.argv):
            directive_text = sys.argv[idx + 1]
            import asyncio
            from PySide6.QtWidgets import QApplication
            from friday_ui.core.engine import FridayBrain, FridaySignals, FridayVoiceEngine

            app = QApplication.instance() or QApplication(sys.argv)
            signals = FridaySignals()
            tts = FridayVoiceEngine(signals) if is_voice else None
            brain = FridayBrain(signals, tts)

            async def _run():
                print(f"[FRIDAY_PACKAGED_EXEC] Processing directive: '{directive_text}'", flush=True)
                try:
                    ans = await brain.query_llm(directive_text, stream_to_ui=False, stream_to_speech=is_voice)
                    print("=== DIRECTIVE OUTPUT START ===", flush=True)
                    print(ans, flush=True)
                    print("=== DIRECTIVE OUTPUT END ===", flush=True)
                except Exception as ex:
                    print(f"[ERROR] Directive execution failed: {ex}", flush=True)

            asyncio.run(_run())
        return True

    return False

from friday_ui.app import main

if __name__ == "__main__":
    if handle_cli_mode():
        sys.exit(0)
    if not check_single_instance():
        sys.exit(0)
    main()

