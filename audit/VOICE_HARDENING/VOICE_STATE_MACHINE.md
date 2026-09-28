# F.R.I.D.A.Y. 3.0 — Voice State Machine Specification
**Module**: `friday_core/voice/state_machine.py`  
**Architecture**: Formal 13-State Deterministic Finite State Machine (FSM)  
**Safety Model**: Transition-Gated Watchdog Supervised Zero-Trust  

---

## 1. Formal Voice States Definition

| State Name | Mode | Description | Watchdog Limit |
|---|---|---|---|
| `OFFLINE` | Quiescent | Acoustic sensors offline, disabled by user settings or uninitialized. | Infinite |
| `IDLE` | Quiescent | Ready and standing by for push-to-talk (Ctrl+M) or wake-word detection. | Infinite |
| `LISTENING` | Active | Microphone stream active; VAD tracking ambient floor and awaiting onset. | 30.0 seconds |
| `DETECTING_SPEECH` | Active | Acoustic energy exceeded onset threshold; recording speech chunks. | 16.0 seconds |
| `TRANSCRIBING` | Active | Speech segment finalized; STT inferring text with timeout tokens. | 15.0 seconds |
| `THINKING` | Active | Spoken transcript routed to main model (`brain.query_llm`). | 120.0 seconds |
| `TOOL_CALLING` | Active | Main model generated tool call(s) for UI, web, or document tasks. | 60.0 seconds |
| `EXECUTING` | Active | Native Python tool execution and postcondition verification running. | 60.0 seconds |
| `SPEAKING` | Active | Synthesized speech playing through mixer; acoustic visualizer active. | 90.0 seconds |
| `COMPLETED` | Terminal | Turn successfully executed, postconditions verified, audio finished. | Instant -> IDLE / LISTENING |
| `FAILED` | Terminal | Error in audio stream, model, or hardware; logged to forensics. | Instant -> IDLE |
| `CANCELLED` | Terminal | User issued emergency stop (`ESC`, `STOP`, click); immediate halt. | Instant -> IDLE |
| `TIMED_OUT` | Terminal | Watchdog timer expired on stuck state; forces safe release. | Instant -> IDLE |

---

## 2. Permitted Transition Matrix

```
Current State        Allowed Next States
--------------------------------------------------------------------------------------------------
OFFLINE           -> IDLE, FAILED
IDLE              -> LISTENING, OFFLINE, THINKING (typed chat), FAILED
LISTENING         -> DETECTING_SPEECH, IDLE, CANCELLED, TIMED_OUT, FAILED, OFFLINE
DETECTING_SPEECH  -> TRANSCRIBING, LISTENING (transient click discarded), CANCELLED, TIMED_OUT, FAILED, IDLE
TRANSCRIBING      -> THINKING, LISTENING (silence/no speech), IDLE, CANCELLED, TIMED_OUT, FAILED
THINKING          -> TOOL_CALLING, EXECUTING, SPEAKING, COMPLETED, CANCELLED, TIMED_OUT, FAILED, IDLE
TOOL_CALLING      -> EXECUTING, THINKING, SPEAKING, CANCELLED, TIMED_OUT, FAILED
EXECUTING         -> THINKING, SPEAKING, COMPLETED, CANCELLED, TIMED_OUT, FAILED
SPEAKING          -> COMPLETED, LISTENING (continuous mode follow-up), IDLE, CANCELLED, TIMED_OUT, FAILED
COMPLETED         -> IDLE, LISTENING (continuous conversation follow-up)
FAILED            -> IDLE, OFFLINE
CANCELLED         -> IDLE, OFFLINE
TIMED_OUT         -> IDLE, OFFLINE
```

---

## 3. Prohibited Transition Rules

To eliminate zombie playback, infinite loops, and unmonitored recording, the following transitions are strictly prohibited and raise `VoiceStateTransitionError`:
1. **No Direct Jumps from IDLE to Execution**: `IDLE -> SPEAKING` or `IDLE -> EXECUTING` is illegal. Every voice command must pass through `LISTENING -> DETECTING_SPEECH -> TRANSCRIBING -> THINKING`.
2. **No Silent State Jumps**: `DETECTING_SPEECH -> SPEAKING` is impossible without passing through transcription and model reasoning.
3. **No Stuck Active States**: `THINKING`, `TOOL_CALLING`, or `SPEAKING` can never persist beyond their watchdog limits.
4. **Clean Cancel Recovery**: From `CANCELLED` or `FAILED`, the system may only recover to `IDLE` or transition to `OFFLINE`.

---

## 4. Continuous Conversation State Flow

In Continuous Conversation Mode:
```
[USER SPEAKS]
     │
     ▼
 LISTENING -> DETECTING_SPEECH -> TRANSCRIBING -> THINKING -> SPEAKING
                                                                 │
                                                                 ▼
                                                             COMPLETED
                                                                 │
                                             (Echo Cooldown 0.45s)
                                                                 │
                                                                 ▼
                                                             LISTENING  <───┐
                                                                 │          │
                                                                 └── (Turn 2-10)
```
- Re-entering `LISTENING` immediately after `COMPLETED` is valid and guarded by `voice_interruption_controller.is_in_echo_cooldown` (0.45s).
- During `SPEAKING`, user acoustic barge-in triggers `tts.stop_speaking()` and forces an immediate transition to `LISTENING`.
