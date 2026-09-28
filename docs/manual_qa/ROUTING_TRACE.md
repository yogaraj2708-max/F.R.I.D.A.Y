# F.R.I.D.A.Y. 3.0 — Comprehensive End-to-End Routing Trace

**Date**: 2026-09-24  
**Auditor**: Independent Principal Debugger  
**Trace Protocol**: Section 3 Pipeline Instrument & Verification  

---

## Pipeline Stage Breakdown

```
[1. USER INPUT]
       │
       ▼
[2. NORMALIZATION & PREPROCESSING]
       │
       ▼
[3. TIER 0 FAST PATH EVALUATION]
       │ (if matched: < 1ms dispatch)
       ▼ (if unmatched)
[4. TIER 1 VECTOR EMBEDDING CENTROID MATCH]
       │ (if score >= 0.76: ~0.174ms dispatch)
       ▼ (if score < 0.76 / ambiguous)
[5. TIER 2 DISAMBIGUATION (Laya / Nano Decider)]
       │ (handles typos / slang: ~2.1s)
       ▼ (if unclassified)
[6. HEAVY REASONING LLM (DeepSeek-R1 / LLaMA)]
       │
       ▼
[7. PEOV PLANNER & DAG COMPILER]
       │
       ▼
[8. PEOV CLOSED-LOOP EXECUTOR]
       │
       ▼
[9. NATIVE WINDOWS / UI AUTOMATION TOOL]
       │
       ▼
[10. POSTCONDITION VERIFICATION]
       │
       ▼
[11. RESPONSE GENERATION & UI RENDERING]
       │
       ▼
[12. DUPLEX TTS SPEECH SYNTHESIS]
```

---

## Detailed Trace 1: Deterministic Command ("what time is it?")

| Stage | Input State | Processing Action | Output / Decision | Measured Latency | Verification & Status |
|:---|:---|:---|:---|:---:|:---:|
| **1. User Input** | `"what time is it?"` | Raw text received from GUI chat input / STT | `"what time is it?"` | 0.00 ms | Input verified |
| **2. Normalization** | `"what time is it?"` | Lowercase, whitespace trim, punctuation stripped | `"what time is it"` | 0.02 ms | OK |
| **3. Tier 0 Fast Path** | `"what time is it"` | Regex pattern match: `r"^(?:what\s+time\s+is\s+it\|...)$"` | Matched: `System Time & Date` | 0.05 ms | Deterministic Hit |
| **4. Gatekeeper Clearance** | `ActionIntent("get_time")` | Classify risk tier (Tier 0 Safe) | Authorized (No prompt required) | 0.03 ms | Clearance Granted |
| **5. Tool Execution** | `datetime.now()` | Query OS local system clock | `10:35 AM` | 0.01 ms | OS Clock Read |
| **6. Verification** | String format | Check non-empty time string | Verified valid time string | 0.01 ms | VERIFIED |
| **7. Response Generation** | Output format | Construct assistant voice response | `"The current time is 10:35 AM, Boss."` | 0.02 ms | OK |
| **8. UI Rendering** | Assistant bubble | Render bubble in Fluent ChatView | Bubble displayed | 0.85 ms | Rendered |
| **9. TTS Synthesis** | Voice generation | SAPI5 / Kokoro audio synthesis | Audio stream started | 85.00 ms | Spoken |
| **Total Pipeline Latency** | | | | **0.99 ms (excl. TTS)** | **100% Deterministic (No LLM invoked)** |

---

## Detailed Trace 2: Compound Desktop Action ("open notepad and type hello")

| Stage | Input State | Processing Action | Output / Decision | Measured Latency | Verification & Status |
|:---|:---|:---|:---|:---:|:---:|
| **1. User Input** | `"open notepad and type hello"` | Raw text received | `"open notepad and type hello"` | 0.00 ms | Input verified |
| **2. Normalization** | `"open notepad and type hello"` | Trim, lowercase | `"open notepad and type hello"` | 0.02 ms | OK |
| **3. Compound Parser** | `CompoundIntentParser.parse()` | Grammar decomposition into AST steps | `Step 1: open_app("notepad")`<br>`Step 2: ui_type_text("hello")` | 0.25 ms | Multi-step AST Compiled |
| **4. PEOV DAG Formulation** | `PEOVPlanner.plan_compound_directive()` | Formulate DAG with dependencies | `MissionState(steps=[step_1, step_2])` | 0.35 ms | DAG Formulated |
| **5. PEOV Step 1 Execution** | `tool_id="app_launcher"` | ShellExecute `notepad.exe` | Process spawned | 12.50 ms | Process Running |
| **6. Step 1 Verification** | `UIA WindowControl("Notepad")` | Poll window handle and readiness | Notepad window verified active | 120.00 ms | Window Verified |
| **7. PEOV Step 2 Execution** | `tool_id="ui_type_text"` | Focus edit control, type text | Text injected | 45.00 ms | Injected |
| **8. Step 2 Verification** | `DocumentControl.GetValuePattern()` | Read back text from Notepad buffer | Content verified == `"hello"` | 8.50 ms | Postcondition Verified |
| **9. Response Generation** | Mission completed | Format verified summary | `"Successfully opened notepad and typed 'hello', Boss. All operations verified."` | 0.05 ms | VERIFIED |
| **10. UI & TTS** | Bubble + speech | Render bubble, speak response | Complete | 92.00 ms | Success |
| **Total Pipeline Latency** | | | | **186.67 ms (Real Windows UIA)** | **Zero False-Success** |

---

## Detailed Trace 3: Defective Legacy Trace (Why "close notepad" took 18s and False-Succeeded)

| Stage | What Happened in Defective Code | Flaw Identified |
|:---|:---|:---|
| **User Input** | `"close notepad"` | Command entered |
| **Tier 0 Check** | Looked only for `"kill process "` or `"terminate process "` | Did not match `"close notepad"`, fell through |
| **Semantic Router** | Inverted order called Ollama `friday-decider` | Ollama model load / inference delay added 2-7 seconds |
| **Router Result** | Failed to find dedicated skill, returned `GENERAL_CHAT` | Routed to `query_llm` |
| **Model Invocation** | Invoked `deepseek-r1:8b` | 8-billion parameter model ran for 18.5 seconds generating `<think>` tokens |
| **Model Output** | Generated string: `"I have closed Notepad for you."` | **Hallucination! No OS process was ever killed!** |
| **Status Reported** | UI displayed: `"I have closed Notepad for you."` | **FALSE SUCCESS: Notepad was still running!** |
