"""
F.R.I.D.A.Y. 3.0 — True Duplex Voice Pipeline
Coordinates bidirectional voice streams, real-time user barge-in cut-offs,
and voice emergency stops.
"""

import asyncio
import logging
from typing import Optional, Callable
import numpy as np
from friday_core.voice.wake_word import WakeWordDetector, DuplexBargeInManager, wake_word_detector, barge_in_manager
from friday_core.agent.emergency_stop import emergency_stop

logger = logging.getLogger("FRIDAY.DuplexVoice")


class DuplexVoicePipeline:
    """
    Manages true duplex audio processing:
    - Hands-free wake word recognition
    - Instant barge-in interruption during speech output
    - Voice emergency stop propagation
    """
    def __init__(
        self,
        wake_detector: Optional[WakeWordDetector] = None,
        barge_in: Optional[DuplexBargeInManager] = None,
        stop_mgr=None
    ):
        self.wake_detector = wake_detector or wake_word_detector
        self.barge_in = barge_in or barge_in_manager
        self.stop_mgr = stop_mgr or emergency_stop
        self.barge_in_count = 0

    def handle_audio_frame(
        self,
        frame: np.ndarray,
        is_assistant_speaking: bool,
        ambient_baseline_rms: float,
        tts_abort_fn: Optional[Callable[[], None]] = None
    ) -> bool:
        """
        Processes a single microphone frame.
        If assistant is speaking and user interrupts (barge-in):
        Invokes tts_abort_fn and returns True.
        """
        if is_assistant_speaking and self.barge_in.check_barge_in(frame, is_assistant_speaking, ambient_baseline_rms):
            self.barge_in_count += 1
            if tts_abort_fn:
                try:
                    tts_abort_fn()
                    logger.info("⚡ [Duplex Pipeline] Assistant speech halted via user barge-in.")
                except Exception as ex:
                    logger.warning(f"Error in TTS abort callback during barge-in: {ex}")
            return True
        return False

    def handle_transcribed_text(
        self,
        raw_text: str,
        tts_abort_fn: Optional[Callable[[], None]] = None
    ) -> dict:
        """
        Processes transcribed utterance:
        - Detects voice emergency stop commands ("STOP", "CANCEL", "SHUT UP").
        - Triggers global emergency stop if detected.
        - Parses wake word and command payload.
        """
        matched_wake, clean_cmd, is_stop = self.wake_detector.classify_utterance(raw_text)

        if is_stop:
            logger.warning(f"🛑 [Duplex Pipeline] Voice Emergency Stop triggered by utterance: '{raw_text}'")
            if tts_abort_fn:
                tts_abort_fn()
            self.stop_mgr.trigger_stop(source=f"voice:{raw_text}")
            return {
                "action": "EMERGENCY_STOP",
                "matched_wake": matched_wake,
                "command": clean_cmd,
                "raw_text": raw_text
            }

        return {
            "action": "DISPATCH",
            "matched_wake": matched_wake,
            "command": clean_cmd,
            "raw_text": raw_text
        }


# Global Singleton Duplex Pipeline
duplex_pipeline = DuplexVoicePipeline()
