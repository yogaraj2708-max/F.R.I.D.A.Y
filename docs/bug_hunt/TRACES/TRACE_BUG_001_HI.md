# Execution Trace: BUG-001 ("hi")

**Date**: 2026-09-24  
**Directive**: "hi"  
**Subsystem**: GUI Send -> Router -> Model Dispatch -> UI Render -> TTS  

---

## Stage Breakdown

| Stage | Input | Output / State | Status | Duration (ms) | Notes |
|---|---|---|---|---|---|
| **1. GUI SEND** | `"hi"` | `chat_view._submit_prompt()` | OK | 0.2ms | Text cleared from `prompt_input`, signal `command_submitted("hi", "hi")` emitted. |
| **2. MESSAGE HANDLER** | `"hi"` | `main_window.handle_user_command` | OK | 0.8ms | Bubble rendered for user. `_current_command_task` scheduled. |
| **3. MESSAGE NORMALIZER** | `"hi"` | `cmd = "hi"` | OK | 0.1ms | Lowercased, whitespace stripped. |
| **4. CONTEXT ASSEMBLER** | `"hi"` | No attachments | OK | 0.1ms | Passed to `execute_smart_skill`. |
| **5. SMART SKILLS CHECK** | `"hi"` | No math, code, vision, or theme match | FALLTHROUGH | 1.2ms | Cascades to semantic intent router. |
| **6. SEMANTIC ROUTER TIER 1** | `"hi"` | `SkillIntent.GENERAL_CHAT` (confidence ~0.35) | BELOW_THRESHOLD | 0.5ms | Score < 0.76 threshold; triggers Tier 2. |
| **7. SEMANTIC ROUTER TIER 2** | `"hi"` | `friday-decider` missing; fallback to `deepseek-r1:8b` | SLOW_POLL | 6,370.7ms | 8B reasoning model used as classification router! |
| **8. ROUTER RESULT** | `"hi"` | `SkillIntent.GENERAL_CHAT` | NOT_DISPATCHED | 0.1ms | `execute_smart_skill` returns `None` after testing 15 remaining regexes. |
| **9. MODEL SELECTION** | `"hi"` | Fallback to `brain.query_llm` (`deepseek-r1:8b`) | OK | 0.2ms | Signal `stream_started("friday", "Neural core...")` emitted. |
| **10. MODEL REQUEST** | `"hi"` | `POST http://localhost:11434/api/chat` | RUNNING | 200.0ms | Streaming requested. |
| **11. MODEL REASONING** | `"hi"` | DeepSeek-R1 `<think>` token generation | BLOCKING | 33,253.3ms | Model emits reasoning tokens for 33+ seconds. Chat bubble shows only `⚡ Reasoning in progress...`. |
| **12. MODEL RESPONSE** | `"hi"` | `"Hello, Boss. How are you feeling today? I'm ready to assist..."` | OK | 1,120.0ms | Content tokens streamed. |
| **13. RESPONSE PARSER** | Full text | Extracted thinking block + greeting response | OK | 1.5ms | Signal `stream_finished` emitted. |
| **14. UI RENDER** | Markdown | `chat_view.finish_stream` | OK | 45.0ms | Markdown rendered in `ChatBubble`. |
| **15. TTS SYNTHESIS** | Spoken summary | Kokoro-82M ONNX or Edge-TTS | SLOW/BLOCKING | 19,000.0ms (cold) | Pygame mixer playback or SAPI fallback. |

---

## Root Cause Analysis
1. **Missing Fast Conversational Tier 0 Skill**: Pure greetings ("hi", "hello", "hey friday", "good morning", "who are you") have no deterministic fast-path handler. Calculations ("2 + 2") and time queries ("what time is it") return in < 90ms, but greetings fall all the way through to an 8-billion parameter reasoning model (`deepseek-r1:8b`).
2. **Nano-Router Fallback to Heavy Model**: When `friday-decider` is not pre-installed in Ollama, `SemanticIntentRouter.route_tier2_nano` defaults to `self.ollama_model` (`deepseek-r1:8b`). Sending a 400-word classification prompt to an 8B model adds a 6–12 second delay just to decide that "hi" is general conversation.
3. **Reasoning Model Thinking Latency**: `deepseek-r1:8b` generates extensive internal `<think>` tokens (often 100–300 tokens) even for trivial inputs like "hi". During this 30+ second interval, the user sees only an indeterminate spinner or collapsed thinking block with zero visible response or spoken audio, leading to the reported "silent failure".
4. **Offline Resilience Gap**: When Ollama is offline or unreachable, `query_llm` catches `httpx.ConnectError` and emits an error string, but does not provide a polite conversational fallback or clear recovery guidance in speech.
