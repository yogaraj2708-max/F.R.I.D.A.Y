# GUI HANG FORENSIC REPORT

> **Classification**: `GUI_THREAD_BLOCK`
> **Status**: FIXED
> **Date**: 2026-09-29

## Summary

The F.R.I.D.A.Y. GUI became "Not Responding" during compound content-to-desktop tasks because `execute_mission()` — containing synchronous blocking I/O (Ollama HTTP, subprocess, UIA, time.sleep) — was called directly on the Qt/asyncio event loop thread without any thread offload.

## Thread Analysis

### Before Fix (BROKEN)
```
Thread: Qt Main (GUI) Thread
  ├─ Processes Windows messages (WM_PAINT, WM_TIMER, etc.)
  ├─ Runs asyncio event loop (qasync integration)
  └─ execute_mission() ← BLOCKS FOR 60-100s
       ├─ urllib.request.urlopen() ← 15-20s per model × 5 models
       ├─ subprocess.Popen() ← ~1s
       ├─ time.sleep() ← 0.2-0.4s per step
       └─ UIA calls ← 0.5-3s per call
```
**Result**: Windows message pump starved → "Not Responding" after ~5s

### After Fix (WORKING)
```
Thread: Qt Main (GUI) Thread
  ├─ Processes Windows messages ← NEVER BLOCKED
  ├─ Runs asyncio event loop
  └─ await asyncio.to_thread(execute_mission) ← YIELDS CONTROL

Thread: Worker Thread (ThreadPoolExecutor)
  └─ execute_mission() ← BLOCKS HERE (safe)
       ├─ urllib.request.urlopen()
       ├─ subprocess.Popen()
       ├─ time.sleep()
       └─ UIA calls
```
**Result**: GUI remains responsive. Mission runs in background.

## Blocking Operations Audit

| Operation | Location | Duration | Thread-Safe? |
|-----------|----------|----------|-------------|
| urllib.request.urlopen | content.py:88 | 15-20s/model | Yes |
| subprocess.Popen | apps.py | ~1s | Yes |
| time.sleep | ui_automation.py:215-239 | 0.08-0.4s | Yes |
| UIA SetActive/SetFocus | ui_automation.py:234-236 | 0.1-1s | Yes (COM) |
| UIA DocumentControl | ui_automation.py:242-244 | 0.5-3s | Yes (COM) |
| win32 SendInput | ui_automation.py | <0.1s | Yes |

All operations are thread-safe and work correctly from a worker thread.

## Lock Analysis

No deadlock risk identified:
- PEOVExecutor has no internal locks
- skill_registry has no locks around execute_skill
- MissionStore uses simple dict operations (single-threaded access from worker)
- No GUI ↔ worker circular wait possible (worker thread only writes to mission state, GUI thread only reads result after join)

## Watchdog

The fix adds a 120-second `asyncio.wait_for()` timeout:
- If mission exceeds 120s → `asyncio.TimeoutError` → user gets informative error
- GUI never freezes regardless of mission duration
- Worker thread is abandoned (daemon) but no resource leak since urllib/UIA have their own timeouts
