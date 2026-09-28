"""
Unit and integration tests for F.R.I.D.A.Y. 3.0 Voice Resource Cleanup.
Verifies no leaking of audio streams, reader threads, or memory
over repeated start/stop cycles.
"""

import threading
import gc
import pytest
from unittest.mock import MagicMock, patch

from friday_ui.core.engine import FridayVoiceLoop, FridaySignals, FridayBrain, FridayVoiceEngine
from friday_core.voice.deduplicator import TranscriptDeduplicator


class TestVoiceResourceCleanup:

    def test_voice_loop_start_stop_thread_safety(self):
        """Verify repeated start and stop cycles do not leak threads or corrupt state."""
        signals = FridaySignals()
        brain = MagicMock()
        tts = MagicMock()
        tts.voice_loop_active = False

        initial_threads = threading.active_count()
        loop = FridayVoiceLoop(signals, brain, tts)

        for _ in range(25):
            loop.start()
            assert loop.running is True
            assert tts.voice_loop_active is True
            loop.stop()
            assert loop.running is False
            assert tts.voice_loop_active is False

        # Thread count should remain stable
        current_threads = threading.active_count()
        assert current_threads <= initial_threads + 1

    def test_deduplicator_bounded_memory(self):
        """Verify deduplicator prunes old entries and does not grow indefinitely."""
        dedup = TranscriptDeduplicator(window_sec=0.01)

        for i in range(100):
            dedup.is_duplicate(f"Utterance number {i}")

        # Sleep past window and check another utterance to trigger prune
        import time
        time.sleep(0.02)
        dedup.is_duplicate("Trigger prune utterance")

        # History size should be tightly bounded (only recent entries)
        assert len(dedup.history) <= 5

    def test_reader_idle_event_synchronization(self):
        """Verify _reader_idle event is set when not recording to avoid PortAudio use-after-close."""
        signals = FridaySignals()
        brain = MagicMock()
        tts = MagicMock()
        loop = FridayVoiceLoop(signals, brain, tts)

        assert loop._reader_idle.is_set() is True
