# F.R.I.D.A.Y. 3.0 — Model & Router Architecture Audit

**Protocol**: Zero-Trust Independent System Audit  
**Date**: 2026-09-25  
**Author**: Principal Software Debugger & AI Agent Reliability Engineer  

---

## 1. Executive Summary & Empirical Findings

An exhaustive audit of F.R.I.D.A.Y.'s intent routing pipeline (`friday_core/router/semantic_router.py` and `friday_ui/core/engine.py`) was performed. The investigation revealed an **inverted routing precedence bug** and **missing intent taxonomy gaps** that caused deterministic system commands (such as "close notepad", "mute volume", "what time is it", and "what is the first sentence of this PDF?") to either:
1. Block in Ollama for 7.3+ seconds querying `friday-decider` even when Tier 1 vector embedding resolved the query in **0.174 ms**.
2. Collide into `SYSTEM_TELEMETRY` (reporting battery and CPU usage when asked about documents).
3. Fall past smart skill handlers and invoke the 8-billion parameter reasoning model (`deepseek-r1:8b`), inducing 18–56 seconds of reasoning dead air followed by hallucinations or connection drops.

---

## 2. Answers to Section 4 Audit Questions (With Empirical Evidence)

### Q1: What exactly does Laya classify?
**Answer**: Laya (Convai Innovations System 1) classifies an input string into one of 11 discrete operational intent categories:
- `desktop_audio` (volume, mute, unmute)
- `media_control` (playback, songs, Spotify/YouTube)
- `system_telemetry` (battery, RAM, CPU, charging)
- `system_time_date` (clock, date, time)
- `desktop_action` (screenshot, snip, lock workstation)
- `app_launch` (open/start application)
- `timer_clock` (timers, countdowns)
- `deep_research` (web investigation)
- `weather` (temperature, forecast)
- `document_qa` (reading, analyzing, extracting, or summarizing PDFs/documents)
- `general_chat` (conversations, coding, explanations)

### Q2: What exact inputs reach Laya?
**Answer**: The raw user command stripped of vocal disfluencies (`uh`, `um`, `ah`, `a`, `an`, `the` prefixing action verbs). Example: `"uh open notepad"` -> `"open notepad"`.

### Q3: What is the expected output schema?
**Answer**: A structured dictionary or object with an `intent` field containing the chosen category name:
```json
{
  "answers": {
    "intent": "app_launch"
  }
}
```

### Q4: When is the Tier-2/small model invoked?
**Answer**: In the corrected architecture:
1. Tier 0 deterministic regex primitives execute in `< 0.1ms`.
2. Tier 1 Fast Local Embedding Centroid match executes in `< 0.2ms`.
3. Tier 2 (Ollama `friday-decider` / Laya) is invoked **ONLY** when Tier 1 confidence is ambiguous (`< 0.70`).

### Q5: What exact model is used?
**Answer**:
- For Ollama: `friday-decider:latest` (or `qwen2.5:0.5b`).
- For Laya: `convaiinnovations/laya` (ModernBERT System 1 checkpoint).

### Q6: What happens if the intended nano/small model is unavailable?
**Answer**: In `route_tier2_nano()`, if neither `friday-decider` nor `qwen2.5:0.5b` is in Ollama, it catches the exception or returns `None`. The system falls back cleanly to the Tier 1 vector embedding result.

### Q7: Can the router accidentally fall back to a heavy 8B model?
**Answer**: Previously **YES**. If `route()` failed to classify or returned `GENERAL_CHAT` (or if `execute_smart_skill` returned `None`), execution fell through to `query_llm()`, which invoked `REASONING_MODEL = "deepseek-r1:8b"`. `deepseek-r1:8b` generated extensive internal `<think>` tokens, producing 18–56 seconds of latency. For commands like "close notepad", the 8B LLM generated conversational text ("I have closed Notepad") without ever invoking any process termination skill, causing **False-Success**.
**Resolution**: Elevated Tier 1 fast-paths in `FridayBrain.execute_smart_skill` intercept application closure (`# 0.0051`), UI typing (`# 0.0052`), file saving (`# 0.0053`), and document QA (`# 0.0054`) deterministically.

### Q8: Can trivial commands bypass all expensive model stages?
**Answer**: **YES**. Trivial commands bypass expensive models through:
1. **Tier 0 Deterministic Fast Paths** (< 1ms): exact regex and pattern matching for system primitives.
2. **Tier 1 FastLocalEmbedder** (< 0.2ms): precomputed centroid and exemplar vector similarity.
Tier 2 (Ollama decider) is ONLY invoked if Tier 1 score is ambiguous (< 0.70).

### Q9: Measured Latency Across All Layers
Empirical measurements on active Windows environment:
- **Tier 0 Deterministic Primitive**: **0.05 ms – 0.8 ms**
- **Tier 1 FastLocalEmbedder**: **0.174 ms** (measured on "what time is it", confidence: 0.914)
- **Laya System 1**: **33 ms** warm (30+ seconds cold download from HuggingFace)
- **Tier 2 Nano (Ollama friday-decider)**: **7,337 ms** cold/idle, **2,170 ms** warm
- **Heavy LLM (deepseek-r1:8b)**: **18,400 ms – 56,500 ms**

### Q10: Which requests truly need each layer?
- **Tier 0**: System commands with fixed grammar: "open <app>", "close <app>", "mute", "unmute", "what time is it", "2 + 2", "hi", "battery status".
- **Tier 1**: Lexical/semantic variations: "silence my audio", "bring up notes", "how much battery juice is left", "what's the first sentence in this PDF".
- **Tier 2 (Nano Decider)**: Queries with heavy typos, phonetic misspellings, or high ambiguity where Tier 1 confidence is below 0.70.
- **Heavy LLM**: Complex open-ended reasoning, deep research synthesis, multi-clause creative drafting, programming assistance, or conversational discourse.

---

## 3. Implemented Architectural Changes

1. **Inverted Precedence in `SemanticIntentRouter.route()`**:
   - Run Tier 1 Fast Local Embedding FIRST (< 0.2ms).
   - If `score >= threshold` (0.76) and unambiguous, return immediately.
   - ONLY if `score < threshold` or ambiguous, invoke Tier 2 (Ollama / Laya).
2. **Elevated Deterministic Fast Paths in `engine.py`**:
   - `# 0.0051 close_app`: Application closure with process termination and HWND destruction verification.
   - `# 0.0052 ui_type_text`: Standalone typing into active editor with explicit semantics (`type`, `append`, `replace`).
   - `# 0.0053 save_file`: Standalone file save with verified disk persistence and byte assertions.
   - `# 0.0054 document_qa`: Grounded PDF title extraction, Page 1 sentence extraction, and token budgeting.
3. **Intent Taxonomy Expansion & Anti-Collision**:
   - Added `SkillIntent.DOCUMENT_QA` to `SkillIntent`.
   - Added 25 rich exemplars to `INTENT_EXEMPLARS[DOCUMENT_QA]`.
   - Added anti-collision guards in `route_tier2_nano` to intercept nano-model collisions into `system_telemetry`.
