# F.R.I.D.A.Y. 3.0 — Critical Agent Tool Plumbing Root-Cause Report
## Forensic Proof & Engineering Dissection

---

### Executive Forensic Answers to the 10 Critical Questions

#### 1. Why did the model say it would search but not actually search?
**Answer**:
The model was informed in natural language via the system prompt ([`friday_ui/core/engine.py:844-845`](file:///c:/Users/Admin/OneDrive/Documents/jarvis%20voice/friday_ui/core/engine.py#L844-L845)) that it possesses `"REAL integrated subsystems: - WEB SEARCH & LIVE INTEL"`. However, in [`query_llm`](file:///c:/Users/Admin/OneDrive/Documents/jarvis%20voice/friday_ui/core/engine.py#L3927), the model request was dispatched as a pure text conversation **without any callable tool schemas**. The model recognized from the prompt text that web search was relevant to the query, but having no API tool interface to invoke it, it produced natural language text describing its intent to search (e.g. *"I should initiate a web search..."* or *"I can search using my live intel subsystem..."*).

#### 2. Was the tool schema missing?
**Answer**: **YES**.
In [`friday_ui/core/engine.py:3927-3932`](file:///c:/Users/Admin/OneDrive/Documents/jarvis%20voice/friday_ui/core/engine.py#L3927-L3932):
```python
response_stream = await self.client.chat(
    model=self.model,
    messages=messages_to_send,
    options={'temperature': 0.7, 'top_p': 0.9, 'num_ctx': 8192},
    stream=True
)
```
The parameter `tools=[...]` was **never passed**. The request payload contained only `model`, `messages`, `options`, and `stream`.

#### 3. Was `tool_choice` missing?
**Answer**: **YES**.
Neither `tools` nor `tool_choice` was passed to the provider client.

#### 4. Did the active model support native tools?
**Answer**: **YES**.
Empirically proven via live runtime test in [`scripts/audit_tool_plumbing.py`](file:///c:/Users/Admin/OneDrive/Documents/jarvis%20voice/scripts/audit_tool_plumbing.py):
When `tools=[get_web_search_schema()]` was provided to the active model (`llama3.2:1b`), the model immediately and autonomously emitted:
```python
tool_calls=[ToolCall(function=Function(name='web_search', arguments={'query': 'latest NVIDIA news'}))]
```
The model's native function-calling capability is 100% operational; it was simply starved of tool schemas by the caller.

#### 5. Did the adapter drop `tool_calls`?
**Answer**: **YES**.
There was no tool adapter or tool-call extractor in `FridayBrain.query_llm`. The engine assumed the model only outputs plain text tokens.

#### 6. Did streaming drop `tool_calls`?
**Answer**: **YES**.
In streaming mode (`stream=True`), Ollama streams tool calls as raw JSON tokens or tool deltas. The streaming loop in `query_llm` blindly piped all incoming chunks directly to the UI markdown stream and the TTS audio synthesis buffer as text, rather than intercepting tool calls for execution.

#### 7. Did dispatcher registration fail?
**Answer**: **YES**.
`web_search` was not registered as a tool in `SkillRegistry` ([`friday_core/skills/registry.py`](file:///c:/Users/Admin/OneDrive/Documents/jarvis%20voice/friday_core/skills/registry.py)). It only existed as a standalone helper function `fetch_web_results` in `friday_ui/core/engine.py`.

#### 8. Did normal chat bypass the agent loop?
**Answer**: **YES**.
Normal chat calls `FridayBrain.query_llm()` directly, which had zero tool calling, zero tool execution, and zero multi-turn tool-result loop. It was a 1-shot conversational stream, not an agent loop.

#### 9. Is manual deep search a separate legacy path?
**Answer**: **YES**.
Manual deep search runs through `handle_research(topic, depth)` in `friday_ui/views/main_window.py` via `DeepResearchWorker`, completely isolated from normal chat. It only activates when the user clicks the `+` button in the UI or enters a prompt beginning strictly with `"deep research..."`.

#### 10. Are there similar failures for UI, vision, documents, browser, etc.?
**Answer**: **YES — SYSTEMIC ROOT CAUSE**.
While `friday_core/skills/registry.py` defines 23 pluggable `BaseSkill` implementations (including `ui_type_text`, `app_launcher`, `calculate`, `system_telemetry`, `browser_navigate`, `memory`, `timer`), **none of these schemas were ever exposed to `query_llm`**. The entire system relied on hardcoded regex prefixes in `execute_smart_skill()`. Any command phrased with natural language variations that did not match the regex prefix fell through to `query_llm()`, where the model had zero tool access and hallucinated discussions about performing actions.

---

### Root-Cause Summary Table

| Layer | Expected Behavior | Observed Code Behavior | Forensic Verdict |
| :--- | :--- | :--- | :--- |
| **System Prompt** | State real callable tools | States capabilities in text (`LIVE INTEL`, etc.) but provides no schemas | **MISLEADING TO MODEL** |
| **Model Request** | `client.chat(model, messages, tools=tools)` | `client.chat(model, messages, options=options)` | **TOOLS NOT EXPOSED** |
| **Stream Parser** | Detect & accumulate `tool_calls` | Only reads `chunk["message"]["content"]` | **TOOL CALLS UNHANDLED** |
| **Dispatcher Loop** | Execute tool, append result, re-invoke model | Does not exist in `query_llm` | **AGENT LOOP MISSING** |
| **Tool Registry** | Register `web_search` with typed schema | `web_search` absent from registry | **UNREGISTERED CAPABILITY** |
