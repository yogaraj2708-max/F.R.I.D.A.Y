# F.R.I.D.A.Y. 3.0 — UI State Transition Map

**Status**: CERTIFIED & PRODUCTION-READY  
**Version**: 3.0.0  

---

## 1. Runtime State Machine & Visual Indicators

F.R.I.D.A.Y. 3.0 enforces a strict state-driven presentation model. Every UI indicator reflects live underlying engine state without stale "ACTIVE forever" indicators.

```
                  ┌──────────────┐
                  │   OFFLINE    │
                  └──────┬───────┘
                         │ Provider detected
                         ▼
                  ┌──────────────┐
                  │    ONLINE    │◄─────────────────────────┐
                  └──────┬───────┘                          │
                         │ Prompt submitted                 │
                         ▼                                  │
                  ┌──────────────┐                          │
                  │   THINKING   │                          │
                  └──────┬───────┘                          │
                         │ Tool called                      │
                         ▼                                  │
                  ┌──────────────┐                          │
                  │ TOOL_CALLING │                          │
                  └──────┬───────┘                          │
                         │ Tool dispatch                    │
                         ▼                                  │
                  ┌──────────────┐                          │
                  │  EXECUTING   │                          │
                  └──────┬───────┘                          │
                         │ Execution done                   │
                         ▼                                  │
                  ┌──────────────┐                          │
                  │  VERIFYING   │                          │
                  └──────┬───────┘                          │
                         │ Synthesizing text                │
                         ▼                                  │
                  ┌──────────────┐                          │
                  │   SPEAKING   │                          │
                  └──────┬───────┘                          │
                         │ Speech done / Finalized          │
                         ▼                                  │
                  ┌──────────────┐                          │
                  │  COMPLETED   ├──────────────────────────┘
                  └──────────────┘
                         │
                         ├─► FAILED (Error detected)
                         └─► CANCELLED (Esc / Stop clicked)
```

---

## 2. State-to-Visual Indicator Matrix

| State Name | HUD Status Dot | HUD Status Label | Chat Bubble Visual | Command Bar State |
| :--- | :--- | :--- | :--- | :--- |
| `OFFLINE` | Solid Gray (`#6B7280`) | `● Offline` | No active bubble | `Send` disabled, retry pill |
| `ONLINE` | Solid Green (`#10B981`) | `● Online` | Quiescent conversation | `Send` enabled (Orange) |
| `MODEL_LOADING`| Pulse Blue (`#3B82F6`)| `● Loading Model` | `● Initializing neural core...` | `Send` disabled |
| `THINKING` | Pulse Amber (`#F59E0B`)| `● Thinking` | `● Thinking...` (Animated badge) | `■ Stop` active (Red) |
| `TOOL_CALLING` | Pulse Amber (`#F59E0B`)| `● Calling Tool` | `⚡ Calling tool: <tool_name>` | `■ Stop` active (Red) |
| `EXECUTING` | Pulse Amber (`#F59E0B`)| `● Executing` | `⚡ Executing: <tool_action>` | `■ Stop` active (Red) |
| `VERIFYING` | Pulse Cyan (`#06B6D4`)| `● Verifying` | `⚡ Verifying action output...` | `■ Stop` active (Red) |
| `SPEAKING` | Pulse Purple (`#8B5CF6`)| `● Speaking` | `✓ Thought for X.Xs` + Streaming | `■ Stop` active (Red) |
| `COMPLETED` | Solid Green (`#10B981`) | `● Online` | Collapsible `Thought Process` + `✓ Tool done` | `Send` enabled (Orange) |
| `FAILED` | Solid Red (`#EF4444`) | `● Error` | Problem-Reason-Action card | `Send` enabled (Orange) |
| `CANCELLED` | Solid Amber (`#F59E0B`)| `● Cancelled` | `[Response interrupted by user]` | `Send` enabled (Orange) |

---

## 3. Structured Professional Error States

F.R.I.D.A.Y. 3.0 strictly bans raw stack dumps, giant red boxes, or unformatted Python exception strings in the user-facing view. All runtime errors are presented using the **Problem — Reason — Action** architecture:

```html
<div style='background: rgba(239, 68, 68, 0.12); border: 1px solid #EF4444; border-radius: 8px; padding: 10px 14px;'>
    <div style='color: #EF4444; font-weight: bold;'>⚠️ Problem: Web Search Provider Unavailable</div>
    <div style='color: #9CA3AF;'>Reason: Connection to search endpoint timed out after 10.0s.</div>
    <div style='color: #F59E0B;'>Resolution: Verify network connectivity or switch to local cached documents.</div>
</div>
```

---

## 4. Intentional Empty States

| Surface | Empty State Presentation | Action Guidance Offered |
| :--- | :--- | :--- |
| **Chat View** | Monogram avatar (`F`), "F.R.I.D.A.Y. 3.0 Desktop AI Assistant" subtitle, and 5 interactive quick-action chips | Suggests Deep Research, Document Analysis, System Telemetry, Screenshot Snip, VS Code open |
| **Research View** | "Research Any Topic" banner with explanatory briefing description | Suggests prompts: *multimodal agent benchmarks*, *local LLM quant performance*, *tool protocols* |
| **Documents View**| "Document Intelligence Standing By" with metadata badge reading "Select a document" | Directs user to workspace list or semantic vector query bar |
| **Settings Panes**| Clean default values pre-populated from `friday_core.settings` | Restores default profiles instantly with "Restore Defaults" button |
