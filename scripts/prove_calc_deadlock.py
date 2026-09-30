import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from friday_core.system.window_manager import window_manager

print("[*] Probing window_manager.get_or_launch_window('calculator')...")
try:
    # Set a timeout so we don't block forever if it deadlocks
    import threading
    res_box = []
    def _test():
        try:
            ok, target, reused, msg = window_manager.get_or_launch_window("calculator", timeout=2.0)
            res_box.append((ok, target, reused, msg))
        except Exception as e:
            res_box.append(e)

    t = threading.Thread(target=_test, daemon=True)
    t.start()
    t.join(timeout=3.0)
    if t.is_alive():
        print("[!] CONFIRMED: Thread is DEADLOCKED / HUNG after 3.0s!")
    else:
        print(f"[+] Returned cleanly: {res_box}")
except Exception as ex:
    print(f"[!] Error: {ex}")
