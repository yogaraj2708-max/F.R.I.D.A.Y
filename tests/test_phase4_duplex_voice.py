"""
Tests for F.R.I.D.A.Y. 3.0 Phase 4 — True Duplex Voice, Wake Word & Interruption
Verifies:
1. WakeWordDetector classification, wake word extraction, and filler stripping.
2. Voice Emergency Stop detection ("stop", "cancel", "shut up", "abort").
3. DuplexBargeInManager acoustic energy evaluation and speech threshold cut-off.
4. DuplexVoicePipeline real-time TTS abort on barge-in.
5. Integration between EmergencyStopManager and FridayVoiceEngine.
"""

import unittest
import numpy as np
from unittest.mock import MagicMock
import asyncio

from friday_core.voice.wake_word import WakeWordDetector, DuplexBargeInManager
from friday_core.voice.duplex import DuplexVoicePipeline
from friday_core.agent.emergency_stop import EmergencyStopManager
from friday_ui.core.engine import FridayVoiceEngine, FridaySignals


class TestDuplexVoicePipeline(unittest.TestCase):
    def setUp(self):
        self.stop_mgr = EmergencyStopManager()
        self.detector = WakeWordDetector()
        self.barge_in = DuplexBargeInManager(energy_multiplier=2.5, min_rms_threshold=50.0)
        self.pipeline = DuplexVoicePipeline(
            wake_detector=self.detector,
            barge_in=self.barge_in,
            stop_mgr=self.stop_mgr
        )

    # 1. Wake Word & Voice Command Classification
    def test_wake_word_classification(self):
        wake, cmd, is_stop = self.detector.classify_utterance("hey friday what time is it")
        self.assertEqual(wake, "hey friday")
        self.assertEqual(cmd, "what time is it")
        self.assertFalse(is_stop)

        wake2, cmd2, is_stop2 = self.detector.classify_utterance("friday please open notepad")
        self.assertEqual(wake2, "friday")
        self.assertEqual(cmd2, "open notepad")
        self.assertFalse(is_stop2)

    def test_voice_emergency_stop_classification(self):
        """Voice command 'stop', 'cancel', or 'shut up' must be classified as emergency stop."""
        for phrase in ["friday stop", "hey friday cancel", "shut up", "friday abort everything", "stop"]:
            wake, cmd, is_stop = self.detector.classify_utterance(phrase)
            self.assertTrue(is_stop, f"Failed for phrase: '{phrase}'")

    # 2. Acoustic Energy & Barge-In Cut-off
    def test_barge_in_suppression_when_assistant_silent(self):
        """Audio frames must not trigger barge-in when assistant is not speaking."""
        loud_chunk = (np.ones(1024) * 500).astype(np.int16)
        res = self.barge_in.check_barge_in(
            audio_chunk=loud_chunk,
            is_assistant_speaking=False,
            ambient_baseline_rms=20.0
        )
        self.assertFalse(res)

    def test_barge_in_trigger_during_assistant_speech(self):
        """High energy user voice while assistant is speaking triggers barge-in."""
        quiet_chunk = (np.ones(1024) * 15).astype(np.int16)
        loud_user_chunk = (np.ones(1024) * 200).astype(np.int16)

        # Ambient baseline 20.0, quiet speech -> no barge in
        res_quiet = self.barge_in.check_barge_in(
            audio_chunk=quiet_chunk,
            is_assistant_speaking=True,
            ambient_baseline_rms=20.0
        )
        self.assertFalse(res_quiet)

        # Loud user burst -> triggers barge-in
        res_loud = self.barge_in.check_barge_in(
            audio_chunk=loud_user_chunk,
            is_assistant_speaking=True,
            ambient_baseline_rms=20.0
        )
        self.assertTrue(res_loud)

    # 3. Pipeline Real-Time Interruption & Abort
    def test_pipeline_audio_frame_halts_tts(self):
        tts_aborted = False
        def mock_tts_abort():
            nonlocal tts_aborted
            tts_aborted = True

        loud_frame = (np.ones(1024) * 250).astype(np.int16)
        interrupted = self.pipeline.handle_audio_frame(
            frame=loud_frame,
            is_assistant_speaking=True,
            ambient_baseline_rms=20.0,
            tts_abort_fn=mock_tts_abort
        )
        self.assertTrue(interrupted)
        self.assertTrue(tts_aborted)
        self.assertEqual(self.pipeline.barge_in_count, 1)

    def test_pipeline_transcribed_emergency_stop(self):
        tts_aborted = False
        def mock_tts_abort():
            nonlocal tts_aborted
            tts_aborted = True

        res = self.pipeline.handle_transcribed_text("friday stop", tts_abort_fn=mock_tts_abort)
        self.assertEqual(res["action"], "EMERGENCY_STOP")
        self.assertTrue(tts_aborted)
        self.assertTrue(self.stop_mgr.is_stopped())

    # 4. Engine Emergency Stop Hook Integration
    def test_voice_engine_emergency_stop_hook(self):
        signals = FridaySignals()
        tts = FridayVoiceEngine(signals)
        tts.is_speaking = True

        from friday_core.agent.emergency_stop import emergency_stop
        # Trigger emergency stop
        res = emergency_stop.trigger_stop(source="ESC")
        self.assertTrue(emergency_stop.is_stopped())
        self.assertTrue(tts.cancel_event.is_set())
        self.assertFalse(tts.is_speaking)

        # Cleanup
        emergency_stop.reset()


if __name__ == "__main__":
    unittest.main()
