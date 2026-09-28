# F.R.I.D.A.Y. 3.0 — End-to-End Runtime Architecture Trace
## Target Query: `"who is jensen huang search web and tell"`

---

### Complete Execution Stage Ledger

| Stage Index | Pipeline Stage | Code Location | Status | Runtime Observation / Forensic Finding |
| :---: | :--- | :--- | :---: | :--- |
| **1** | **USER INPUT** | `ChatView.prompt_input` | **PRESENT** | User types `"who is jensen huang search web and tell"` and submits. |
| **2** | **GUI CHAT HANDLER** | `friday_ui/views/main_window.py:545` (`handle_user_command`) | **PRESENT** | Emits command to `_process_command()`, sets HUD state to `"thinking"`, appends bubble to `ChatView`. |
| **3** | **MESSAGE NORMALIZATION** | `friday_ui/views/main_window.py:552` (`_process_command`) | **PRESENT** | Checks for image attachments (`[Attached Image:`), PDF attachments, and regex prefix matching. |
| **4** | **ROUTER / ORCHESTRATOR** | `friday_ui/core/engine.py:2511` (`execute_smart_skill`) | **PRESENT (BYPASSED)** | Evaluates regex prefix rules (`cmd.startswith(prefix)`). Because the query starts with `"who is"` rather than `"search web"`, all prefixes evaluate to `False`. Returns `None`. |
| **5** | **ACTIVE MODEL SELECTION** | `friday_ui/core/engine.py:814` (`_detect_best_model`) | **PRESENT** | Resolves `llama3.2:1b` (1.5 GB running at 100% GPU). |
| **6** | **MODEL API REQUEST** | `friday_ui/core/engine.py:3927` (`self.client.chat(...)`) | **PRESENT** | Dispatches HTTP POST to `http://localhost:11434/api/chat` with `model='llama3.2:1b'`, `options={'num_ctx': 4096}`, `stream=True`. |
| **7** | **TOOLS PASSED TO MODEL** | `friday_ui/core/engine.py:3927` | **MISSING (ROOT CAUSE 1)** | **CRITICAL FAILURE**: `tools=` parameter is **completely omitted**. Zero tool schemas are passed to the model. The request is pure text conversation. |
| **8** | **MODEL RESPONSE** | `ollama` response stream | **PRESENT** | Model receives the system prompt asserting `"You have REAL integrated subsystems: - WEB SEARCH & LIVE INTEL..."`. Having no callable tool interface, model outputs natural language text discussing searching for Jensen Huang. |
| **9** | **TOOL_CALL EXTRACTION** | `friday_ui/core/engine.py:3936` | **MISSING (ROOT CAUSE 2)** | Engine stream loop only accumulates text chunks into `collected` and feeds `sentence_buffer`. There is zero logic to detect, parse, or extract `tool_calls`. |
| **10** | **DISPATCHER** | N/A | **MISSING (NOT INVOKED)** | Because no `tool_calls` were extracted, no dispatcher was ever called. |
| **11** | **WEB SEARCH HANDLER** | `friday_ui/core/engine.py:648` (`fetch_web_results`) | **NOT REACHED** | Handler exists and is fully functional in Python, but was never invoked for this query. |
| **12** | **ACTUAL WEB REQUEST** | DuckDuckGo HTTP POST | **NOT EXECUTED** | Zero network calls occurred for the user's prompt. |
| **13** | **WEB RESULT** | N/A | **MISSING** | No results retrieved. |
| **14** | **TOOL RESULT IN CONTEXT** | `conversation_history` | **MISSING** | No `role: tool` message appended to LLM context. |
| **15** | **SECOND MODEL CALL** | `self.client.chat` | **NOT EXECUTED** | No second generation grounded on tool results occurred. |
| **16** | **FINAL RESPONSE** | `ChatView.add_message` | **UNGROUNDED** | User is shown plain ungrounded chat text where the model discusses searching without having searched. |
| **17** | **GUI** | `hud_state_label` | **PRESENT** | Transitions back to `idle`. |

---

### Stage Audit Verdict

- **Total Expected Stages**: 17
- **Stages Present**: 9
- **Stages Missing in Runtime Engine**: 8 (`TOOLS_PASSED_TO_MODEL`, `TOOL_CALL_EXTRACTION`, `DISPATCHER`, `WEB_SEARCH_HANDLER`, `ACTUAL_WEB_REQUEST`, `WEB_RESULT`, `TOOL_RESULT_APPENDED_TO_CONTEXT`, `SECOND_MODEL_CALL`)
- **First Point of Failure**: **Stage 7 (TOOLS PASSED TO MODEL)**. The model request is dispatched without a `tools` parameter.
