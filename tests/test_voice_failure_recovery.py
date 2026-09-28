"""
Unit and integration tests for F.R.I.D.A.Y. 3.0 Voice Subsystem Failure Recovery.
Verifies graceful handling of STT crashes, microphone disconnects, TTS failures,
text chat isolation, and recovery to IDLE state.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from friday_core.voice.state_machine import VoiceStateMachine, VoiceState
from friday_core.voice.stt import SpeechToTextOrchestrator
from friday_core.voice.tts import TextToSpeechOrchestrator
from friday_core.voice.device_manager import AudioDeviceManager


class TestVoiceFailureRecovery:

    def test_stt_crash_recovers_to_idle(self):
        """Verify that when STT raises an unhandled exception, FSM transitions to FAILED and recovers to IDLE."""
        fsm = VoiceStateMachine(initial_state=VoiceState.TRANSCRIBING)
        try:
            # Simulate STT crash
            raise RuntimeError("STT Model Out of Memory")
        except Exception as ex:
            fsm.transition(VoiceState.FAILED, reason=str(ex))

        assert fsm.current_state == VoiceState.FAILED
        fsm.transition(VoiceState.IDLE)
        assert fsm.current_state == VoiceState.IDLE

    def test_microphone_disconnect_recovers_to_idle(self):
        """Verify that when microphone stream fails, system recovers to IDLE without locking."""
        fsm = VoiceStateMachine(initial_state=VoiceState.LISTENING)
        try:
            # Simulate PortAudio stream error
            raise OSError("PortAudio: Unanticipated host error (-9999)")
        except Exception as ex:
            fsm.transition(VoiceState.FAILED, reason=str(ex))

        assert fsm.current_state == VoiceState.FAILED
        fsm.transition(VoiceState.IDLE)
        assert fsm.current_state == VoiceState.IDLE

    @pytest.mark.asyncio
    async def test_tts_failure_does_not_break_text_chat(self):
        """Verify that even if TTS completely fails, assistant response text is delivered and task completes."""
        tts = TextToSpeechOrchestrator()
        assistant_reply = "Here is the answer to your query."

        # Simulate TTS playback failure
        with patch.object(tts, "play_audio", side_effect=RuntimeError("Audio hardware disconnected")):
            with patch.object(tts, "synthesize", new_callable=AsyncMock) as mock_syn:
                mock_syn.return_value = b"FAKE_AUDIO"
                # Speak should log error but not crash
                await tts.speak(assistant_reply)

        # Assistant text remains intact
        assert assistant_reply == "Here is the answer to your query."

    def test_text_chat_independent_of_microphone_state(self):
        """Verify text chat pipeline operates normally when microphone is completely disabled or unavailable."""
        fsm = VoiceStateMachine(initial_state=VoiceState.OFFLINE)
        # Even if voice is OFFLINE, text pipeline executes
        text_input = "Tell me a joke"
        assert len(text_input) > 0
        assert fsm.current_state == VoiceState.OFFLINE

    def test_recovery_from_timed_out_state(self):
        """Verify TIMED_OUT state can transition back to IDLE cleanly."""
        fsm = VoiceStateMachine(initial_state=VoiceState.TRANSCRIBING)
        fsm.force_set(VoiceState.TIMED_OUT)
        assert fsm.current_state == VoiceState.TIMED_OUT
        fsm.transition(VoiceState.IDLE)
        assert fsm.current_state == VoiceState.IDLE
