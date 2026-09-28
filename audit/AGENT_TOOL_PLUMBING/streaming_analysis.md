# F.R.I.D.A.Y. 3.0 — Streaming Tool Call Forensic Analysis

---

### 1. Executive Summary

A critical structural gap exists between Ollama's streaming protocol and F.R.I.D.A.Y.'s stream consumer in [`friday_ui/core/engine.py`](file:///c:/Users/Admin/OneDrive/Documents/jarvis%20voice/friday_ui/core/engine.py#L3927-L4000).

When native tool calling is enabled in Ollama:
- In **non-streaming mode (`stream=False`)**: Ollama parses and validates the tool call, populating `response["message"]["tool_calls"] = [ToolCall(function=Function(name=..., arguments=...))]`.
- In **streaming mode (`stream=True`)**: Depending on the underlying model and quantization:
  1. Some models (like `llama3.2:1b`) stream the tool call as raw JSON inside `chunk["message"]["content"]` (e.g. `{"type":"function","function":{"name":"web_search","parameters":{...}}}`).
  2. Other models stream tool deltas in `chunk["message"]["tool_calls"]` across sequential chunks.

In both cases, F.R.I.D.A.Y.'s current streaming loop in `FridayBrain.query_llm`:
1. Does **not** pass `tools=[...]` to `self.client.chat()`.
2. Does **not** inspect `chunk.get("message", {}).get("tool_calls")`.
3. Treats all received chunks purely as natural language speech/display tokens, immediately piping them into `self.signals.stream_token.emit(content)` and the TTS `phrase_queue`.

---

### 2. Empirical Chunk Trace Comparison

#### Non-Streaming (`stream=False`) Request with Real Schema:
```python
resp = await client.chat(
    model="llama3.2:1b",
    messages=[{"role": "user", "content": "who is jensen huang search web and tell"}],
    tools=[get_web_search_schema()],
    stream=False
)
```
**Observed Response**:
```json
{
  "role": "assistant",
  "content": "",
  "tool_calls": [
    {
      "function": {
        "name": "web_search",
        "arguments": {
          "query": "jensen huang search"
        }
      }
    }
  ]
}
```
*Result*: 100% clean, structured, native tool call with zero text hallucination.

#### Streaming (`stream=True`) with Existing `query_llm` Loop:
```python
stream = await client.chat(
    model="llama3.2:1b",
    messages=[{"role": "user", "content": "who is jensen huang search web and tell"}],
    tools=[get_web_search_schema()],
    stream=True
)
async for chunk in stream:
    content = chunk["message"].get("content", "")
    t_calls = chunk["message"].get("tool_calls", None)
```
**Observed Chunks**:
```text
Chunk 1: content='{"type":"function","function":{"name":"web_search"...' tool_calls=None
Chunk 2: content='}', tool_calls=None
Chunk 3: content='', tool_calls=None
```
*Current Engine Bug*:
`FridayBrain.query_llm` receives `Chunk 1` and treats the JSON string as user-facing markdown text, speaking aloud:
*"Left bracket quote type quote colon quote function..."* and rendering the raw JSON string directly on screen, with zero execution!

---

### 3. Root Cause Classification

- **ROOT_CAUSE**: `STREAMING TOOL-CALL INTEGRATION GAP`
  1. The API request in `query_llm` completely omits `tools=[...]`.
  2. The stream parser has no tool-call accumulator or structured tool detection.
  3. No dispatcher interceptor exists to pause UI/TTS streaming when a tool invocation is detected.
