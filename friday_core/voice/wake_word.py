"""
F.R.I.D.A.Y. 3.0 — Acoustic Wake Word & Duplex Barge-In Detector
Processes streaming audio chunks for hands-free wake word recognition and instant voice interruption.
"""

import re
import numpy as np
import logging
from typing import Tuple, Optional, List
from friday_core.agent.emergency_stop import emergency_stop

logger = logging.getLogger("FRIDAY.WakeWord")

DEFAULT_WAKE_WORDS = ["hey friday", "friday", "ok friday", "okay friday", "hey jarvis", "jarvis"]
EMERGENCY_STOP_WORDS = ["stop", "cancel", "shut up", "halt", "abort", "freeze", "quiet", "silence"]


class WakeWordDetector:
    """
    Lightweight, local acoustic wake word and intent extractor.
    Runs independently of heavy LLM inference.
    """
    def __init__(self, wake_words: Optional[List[str]] = None):
        self.wake_words = sorted(wake_words or DEFAULT_WAKE_WORDS, key=len, reverse=True)
        self.stop_words = EMERGENCY_STOP_WORDS

    def classify_utterance(self, raw_text: str) -> Tuple[Optional[str], str, bool]:
        """
        Classifies an utterance.
        Returns:
            (matched_wake_word, cleaned_command, is_emergency_stop)
        """
        if not raw_text:
            return None, "", False

        text = raw_text.strip().lower()

        # 1. Check for Emergency Stop Commands first
        for word in self.stop_words:
            if re.search(rf"\b{re.escape(word)}\b", text):
                logger.warning(f"Voice Emergency Stop command recognized: '{word}' in '{text}'")
                return None, text, True

        # 2. Check for Wake Word
        matched_wake = None
        match_span = None
        for w in self.wake_words:
            m = re.search(rf"\b{re.escape(w)}\b", text)
            if m:
                matched_wake = w
                match_span = m.span()
                break

        if not matched_wake:
            return None, text, False

        # Extract remaining command
        after = text[match_span[1]:].lstrip(" ,:.-").strip()
        before = text[:match_span[0]].lstrip(" ,:.-").strip()
        remainder = after if after else before

        cleaned = re.sub(
            r"^(?:hey|hi|hello|ok|okay|please|can you|could you|would you|uh|um|so|well)\s+",
            "",
            remainder,
            flags=re.IGNORECASE
        ).lstrip(" ,:.-").strip()

        # Check if the extracted command is an emergency stop
        for word in self.stop_words:
            if re.search(rf"\b{re.escape(word)}\b", cleaned):
                return matched_wake, cleaned, True

        return matched_wake, cleaned, False


class DuplexBargeInManager:
    """
    Evaluates acoustic energy levels to detect user barge-in interruptions
    while F.R.I.D.A.Y. is speaking.
    """
    def __init__(self, energy_multiplier: float = 2.8, min_rms_threshold: float = 65.0):
        self.energy_multiplier = energy_multiplier
        self.min_rms_threshold = min_rms_threshold

    def calculate_rms(self, audio_chunk: np.ndarray) -> float:
        """Calculates root-mean-square amplitude of an audio block."""
        if audio_chunk is None or len(audio_chunk) == 0:
            return 0.0
        try:
            samples = audio_chunk.astype(np.float32)
            return float(np.sqrt(np.mean(samples ** 2)))
        except Exception:
            return 0.0

    def check_barge_in(
        self,
        audio_chunk: np.ndarray,
        is_assistant_speaking: bool,
        ambient_baseline_rms: float
    ) -> bool:
        """
        Determines whether the incoming audio block represents an active user barge-in.
        Returns True if user voice interruption threshold is exceeded during playback.
        """
        if not is_assistant_speaking:
            return False

        chunk_rms = self.calculate_rms(audio_chunk)
        threshold = max(ambient_baseline_rms * self.energy_multiplier, self.min_rms_threshold)

        if chunk_rms >= threshold:
            logger.info(
                f"🎙️ [Barge-In Detected] Audio RMS {chunk_rms:.1f} exceeded speech threshold {threshold:.1f}. "
                "Triggering assistant speech cut-off."
            )
            return True

        return False


# Global singletons
wake_word_detector = WakeWordDetector()
barge_in_manager = DuplexBargeInManager()
