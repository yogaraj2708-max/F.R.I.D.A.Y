"""
Unit tests for F.R.I.D.A.Y. 3.0 Transcript Deduplication Defense.
Verifies that rapid duplicate utterances, partial/final echo loops,
and repeated VAD triggers are suppressed within the temporal window.
"""

import time
import pytest
from friday_core.voice.deduplicator import TranscriptDeduplicator


class TestTranscriptDeduplication:

    def test_single_utterance_allowed(self):
        """Verify first occurrence of an utterance is allowed."""
        dedup = TranscriptDeduplicator(window_sec=2.5)
        is_dup, reason = dedup.is_duplicate("Open Notepad")
        assert is_dup is False
        assert reason == ""

    def test_exact_duplicate_suppression_within_window(self):
        """Verify exact duplicate within time window is blocked."""
        dedup = TranscriptDeduplicator(window_sec=2.5)
        # First utterance
        is_dup, _ = dedup.is_duplicate("Open Notepad")
        assert is_dup is False

        # Immediate repeat
        is_dup, reason = dedup.is_duplicate("Open Notepad")
        assert is_dup is True
        assert "duplicate" in reason.lower()

    def test_case_and_punctuation_insensitive_duplicate(self):
        """Verify duplicate suppression ignores casing and trailing punctuation."""
        dedup = TranscriptDeduplicator(window_sec=2.5)
        is_dup, _ = dedup.is_duplicate("What is the time?")
        assert is_dup is False

        # Slight variation in casing and punctuation
        is_dup, reason = dedup.is_duplicate("what is the time")
        assert is_dup is True

    def test_partial_echo_suppression(self):
        """Verify partial prefix echo within 1.2s is suppressed."""
        dedup = TranscriptDeduplicator(window_sec=2.5)
        is_dup, _ = dedup.is_duplicate("What is the latest NVIDIA news today?")
        assert is_dup is False

        # Shorter substring immediately after
        is_dup, reason = dedup.is_duplicate("What is the latest NVIDIA news")
        assert is_dup is True
        assert "echo" in reason.lower()

    def test_distinct_utterances_allowed(self):
        """Verify different utterances in succession are both allowed."""
        dedup = TranscriptDeduplicator(window_sec=2.5)
        is_dup1, _ = dedup.is_duplicate("Open Notepad")
        is_dup2, _ = dedup.is_duplicate("Type hello world")
        assert is_dup1 is False
        assert is_dup2 is False

    def test_window_expiration_allows_repeat(self):
        """Verify that after the time window expires, the same command can be spoken again."""
        dedup = TranscriptDeduplicator(window_sec=0.1)
        is_dup1, _ = dedup.is_duplicate("Open Calculator")
        assert is_dup1 is False

        time.sleep(0.15)  # Wait past window

        is_dup2, _ = dedup.is_duplicate("Open Calculator")
        assert is_dup2 is False

    def test_manual_reset(self):
        """Verify manual reset clears history immediately."""
        dedup = TranscriptDeduplicator(window_sec=10.0)
        dedup.is_duplicate("Turn on lights")
        dedup.reset()
        is_dup, _ = dedup.is_duplicate("Turn on lights")
        assert is_dup is False
