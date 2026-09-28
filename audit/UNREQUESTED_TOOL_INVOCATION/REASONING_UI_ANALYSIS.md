# F.R.I.D.A.Y. 3.0 — Forensic Reasoning UI & State Machine Analysis
## Incident: Exposure of Raw Model Internal Monologue and Stuck "Thinking..." State

---

## 1. Executive Summary

In runtime testing of `"this is your brain"`, the GUI exhibited two severe user-experience and state-machine defects:
1. **Raw Internal Reasoning Exposure**: The ChatBubble rendered the LLM's private chain-of-thought monologue (e.g. *"The user is saying this is your brain... Web search results came back for F.R.I.D.A.Y. 2.0... I should structure my answer..."*).
2. **Stuck Thinking / Reasoning State**: The bottom HUD remained on `"Thinking (28s)..."` and `"⚡ Reasoning in progress..."` for extended durations, leaving the user with an apparent GUI freeze.

---

## 2. Root Cause Analysis

### A. Raw `<think>` Token Stream Leakage
In `friday_ui/core/engine.py` (lines 4154–4180):
- When Ollama runs a reasoning model (such as `deepseek-r1:8b`), tokens arrive in one of two formats:
  1. As a native `msg.thinking` field.
  2. Wrapped inside `<think>` and `</think>` tags within `content_token`.
- `engine.py` emits:
  ```python
  self.signals.stream_thinking.emit(thinking_token)
  ```
- In `main_window.py` (line 337), this is directly connected to:
  ```python
  self.signals.stream_thinking.connect(self.chat_view.append_thinking)
  ```
- In `chat_view.py` and `friday_ui/widgets/chat_bubble.py` (lines 301–310):
  ```python
  def append_thinking(self, token: str):
      if not self.is_thinking:
          self.is_thinking = True
          self.thinking_container.setVisible(True)
          self._thinking_expanded = True
          self.thinking_browser.setVisible(True)
          if not self.raw_text:
              p = get_current_palette()
              self.text_browser.setHtml(f"...⚡ Reasoning in progress...</div>")
      self.thinking_text += token
      self.thinking_browser.setMarkdown(self.thinking_text)
  ```
- **The Defect**:
  - `self._thinking_expanded = True` and `self.thinking_browser.setVisible(True)` **automatically expand and display** the internal thinking browser to the user in the main conversation stream.
  - The model's unformatted, raw, speculative internal planning monologue is shown verbatim to the user.

### B. Stuck "Thinking..." State
- When using `deepseek-r1:8b`, the model can produce 500–1,500 thinking tokens before generating a single answer token.
- On local CPU/GPU hardware, generating 1,000 reasoning tokens at 25–35 tokens/sec takes **28 to 45 seconds**.
- During this entire 28+ second window:
  - `self.raw_text` remains empty.
  - `self.is_thinking` remains `True`.
  - The chat bubble body displays: `⚡ Reasoning in progress...`
  - The thinking header displays: `Thinking (28s)...`
  - The bottom HUD displays: `ACTIVE // THINKING`
- If generation is interrupted, or if an unrequested web search delay is added (e.g. 5–8 seconds for DuckDuckGo), the perceived latency easily exceeds 35–50 seconds without a single user-facing answer token.

---

## 3. UI Redesign: Concise Operational Status Pills

Per User Requirement 12:
> *"The normal GUI must NOT display raw internal reasoning/planning text. Replace this with concise operational status only: ANALYZING ATTACHMENT, RETRIEVING CODE CONTEXT, CALLING WEB SEARCH, VERIFYING RESULT, COMPLETED. Do not expose private chain-of-thought content."*

### Clean Operational State Mapping:

| Pipeline Event | Old UI Display | New Operational Status |
| :--- | :--- | :--- |
| Document/Graphify Ingestion | Raw thinking expanded | `● ANALYZING ATTACHMENTS` |
| AST / Graph Traversal | Raw thinking expanded | `● RETRIEVING CODE CONTEXT` |
| Legitimate Tool Invocation | Raw thinking expanded | `● CALLING WEB SEARCH` / `● RUNNING CALCULATOR` |
| Verification / Validation | Raw thinking expanded | `● VERIFYING RESULT` |
| Generation Complete | Thought for 28.4s (expanded) | `● COMPLETED` |

### Technical Rules for Implementation:
1. **Default Collapsed/Hidden Monologue**:
   - `thinking_browser` must NEVER be expanded by default. Private `<think>` tokens must remain collapsed inside a subtle, optional inspector container or suppressed entirely from user-facing bubbles.
2. **Operational Status Display**:
   - Rather than dumping the model's raw string stream, `status_updated.emit("...")` updates the bubble's operational status pill.
3. **Deterministic Completion**:
   - As soon as the first answer token arrives, or when `stream_finished` is fired, `finish_thinking()` must be called immediately, clearing `is_thinking`, updating the label to `"● COMPLETED"`, and restoring the HUD to `idle`.
