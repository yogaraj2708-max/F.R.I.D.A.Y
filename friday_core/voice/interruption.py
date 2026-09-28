"""
F.R.I.D.A.Y. 3.0 — Voice Interruption & Echo Controller
Enforces deterministic acoustic barge-in interruption policy and echo loop suppression.
"""

import time
import logging
from typing import Optional, Callable
import numpy as np

logger = logging.getLogger("FRIDAY.Interruption")

# Cooldown seconds mic remains in echo suppression after TTS ends
MIC_COOLDOWN_AFTER_SPEECH = 0.45


class VoiceInterruptionController:
    """
    Deterministic Voice Interruption & Echo Defense:
    
    POLICY: [BARGE-IN CUTOFF]
    - When assistant is speaking:
      1. Incoming audio is continuously monitored for user speech interruption.
      2. If acoustic energy exceeds the dynamic barge-in threshold (RMS >= baseline * multiplier),
         or emergency stop command is detected, TTS playback is immediately terminated.
      3. The speech queue is purged and the system transitions to LISTENING.
    - Echo Suppression:
      Microphone frames are ignored for 0.45s after speech completes to discard acoustic reverb.
    """

    def __init__(
        self,
        energy_multiplier: float = 2.8,
        min_rms_threshold: float = 65.0,
        cooldown_sec: float = MIC_COOLDOWN_AFTER_SPEECH
    ):
        self.energy_multiplier = energy_multiplier
        self.min_rms_threshold = min_rms_threshold
        self.cooldown_sec = cooldown_sec
        self.barge_in_count = 0

    def calculate_rms(self, audio_chunk: np.ndarray) -> float:
        if audio_chunk is None or len(audio_chunk) == 0:
            return 0.0
        try:
            samples = audio_chunk.astype(np.float32)
            return float(np.sqrt(np.mean(samples ** 2)))
        except Exception:
            return 0.0

    def is_in_echo_cooldown(self, speech_ended_at: float, now: Optional[float] = None) -> bool:
        """Checks if the system is in the post-speech reverberation cooldown window."""
        t = now if now is not None else time.monotonic()
        return (t - speech_ended_at) < self.cooldown_sec

    def check_barge_in(
        self,
        audio_chunk: np.ndarray,
        is_assistant_speaking: bool,
        ambient_baseline_rms: float,
        tts_abort_fn: Optional[Callable[[], None]] = None
    ) -> bool:
        """
        Evaluates incoming microphone frame during assistant speech.
        If user speaks loudly over playback:
        Calls tts_abort_fn() and returns True.
        """
        if not is_assistant_speaking:
            return False

        chunk_rms = self.calculate_rms(audio_chunk)
        threshold = max(ambient_baseline_rms * self.energy_multiplier, self.min_rms_threshold)

        if chunk_rms >= threshold:
            self.barge_in_count += 1
            logger.info(
                "🎙️ [Barge-In Interruption] User speech RMS %.1f >= threshold %.1f. Aborting assistant speech.",
                chunk_rms, threshold
            )
            if tts_abort_fn:
                try:
                    tts_abort_fn()
                except Exception as ex:
                    logger.warning("Error invoking TTS abort callback: %s", ex)
            return True

        return False


# Global Singleton Interruption Controller
voice_interruption_controller = VoiceInterruptionController()
