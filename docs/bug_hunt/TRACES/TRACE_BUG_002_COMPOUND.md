# Execution Trace: BUG-002 ("open note pad and type FRIDAY IS TESTING CONTEXT")

**Date**: 2026-09-24  
**Directive**: `"open note pad and type FRIDAY IS TESTING CONTEXT"`  
**Subsystem**: Intent Routing / Compound Intent Detection / PEOV Dispatch / App Launcher  

---

## Stage Breakdown

| Stage | Input | Output / State | Status | Duration (ms) | Notes |
|---|---|---|---|---|---|
| **1. INPUT CAPTURE** | `"open note pad and type FRIDAY IS TESTING CONTEXT"` | `cmd = "open note pad and type friday is testing context"` | OK | 0.1ms | Lowercased, whitespace stripped. |
| **2. COMPOUND DETECTION** | Raw text | **MISSING** | DEFECT | 0.0ms | No compound intent recognition parser exists. |
| **3. LAUNCH PATTERN MATCH** | `cmd` | `is_launch_intent = True` | FALSE_POSITIVE | 0.2ms | Regex `r"^(open\|launch\|start...)\s+"` stripped only `"open "`. |
| **4. TARGET EXTRACTION** | Regex group | `target = "note pad and type friday is testing context"` | DEFECT | 0.1ms | Entire remainder of sentence captured as monolithic application name! |
| **5. GATEKEEPER CALL** | `ActionIntent` | `ActionIntent(action="open_app", target="note pad and type friday is testing context")` | DEFECT | 0.5ms | Forwarded to `launch_application`. |
| **6. SHELL / SHORTCUT RESOLUTION** | String | Fuzzy search for executable | DEGRADED | 120.0ms | Finds fuzzy match on "note pad" or launches default Notepad, ignoring trailing directives. |
| **7. SUB-ACTION DISPATCH (TYPE)** | `"FRIDAY IS TESTING CONTEXT"` | **DROPPED** | DEFECT | 0.0ms | Typing sub-intent is completely lost; zero keystrokes injected. |
| **8. VERIFICATION** | None | No window or text postcondition checked | DEFECT | 0.0ms | Postcondition verification never invoked. |
| **9. USER REPORT** | String | `"Opening Note Pad And Type Friday Is Testing Context, Boss."` | INCORRECT | 0.1ms | Hallucinates successful execution of a non-existent compound app. |

---

## Root Cause Analysis
1. **Lack of Compound Intent Decomposition**: Neither `SemanticIntentRouter` nor `FridayBrain.execute_smart_skill` decomposes compound sentences (`<action1> and <action2>`) into sequential mission sub-intents.
2. **Greedy App Name Extraction**: The app launcher regex in `friday_ui/core/engine.py` greedily consumes all text following `"open "` up to the end of the line:
   ```python
   target = re.sub(r"^(open|launch|start|pull up|bring up|run|play)\s+", "", clean_launch_cmd).replace("please", "").strip()
   ```
   This causes compound actions (`and type ...`, `and calculate ...`, `and search for ...`, `and navigate to ...`) to be treated as literal application names.
3. **PEOV Mission Planner Disconnection**: While `friday_core/agent/planner.py` (`PEOVPlanner`) and `executor.py` (`PEOVExecutor`) exist in the codebase, they are only wired for a single hardcoded demo (`plan_organize_and_report`). No generalized compound DAG decomposition maps user natural language compound actions into planned, verified PEOV missions.
