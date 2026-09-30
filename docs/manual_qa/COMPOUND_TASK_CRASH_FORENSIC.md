# COMPOUND TASK CRASH FORENSIC REPORT

> **Root Cause**: `GUI_THREAD_BLOCK`
> **Severity**: CRITICAL — Application "Not Responding"
> **Status**: **FIXED** — 12/12 regression tests passing
> **Date**: 2026-09-29

## Crash Reproduction

**Command**: `"write a summary of Harry Potter and put it in my note pad"`

**Observed**:
- Notepad opened ✅
- F.R.I.D.A.Y. became "Not Responding" ❌
- Notepad remained empty ❌
- Mission did not complete ❌

## Root Cause: `GUI_THREAD_BLOCK`

`execute_mission()` ran **synchronously** on the Qt/asyncio event loop thread. All blocking I/O — Ollama HTTP requests, subprocess launches, UI Automation calls, and `time.sleep()` — executed directly on the GUI thread, preventing Windows message processing for 60-100 seconds.

### Exact Blocking Chain

```
Qt GUI event loop (main thread)
  └─ asyncio task: handle_bar_command()              [app.py:162]
       └─ await execute_smart_skill(command)          [engine.py:2788]
            └─ self.executor.execute_mission()        [engine.py:3340] ← SYNCHRONOUS
                 └─ while loop: 5 DAG steps           [executor.py:76]
                      ├─ Step 1: app_launcher
                      │    └─ subprocess.Popen()      (~1s) ✅ Notepad opens
                      ├─ Step 2: content_generation   ← HANG POINT
                      │    └─ _query_local_ollama()   [content.py:60]
                      │         └─ urllib.request.urlopen(timeout=15-20s)
                      │              └─ Tries 5 models × 15-20s = 60-100s BLOCKING
                      ├─ Step 3: ui_focus
                      │    └─ time.sleep(0.2)         BLOCKS
                      ├─ Step 4: ui_type_text
                      │    └─ time.sleep(), UIA calls  BLOCKS
                      └─ Step 5: ui_verify_content
                           └─ UIA calls               BLOCKS
```

### Last Successful Step
`Step 1: app_launcher` — Notepad opens successfully.

### First Failed Transition
`Step 1 → Step 2` — `content_generation` calls `urllib.request.urlopen()` which blocks the Qt event loop thread for 15-100 seconds. Windows reports "Not Responding" after ~5 seconds of unresponsive message pump.

## Evidence

| Evidence | Finding |
|----------|---------|
| Engine log | Last entry at 20:26:17, crash at ~20:28 — no compound mission logged |
| Screenshot | Title bar shows "(Not Responding)", status shows "THINKING" |
| Notepad | Open, empty (0 characters, Ln 1, Col 1) |
| executor.py | `execute_mission()` is `def` (synchronous), not `async def` |
| engine.py:3340 | Called without `await` or thread offload |
| content.py:60 | `urllib.request.urlopen()` — synchronous blocking HTTP |
| ui_automation.py | `time.sleep()`, UIA `.SetActive()`, `.SetFocus()` — all blocking |

## Fix Applied

**File**: engine.py:3340-3356

```diff
-                mission_res = self.executor.execute_mission(compound_mission)
+                try:
+                    mission_res = await asyncio.wait_for(
+                        asyncio.to_thread(self.executor.execute_mission, compound_mission),
+                        timeout=120.0
+                    )
+                except asyncio.TimeoutError:
+                    return "⚠️ Compound operation timed out after 120 seconds..."
+                except Exception as ex:
+                    return f"⚠️ Compound operation failed: {ex}"
```

### What this fixes:
1. `asyncio.to_thread()` — Offloads the entire mission execution to a worker thread. The Qt event loop continues processing messages.
2. `asyncio.wait_for(timeout=120.0)` — Bounded mission timeout prevents infinite hangs.
3. `except` block — Crash containment ensures a failed mission returns an error message instead of freezing the app.

### What was NOT changed:
- No model changes
- No voice pipeline changes
- No UI appearance changes
- No architecture redesign
- executor.py internals unchanged
- skill framework unchanged

## Regression Test

test_compound_task_crash_regression.py — 12/12 passed

| Test | What it validates |
|------|-------------------|
| test_crash_command_parsed | Crash command produces valid 5-step plan |
| test_execute_mission_runs_on_worker_thread | Mission executes on worker, not main thread |
| test_asyncio_to_thread_offload | asyncio.to_thread pattern works with executor |
| test_timeout_containment | Hanging mission interrupted by timeout |
| test_exception_containment | Crashing mission propagates exception cleanly |
| test_gui_thread_remains_responsive | Heartbeats fire during mission (GUI responsive) |
| test_app_accepts_commands_after_failure | System accepts new commands after failure |
| test_repeated_commands_do_not_deadlock | Sequential missions don't deadlock |
| test_content_generation_blocks_worker_not_main | Blocking I/O runs on worker thread only |
| test_harry_potter_summary_plan | DAG structure correct |
| test_content_gen_uses_variable_ref | Type step uses $content_generation ref |
| test_no_literal_text_in_type_step | No garbage literal text in type step |

## Post-Fix Expected Behavior

### Success path:
```
USER REQUEST → compound planner → worker thread → Ollama generates →
Notepad types → readback verified → "Successfully composed and inserted content"
```

### Failure path:
```
USER REQUEST → compound planner → worker thread → timeout/error →
"⚠️ Compound operation failed: <reason>" → GUI remains responsive
```
