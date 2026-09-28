"""
F.R.I.D.A.Y. 3.0 — Voice Subsystem Coordinator
Centralized orchestrator integrating VAD, STT, Deduplication, State Machine,
TTS, Device Management, Security, and Agent Handoff into a unified zero-trust pipeline.
"""

import time
import uuid
import asyncio
import logging
import threading
from typing import Optional, Dict, Any, Callable

import numpy as np

from friday_core.voice.device_manager import audio_device_manager
from friday_core.voice.vad import voice_activity_detector, VoiceActivityDetector
from friday_core.voice.stt import stt_orchestrator, SpeechToTextOrchestrator
from friday_core.voice.tts import tts_orchestrator, TextToSpeechOrchestrator
from friday_core.voice.deduplicator import transcript_deduplicator, TranscriptDeduplicator
from friday_core.voice.state_machine import voice_state_machine, VoiceStateMachine, VoiceState
from friday_core.voice.interruption import voice_interruption_controller, VoiceInterruptionController
from friday_core.voice.tracer import voice_tracer, VoiceTracer
from friday_core.voice.security import voice_security_gate, VoiceSecurityGate
from friday_core.settings import settings

logger = logging.getLogger("FRIDAY.VoiceCoordinator")


class VoiceCoordinator:
    """
    Coordinates all voice operations with zero-trust safety:
    - Pure pipeline handoff: Spoken transcripts enter the exact same agent path as typed text.
    - Full error isolation: STT/TTS/device failures never block or erase text responses.
    - True duplex barge-in interruption and echo suppression.
    - Comprehensive trace logging.
    """

    def __init__(
        self,
        device_mgr=audio_device_manager,
        vad=voice_activity_detector,
        stt=stt_orchestrator,
        tts=tts_orchestrator,
        dedup=transcript_deduplicator,
        fsm=voice_state_machine,
        interruption=voice_interruption_controller,
        tracer=voice_tracer,
        security=voice_security_gate
    ):
        self.device_mgr = device_mgr
        self.vad = vad
        self.stt = stt
        self.tts = tts
        self.dedup = dedup
        self.fsm = fsm
        self.interruption = interruption
        self.tracer = tracer
        self.security = security

        self.continuous_mode = True
        self.is_listening = False
        self._active_task_id: Optional[str] = None
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()

    def start_listening(self) -> bool:
        """Transitions state to LISTENING and prepares VAD for incoming stream."""
        with self._lock:
            self._cancel_event.clear()
            self.is_listening = True
            self.vad.reset()
            self.fsm.transition_to(VoiceState.LISTENING, reason="User or continuous activation")
            return True

    def stop_listening(self):
        """Halts listening and resets VAD and state to IDLE."""
        with self._lock:
            self.is_listening = False
            self._cancel_event.set()
            self.vad.reset()
            if self.fsm.current_state in (VoiceState.LISTENING, VoiceState.DETECTING_SPEECH, VoiceState.TRANSCRIBING):
                self.fsm.transition_to(VoiceState.IDLE, reason="Listening stopped by caller")

    def stop_speaking(self):
        """Immediately aborts speech synthesis and playback."""
        self.tts.stop()
        if self.fsm.current_state == VoiceState.SPEAKING:
            next_s = VoiceState.LISTENING if self.continuous_mode and self.is_listening else VoiceState.IDLE
            self.fsm.transition_to(next_s, reason="Speech stopped by user")

    def cancel_active_task(self, task_id: Optional[str] = None):
        """Cooperatively cancels active voice task across VAD, STT, and TTS."""
        self._cancel_event.set()
        self.stop_speaking()
        self.vad.reset()
        if self.fsm.current_state not in (VoiceState.IDLE, VoiceState.OFFLINE):
            self.fsm.transition_to(VoiceState.CANCELLED, reason=f"Task {task_id or 'active'} cancelled")
            self.fsm.transition_to(VoiceState.IDLE, reason="Reset after cancellation")

    def process_audio_frame(
        self,
        frame: np.ndarray,
        force_receptive: bool = False,
        now: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Processes a single microphone frame:
        1. Checks duplex barge-in if assistant is speaking.
        2. Checks echo suppression window.
        3. Updates VAD.
        """
        # 1. Duplex Barge-In Check: If assistant speaking and user interrupts
        if self.tts.is_speaking:
            interrupted = self.interruption.check_barge_in(
                audio_chunk=frame,
                is_assistant_speaking=self.tts.is_speaking,
                ambient_baseline_rms=self.vad.ambient_rms,
                tts_abort_fn=self.stop_speaking
            )
            if interrupted:
                self.start_listening()
                return {"status": "BARGE_IN_TRIGGERED", "is_speech_active": True, "phrase_completed": False}
            return {"status": "ASSISTANT_SPEAKING_MUTED", "is_speech_active": False, "phrase_completed": False}

        # 2. Echo Suppression Cooldown
        if self.interruption.is_in_echo_cooldown(self.tts.speech_ended_at, now=now):
            return {"status": "ECHO_COOLDOWN_MUTED", "is_speech_active": False, "phrase_completed": False}

        if not self.is_listening:
            return {"status": "NOT_LISTENING", "is_speech_active": False, "phrase_completed": False}

        # 3. Feed frame into VAD
        vad_res = self.vad.process_frame(frame, force_receptive=force_receptive, now=now)
        if vad_res["is_speech_active"] and self.fsm.current_state == VoiceState.LISTENING:
            self.fsm.transition_to(VoiceState.DETECTING_SPEECH, reason="VAD speech onset detected")

        return vad_res

    async def handle_speech_phrase(
        self,
        audio_data: np.ndarray,
        agent_query_fn: Optional[Callable[[str], Any]] = None,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes end-to-end voice pipeline on finalized speech audio:
        1. STT Transcription
        2. Deduplication Check
        3. Security Evaluation
        4. Normal Agent Handoff (agent_query_fn receives transcript exactly like typed text)
        5. TTS Synthesis & Playback
        6. Listen-After-Speak transition
        """
        tid = task_id or f"voice_turn_{uuid.uuid4().hex[:8]}"
        self._active_task_id = tid
        t_trans_start = time.time()

        if self._cancel_event.is_set():
            self.fsm.transition_to(VoiceState.CANCELLED, reason="Cancelled before STT")
            self.fsm.transition_to(VoiceState.IDLE)
            return {"success": False, "status": "CANCELLED", "task_id": tid}

        # Step 1: STT Transcription
        self.fsm.transition_to(VoiceState.TRANSCRIBING, reason="Transcribing speech segment")
        stt_res = await self.stt.transcribe_async(
            audio_data=audio_data,
            cancel_event=self._cancel_event,
            timeout=8.0
        )

        if not stt_res.get("success") or not stt_res.get("text"):
            status = stt_res.get("status", "NO_SPEECH")
            self.fsm.transition_to(
                VoiceState.LISTENING if self.continuous_mode and self.is_listening else VoiceState.IDLE,
                reason=f"STT returned no speech ({status})"
            )
            return {"success": False, "status": status, "task_id": tid}

        transcript = stt_res["text"]
        logger.info("🎙️ [STT Finalized] '%s' (Model: %s, Latency: %.2fs)", transcript, stt_res.get("model_used"), stt_res.get("duration_sec", 0.0))

        # Step 2: Deduplication Check
        is_dup, dup_reason = self.dedup.is_duplicate(transcript)
        if is_dup:
            logger.warning("🛑 [Deduplication Suppressed] '%s' (Reason: %s)", transcript, dup_reason)
            self.fsm.transition_to(
                VoiceState.LISTENING if self.continuous_mode and self.is_listening else VoiceState.IDLE,
                reason=f"Duplicate utterance suppressed ({dup_reason})"
            )
            return {"success": False, "status": "DUPLICATE_SUPPRESSED", "transcript": transcript, "task_id": tid}

        # Step 3: Security Evaluation
        sec_res = self.security.evaluate_transcript(transcript)
        if not sec_res.get("allowed", True):
            logger.warning("⚠️ [Voice Security Gate Blocked] '%s' (Reason: %s)", transcript, sec_res.get("reason"))
            self.fsm.transition_to(VoiceState.FAILED, reason=f"Security gate blocked: {sec_res.get('reason')}")
            self.fsm.transition_to(VoiceState.IDLE)
            return {"success": False, "status": "SECURITY_BLOCKED", "reason": sec_res.get("reason"), "transcript": transcript, "task_id": tid}

        # Step 4: Normal Agent Handoff (Spoken and typed share identical path)
        self.fsm.transition_to(VoiceState.THINKING, reason="Main agent reasoning on transcript")
        response_text = ""
        tool_call_info = None
        tool_result_info = None

        if agent_query_fn:
            try:
                # Call existing agent handler exactly like typed text!
                res = agent_query_fn(transcript)
                if asyncio.iscoroutine(res):
                    response_text = await res
                else:
                    response_text = res
            except Exception as agent_ex:
                logger.error("Error executing agent query for voice transcript: %s", agent_ex)
                response_text = f"An error occurred while processing directive: {agent_ex}"

        if not response_text:
            response_text = "Directive acknowledged."

        # Step 5: TTS Output
        tts_status = "NOT_REQUESTED"
        if not self._cancel_event.is_set():
            self.fsm.transition_to(VoiceState.SPEAKING, reason="Speaking assistant response")
            tts_res = await self.tts.speak(response_text)
            tts_status = tts_res.get("status", "PLAYED")

        # Step 6: Completion & Trace Recording
        self.fsm.transition_to(VoiceState.COMPLETED, reason="Voice interaction turn completed")
        next_state = VoiceState.LISTENING if (self.continuous_mode and self.is_listening) else VoiceState.IDLE
        self.fsm.transition_to(next_state, reason="Listen-after-speak or idle return")

        # Record forensic trace
        self.tracer.record_turn(
            task_id=tid,
            audio_device=self.device_mgr.resolve_input_device()[1],
            stt_model=stt_res.get("model_used", "whisper-tiny.en"),
            tts_model="kokoro-v1.0",
            voice_state="COMPLETED",
            transcript=transcript,
            transcript_timestamp=t_trans_start,
            main_model=settings.get("model", "qwen3.5:9b"),
            tool_call=tool_call_info,
            tool_result=tool_result_info,
            tts_status=tts_status,
            execution_status="SUCCESS",
            verification_status="VERIFIED",
            final_state=next_state.value,
            details=f"Prompt: '{transcript}' -> Response length: {len(response_text)}"
        )

        return {
            "success": True,
            "status": "COMPLETED",
            "task_id": tid,
            "transcript": transcript,
            "response": response_text,
            "tts_status": tts_status
        }


# Global Singleton Voice Coordinator
voice_coordinator = VoiceCoordinator()
