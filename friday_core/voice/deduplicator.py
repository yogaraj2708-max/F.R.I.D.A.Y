"""
F.R.I.D.A.Y. 3.0 — Transcript Deduplicator
Guards against duplicate voice submissions, partial+final transcript echoes,
and acoustic loopback triggers within dynamic time windows.
"""

import re
import time
import logging
from typing import Optional, List, Tuple

logger = logging.getLogger("FRIDAY.Deduplicator")


class TranscriptDeduplicator:
    """
    Prevents duplicate execution of identical speech utterances caused by:
    - Rapid back-to-back VAD acoustic triggers
    - Overlapping partial and final STT transcription callbacks
    - Sound loopback echoes
    """

    def __init__(self, window_sec: float = 2.5, dedup_window_sec: Optional[float] = None, max_history: int = 20):
        self.window_sec = dedup_window_sec if dedup_window_sec is not None else window_sec
        self.dedup_window_sec = self.window_sec
        self.max_history = max_history
        self._history: List[Tuple[float, str]] = []  # (timestamp, normalized_text)

    @property
    def history(self) -> List[Tuple[float, str]]:
        return self._history

    def normalize(self, text: str) -> str:
        if not text:
            return ""
        # Strip punctuation and lower case for robust comparison
        clean = re.sub(r"[^\w\s]", "", text.strip().lower())
        return re.sub(r"\s+", " ", clean)

    def is_duplicate(self, text: str, now: Optional[float] = None) -> Tuple[bool, str]:
        """
        Evaluates whether the candidate utterance is a duplicate of a recent utterance.
        Returns: (is_duplicate: bool, reason: str)
        If not duplicate, reason is empty string "".
        """
        if not text:
            return True, "EMPTY_TEXT"

        clean = self.normalize(text)
        t = now if now is not None else time.time()

        # Prune older history beyond window
        cutoff = t - self.window_sec
        self._history = [(ts, item) for ts, item in self._history if ts >= cutoff]

        for ts, prev_text in reversed(self._history):
            elapsed = t - ts
            if elapsed <= self.window_sec:
                # 1. Exact match
                if clean == prev_text:
                    logger.warning(
                        "🛑 [Deduplicator] Suppressed exact duplicate utterance '%s' (elapsed: %.2fs <= %.2fs)",
                        clean, elapsed, self.window_sec
                    )
                    return True, f"EXACT_DUPLICATE_WITHIN_{elapsed:.2f}S"

                # 2. Substring echo / partial match
                if len(clean) >= 4 and len(prev_text) >= 4:
                    if clean in prev_text or prev_text in clean:
                        logger.warning(
                            "🛑 [Deduplicator] Suppressed partial duplicate utterance '%s' vs '%s' (elapsed: %.2fs)",
                            clean, prev_text, elapsed
                        )
                        return True, f"SUBSTRING_ECHO_WITHIN_{elapsed:.2f}S"

        # Record clean utterance in history
        self._history.append((t, clean))
        if len(self._history) > self.max_history:
            self._history.pop(0)

        return False, ""

    def clear(self):
        """Resets deduplicator history."""
        self._history.clear()

    reset = clear


# Global Singleton Deduplicator
transcript_deduplicator = TranscriptDeduplicator()
