"""
Unit and integration tests for F.R.I.D.A.Y. 3.0 Continuous Conversation Mode.
Verifies multi-turn state continuity, listen-after-speak timing,
echo suppression cooldown, and acoustic barge-in interruption.
"""

import time
import pytest
import numpy as np
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

from friday_core.voice.interruption import (
    VoiceInterruptionController,
    MIC_COOLDOWN_AFTER_SPEECH,
    voice_interruption_controller
)
from friday_core.voice.state_machine import VoiceStateMachine, VoiceState


class TestContinuousConversationMode:

    def test_echo_cooldown_window(self):
        """Verify that audio frames within MIC_COOLDOWN_AFTER_SPEECH are detected as in cooldown."""
        controller = VoiceInterruptionController(cooldown_sec=0.45)
        now = time.monotonic()
        speech_ended_at = now - 0.20  # Ended 200ms ago

        assert controller.is_in_echo_cooldown(speech_ended_at, now=now) is True

        # Now 500ms after speech ended (> 0.45s)
        speech_ended_at_old = now - 0.50
        assert controller.is_in_echo_cooldown(speech_ended_at_old, now=now) is False

    def test_acoustic_barge_in_detection(self):
        """Verify that user speech during assistant playback triggers barge-in abort."""
        controller = VoiceInterruptionController(energy_multiplier=2.5, min_rms_threshold=50.0)
        ambient_baseline = 20.0  # Threshold will be max(20 * 2.5 = 50.0, 50.0) = 50.0

        abort_called = False
        def mock_abort():
            nonlocal abort_called
            abort_called = True

        # 1. Quiet noise below threshold (RMS = 30) -> No barge-in
        quiet_chunk = np.full(1024, 30, dtype=np.int16)
        interrupted = controller.check_barge_in(
            audio_chunk=quiet_chunk,
            is_assistant_speaking=True,
            ambient_baseline_rms=ambient_baseline,
            tts_abort_fn=mock_abort
        )
        assert interrupted is False
        assert abort_called is False

        # 2. Loud user speech (RMS = 1500) -> Barge-in triggered!
        loud_chunk = np.full(1024, 1500, dtype=np.int16)
        interrupted = controller.check_barge_in(
            audio_chunk=loud_chunk,
            is_assistant_speaking=True,
            ambient_baseline_rms=ambient_baseline,
            tts_abort_fn=mock_abort
        )
        assert interrupted is True
        assert abort_called is True

    def test_barge_in_ignored_if_assistant_not_speaking(self):
        """Verify barge-in check does nothing if assistant is not speaking."""
        controller = VoiceInterruptionController()
        abort_called = False
        def mock_abort():
            nonlocal abort_called
            abort_called = True

        loud_chunk = np.full(1024, 5000, dtype=np.int16)
        interrupted = controller.check_barge_in(
            audio_chunk=loud_chunk,
            is_assistant_speaking=False,
            ambient_baseline_rms=20.0,
            tts_abort_fn=mock_abort
        )
        assert interrupted is False
        assert abort_called is False

    def test_simulated_10_turn_continuous_loop(self):
        """Simulate 10 continuous turns through state machine verifying no state drift or stuck states."""
        fsm = VoiceStateMachine(initial_state=VoiceState.IDLE)

        for turn in range(1, 11):
            # 1. Listen
            assert fsm.transition(VoiceState.LISTENING) is True
            # 2. Detect Speech
            assert fsm.transition(VoiceState.DETECTING_SPEECH) is True
            # 3. Transcribe
            assert fsm.transition(VoiceState.TRANSCRIBING) is True
            # 4. Think
            assert fsm.transition(VoiceState.THINKING) is True
            # 5. Speak
            assert fsm.transition(VoiceState.SPEAKING) is True
            # 6. Completed
            assert fsm.transition(VoiceState.COMPLETED) is True
            # 7. Listen again (Continuous turn)
            if turn < 10:
                assert fsm.transition(VoiceState.LISTENING) is True
            else:
                assert fsm.transition(VoiceState.IDLE) is True

        assert fsm.current_state == VoiceState.IDLE
